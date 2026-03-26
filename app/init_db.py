import csv
import logging
import os
from datetime import datetime, timedelta, timezone

from app import db
from app.models import ActivityLog, Customer, Payment, RouteStop, User

logger = logging.getLogger(__name__)


def init_db(app):
    """Initialize database tables and fix any data issues"""
    with app.app_context():
        db.create_all()

        # Run schema migrations (add missing columns)
        from sqlalchemy import text, inspect
        inspector = inspect(db.engine)
        is_postgres = "postgresql" in app.config["SQLALCHEMY_DATABASE_URI"]

        # Helper to check if column exists
        def column_exists(table_name, column_name):
            if table_name in inspector.get_table_names():
                columns = [col["name"] for col in inspector.get_columns(table_name)]
                return column_name in columns
            return False

        # Migrate user table - add role column
        if "user" in inspector.get_table_names() and not column_exists("user", "role"):
            if is_postgres:
                db.session.execute(text('ALTER TABLE "user" ADD COLUMN role VARCHAR(20) DEFAULT \'sales\''))
            else:
                db.session.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR(20) DEFAULT 'sales'"))
            db.session.execute(text("UPDATE \"user\" SET role='admin' WHERE username='admin'"))
            db.session.commit()
            logger.info("Added role column to user table")

        # Migrate payment table - add receipt_number and previous_balance columns
        if "payment" in inspector.get_table_names():
            if not column_exists("payment", "receipt_number"):
                db.session.execute(text("ALTER TABLE payment ADD COLUMN receipt_number VARCHAR(20)"))
                db.session.commit()
                logger.info("Added receipt_number column to payment table")

            if not column_exists("payment", "previous_balance"):
                db.session.execute(text("ALTER TABLE payment ADD COLUMN previous_balance NUMERIC(10,2)"))
                db.session.commit()
                logger.info("Added previous_balance column to payment table")

        # Migrate customer table - add status column
        if "customer" in inspector.get_table_names() and not column_exists("customer", "status"):
            db.session.execute(text("ALTER TABLE customer ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
            db.session.execute(text("UPDATE customer SET status = 'active' WHERE status IS NULL"))
            db.session.commit()
            logger.info("Added status column to customer table")

        # Migrate customer table - add tax_exempt column
        if "customer" in inspector.get_table_names() and not column_exists("customer", "tax_exempt"):
            if is_postgres:
                db.session.execute(text("ALTER TABLE customer ADD COLUMN tax_exempt BOOLEAN DEFAULT FALSE"))
            else:
                db.session.execute(text("ALTER TABLE customer ADD COLUMN tax_exempt BOOLEAN DEFAULT 0"))
            db.session.commit()
            logger.info("Added tax_exempt column to customer table")

        # Migrate customer table - add lead_source column
        if "customer" in inspector.get_table_names() and not column_exists("customer", "lead_source"):
            db.session.execute(text("ALTER TABLE customer ADD COLUMN lead_source VARCHAR(50)"))
            db.session.commit()
            logger.info("Added lead_source column to customer table")

        # Migrate money columns from FLOAT to NUMERIC(10,2) (PostgreSQL only)
        if is_postgres:
            try:
                db.session.execute(text("ALTER TABLE customer ALTER COLUMN balance TYPE NUMERIC(10,2)"))
                db.session.execute(text("ALTER TABLE payment ALTER COLUMN amount TYPE NUMERIC(10,2)"))
                db.session.execute(text("ALTER TABLE payment ALTER COLUMN previous_balance TYPE NUMERIC(10,2)"))
                db.session.commit()
                logger.info("Migrated money columns from FLOAT to NUMERIC(10,2)")
            except Exception:
                db.session.rollback()  # Already migrated or no data

        # Create default admin user if no users exist
        if User.query.count() == 0:
            import secrets
            default_password = os.environ.get("ADMIN_PASSWORD", secrets.token_urlsafe(16))
            admin = User(
                username="admin",
                email="admin@candyroute.local",
                role="admin"
            )
            admin.set_password(default_password)
            db.session.add(admin)
            db.session.commit()
            if os.environ.get("FLASK_ENV") == "development":
                logger.warning(f"Created default admin user (username: admin, password: {default_password})")
            else:
                logger.warning("Created default admin user (username: admin). Password was set from ADMIN_PASSWORD env var or generated randomly — check startup logs.")
            logger.warning("Change the default admin password immediately!")

        # Import customers from CSV if database is empty
        if Customer.query.count() == 0:
            csv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "customers_cleaned.csv")
            if os.path.exists(csv_file):
                logger.info(f"Importing customers from {csv_file}...")
                imported = 0
                try:
                    with open(csv_file, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            customer = Customer(
                                name=row["name"],
                                address=row.get("address", ""),
                                city=row.get("city", ""),
                                phone=row.get("phone", ""),
                                balance=0.0,
                                created_at=datetime.now(timezone.utc),
                            )
                            db.session.add(customer)
                            imported += 1
                            if imported % 50 == 0:
                                db.session.commit()
                    db.session.commit()
                    logger.info(f"Imported {imported} customers from CSV")
                except Exception as e:
                    logger.error(f"Error importing customers: {e}")
                    db.session.rollback()

        # Fix any None balances
        customers_with_none_balance = Customer.query.filter(
            Customer.balance == None
        ).all()
        for customer in customers_with_none_balance:
            customer.balance = 0.0
        if customers_with_none_balance:
            db.session.commit()
            logger.info(f"Fixed {len(customers_with_none_balance)} customers with None balance")

        # Fix any None created_at dates
        customers_with_none_created = Customer.query.filter(
            Customer.created_at == None
        ).all()
        for customer in customers_with_none_created:
            customer.created_at = datetime.now(timezone.utc)
        if customers_with_none_created:
            db.session.commit()
            logger.info(f"Fixed {len(customers_with_none_created)} customers with None created_at")

        # Add sample data in development mode
        if os.environ.get("FLASK_ENV") == "development" and Customer.query.count() == 0:
            today = datetime.now(timezone.utc).date()
            sample_customers = [
                Customer(
                    name="Acme Grocery",
                    city="Springfield",
                    address="123 Main St",
                    phone="555-0101",
                    balance=150.00,
                    last_visit=datetime.now(timezone.utc).date() - timedelta(days=5),
                ),
                Customer(
                    name="Best Market",
                    city="Springfield",
                    address="456 Oak Ave",
                    phone="555-0102",
                    balance=0,
                    last_visit=datetime.now(timezone.utc).date() - timedelta(days=2),
                ),
                Customer(
                    name="Corner Store",
                    city="Shelbyville",
                    address="789 Elm St",
                    phone="555-0103",
                    balance=75.50,
                    last_visit=datetime.now(timezone.utc).date() - timedelta(days=35),
                ),
                Customer(
                    name="Downtown Deli",
                    city="Springfield",
                    address="321 Pine Rd",
                    phone="555-0104",
                    balance=0,
                ),
                Customer(
                    name="Express Mart",
                    city="Capital City",
                    address="555 Cedar Ln",
                    phone="555-0105",
                    balance=200.00,
                    last_visit=datetime.now(timezone.utc).date() - timedelta(days=15),
                ),
                Customer(
                    name="Fresh Foods",
                    city="Shelbyville",
                    address="888 Birch Dr",
                    phone="555-0106",
                    balance=50.00,
                    last_visit=datetime.now(timezone.utc).date() - timedelta(days=8),
                ),
            ]
            db.session.add_all(sample_customers)
            db.session.commit()

            # Create today's route
            today_stops = [
                RouteStop(
                    customer_id=sample_customers[0].id,
                    route_date=today,
                    sequence=1,
                    completed=True,
                ),
                RouteStop(
                    customer_id=sample_customers[1].id,
                    route_date=today,
                    sequence=2,
                    completed=True,
                ),
                RouteStop(
                    customer_id=sample_customers[4].id,
                    route_date=today,
                    sequence=3,
                    completed=False,
                ),
                RouteStop(
                    customer_id=sample_customers[5].id,
                    route_date=today,
                    sequence=4,
                    completed=False,
                ),
            ]
            db.session.add_all(today_stops)

            # Create a future route (tomorrow)
            tomorrow = today + timedelta(days=1)
            tomorrow_stops = [
                RouteStop(
                    customer_id=sample_customers[2].id,
                    route_date=tomorrow,
                    sequence=1,
                    completed=False,
                ),
            ]
            db.session.add_all(tomorrow_stops)

            # Add some payment history
            sample_payments = [
                Payment(
                    customer_id=sample_customers[0].id,
                    amount=50.00,
                    payment_date=today - timedelta(days=10),
                ),
                Payment(
                    customer_id=sample_customers[1].id,
                    amount=120.00,
                    payment_date=today - timedelta(days=5),
                ),
                Payment(
                    customer_id=sample_customers[4].id,
                    amount=25.00,
                    payment_date=today - timedelta(days=20),
                ),
                Payment(
                    customer_id=sample_customers[2].id,
                    amount=75.00,
                    payment_date=today - timedelta(days=15),
                ),
            ]
            db.session.add_all(sample_payments)

            db.session.commit()
            print("Sample data added with routes and payments!")

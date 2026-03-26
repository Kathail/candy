import csv
import logging
import os
from datetime import datetime, timedelta, timezone

from app import db
from app.models import (ActivityLog, Announcement, AuditLog, Customer, Payment,
                        RouteStop, RouteTemplate, RouteTemplateStop, Setting, User)

logger = logging.getLogger(__name__)


def init_db(app):
    """Initialize database tables and fix any data issues"""
    with app.app_context():
        db.create_all()

        # Run schema migrations (add missing columns)
        # Single inspect call to minimize Turso round-trips
        from sqlalchemy import text, inspect
        try:
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
        except Exception as e:
            logger.warning(f"Could not inspect database: {e}")
            return

        is_postgres = "postgresql" in app.config["SQLALCHEMY_DATABASE_URI"]

        # Build column map in one pass
        column_map = {}
        for table in tables:
            try:
                column_map[table] = {col["name"] for col in inspector.get_columns(table)}
            except Exception:
                column_map[table] = set()

        def column_exists(table_name, column_name):
            return column_name in column_map.get(table_name, set())

        # Migrate user table - add role column
        if "user" in tables and not column_exists("user", "role"):
            if is_postgres:
                db.session.execute(text('ALTER TABLE "user" ADD COLUMN role VARCHAR(20) DEFAULT \'sales\''))
            else:
                db.session.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR(20) DEFAULT 'sales'"))
            db.session.execute(text("UPDATE \"user\" SET role='admin' WHERE username='admin'"))
            db.session.commit()
            logger.info("Added role column to user table")

        # Migrate payment table - add receipt_number and previous_balance columns
        if "payment" in tables:
            if not column_exists("payment", "receipt_number"):
                db.session.execute(text("ALTER TABLE payment ADD COLUMN receipt_number VARCHAR(20)"))
                db.session.commit()
                logger.info("Added receipt_number column to payment table")

            if not column_exists("payment", "previous_balance"):
                db.session.execute(text("ALTER TABLE payment ADD COLUMN previous_balance NUMERIC(10,2)"))
                db.session.commit()
                logger.info("Added previous_balance column to payment table")

        # Migrate customer table - add status column
        if "customer" in tables and not column_exists("customer", "status"):
            db.session.execute(text("ALTER TABLE customer ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
            db.session.execute(text("UPDATE customer SET status = 'active' WHERE status IS NULL"))
            db.session.commit()
            logger.info("Added status column to customer table")

        # Migrate customer table - add tax_exempt column
        if "customer" in tables and not column_exists("customer", "tax_exempt"):
            if is_postgres:
                db.session.execute(text("ALTER TABLE customer ADD COLUMN tax_exempt BOOLEAN DEFAULT FALSE"))
            else:
                db.session.execute(text("ALTER TABLE customer ADD COLUMN tax_exempt BOOLEAN DEFAULT 0"))
            db.session.commit()
            logger.info("Added tax_exempt column to customer table")

        # Migrate customer table - add lead_source column
        if "customer" in tables and not column_exists("customer", "lead_source"):
            db.session.execute(text("ALTER TABLE customer ADD COLUMN lead_source VARCHAR(50)"))
            db.session.commit()
            logger.info("Added lead_source column to customer table")

        # Migrate customer table - add assigned_to column
        if "customer" in tables and not column_exists("customer", "assigned_to"):
            db.session.execute(text("ALTER TABLE customer ADD COLUMN assigned_to INTEGER REFERENCES user(id)"))
            db.session.commit()
            logger.info("Added assigned_to column to customer table")

        # Migrate user table - add is_active_user and last_login columns
        if "user" in tables:
            if not column_exists("user", "is_active_user"):
                if is_postgres:
                    db.session.execute(text('ALTER TABLE "user" ADD COLUMN is_active_user BOOLEAN DEFAULT TRUE'))
                else:
                    db.session.execute(text("ALTER TABLE user ADD COLUMN is_active_user BOOLEAN DEFAULT 1"))
                db.session.commit()
                logger.info("Added is_active_user column to user table")

            if not column_exists("user", "last_login"):
                if is_postgres:
                    db.session.execute(text('ALTER TABLE "user" ADD COLUMN last_login TIMESTAMP'))
                else:
                    db.session.execute(text("ALTER TABLE user ADD COLUMN last_login DATETIME"))
                db.session.commit()
                logger.info("Added last_login column to user table")

        # Migrate money columns from FLOAT to NUMERIC(10,2) (PostgreSQL only)
        if is_postgres:
            try:
                db.session.execute(text("ALTER TABLE customer ALTER COLUMN balance TYPE NUMERIC(10,2)"))
                db.session.execute(text("ALTER TABLE payment ALTER COLUMN amount TYPE NUMERIC(10,2)"))
                db.session.execute(text("ALTER TABLE payment ALTER COLUMN previous_balance TYPE NUMERIC(10,2)"))
                db.session.commit()
                logger.info("Migrated money columns from FLOAT to NUMERIC(10,2)")
            except Exception:
                db.session.rollback()

        # Create default admin user if no users exist
        if User.query.count() == 0:
            import secrets
            is_dev = os.environ.get("FLASK_ENV") == "development"
            admin_pw = os.environ.get("ADMIN_PASSWORD")

            if not admin_pw:
                if is_dev:
                    admin_pw = secrets.token_urlsafe(16)
                    # Print once to console — never to persistent logs
                    print(f"\n{'='*60}")
                    print(f"  DEV ONLY — initial admin password: {admin_pw}")
                    print(f"  username: admin")
                    print(f"  Change this immediately via /admin/users")
                    print(f"{'='*60}\n")
                else:
                    logger.critical(
                        "ADMIN_PASSWORD env var is required on first run in production. "
                        "Set it and restart."
                    )
                    return

            admin = User(
                username="admin",
                email="admin@candyroute.local",
                role="admin"
            )
            admin.set_password(admin_pw)
            db.session.add(admin)
            db.session.commit()
            logger.info("Created default admin user (username: admin). Change password immediately.")

        # Fix any None balances
        try:
            customers_with_none_balance = Customer.query.filter(
                Customer.balance == None
            ).all()
            for customer in customers_with_none_balance:
                customer.balance = 0.0
            if customers_with_none_balance:
                db.session.commit()
                logger.info(f"Fixed {len(customers_with_none_balance)} customers with None balance")
        except Exception:
            db.session.rollback()

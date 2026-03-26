import logging
import os
from datetime import datetime, timezone

from app import db
from app.models import (ActivityLog, Announcement, AuditLog, Customer, Payment,
                        RouteStop, RouteTemplate, RouteTemplateStop, Setting, User)

logger = logging.getLogger(__name__)


def _column_exists_sqlite(table_name, column_name):
    """Check if a column exists using PRAGMA — works on SQLite, libsql, and Turso."""
    from sqlalchemy import text
    try:
        # Strip quotes from table name for PRAGMA
        clean_name = table_name.strip('"')
        result = db.session.execute(text(f"PRAGMA table_info({clean_name})"))
        columns = {row[1] for row in result}
        return column_name in columns
    except Exception as e:
        logger.warning(f"PRAGMA table_info failed for {table_name}: {e}")
        return True  # Assume exists to avoid breaking ALTER TABLE


def _column_exists_postgres(table_name, column_name):
    """Check if a column exists using information_schema — PostgreSQL only."""
    from sqlalchemy import text
    try:
        clean_name = table_name.strip('"')
        result = db.session.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :col"
        ), {"table": clean_name, "col": column_name})
        return result.fetchone() is not None
    except Exception:
        return True  # Assume exists


def _add_column(table, column_name, column_def, is_postgres=False):
    """Add a column if it doesn't exist. Check first, then ALTER TABLE."""
    from sqlalchemy import text

    # Check if column already exists
    if is_postgres:
        exists = _column_exists_postgres(table, column_name)
    else:
        exists = _column_exists_sqlite(table, column_name)

    if exists:
        return

    sql = f"ALTER TABLE {table} ADD COLUMN {column_def}"
    try:
        db.session.execute(text(sql))
        db.session.commit()
        logger.info(f"Migration OK: {table}.{column_name}")
    except Exception as e:
        db.session.rollback()
        logger.warning(f"Migration FAILED: {table}.{column_name} — {e} — SQL: {sql}")


def init_db(app):
    """Initialize database tables and fix any data issues."""
    with app.app_context():
        db.create_all()
        logger.info("db.create_all() completed")

        is_pg = "postgresql" in app.config.get("SQLALCHEMY_DATABASE_URI", "")

        # --- User table migrations ---
        _add_column('"user"', "role", "role VARCHAR(20) DEFAULT 'sales'", is_pg)
        _add_column('"user"', "is_active_user",
                    "is_active_user BOOLEAN DEFAULT " + ("TRUE" if is_pg else "1"), is_pg)
        _add_column('"user"', "last_login",
                    "last_login " + ("TIMESTAMP" if is_pg else "DATETIME"), is_pg)

        # Set admin role on existing admin user if role was just added
        from sqlalchemy import text
        try:
            db.session.execute(text('UPDATE "user" SET role=\'admin\' WHERE username=\'admin\' AND role IS NULL'))
            db.session.commit()
        except Exception:
            db.session.rollback()

        # --- Payment table migrations ---
        _add_column("payment", "receipt_number", "receipt_number VARCHAR(20)", is_pg)
        _add_column("payment", "previous_balance", "previous_balance NUMERIC(10,2)", is_pg)

        # --- Customer table migrations ---
        _add_column("customer", "status", "status VARCHAR(20) DEFAULT 'active'", is_pg)
        _add_column("customer", "tax_exempt",
                    "tax_exempt BOOLEAN DEFAULT " + ("FALSE" if is_pg else "0"), is_pg)
        _add_column("customer", "lead_source", "lead_source VARCHAR(50)", is_pg)
        _add_column("customer", "assigned_to", "assigned_to INTEGER", is_pg)

        # Set status on existing customers
        try:
            db.session.execute(text("UPDATE customer SET status = 'active' WHERE status IS NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        # --- PostgreSQL-only: fix money column types ---
        if is_pg:
            try:
                db.session.execute(text("ALTER TABLE customer ALTER COLUMN balance TYPE NUMERIC(10,2)"))
                db.session.execute(text("ALTER TABLE payment ALTER COLUMN amount TYPE NUMERIC(10,2)"))
                db.session.execute(text("ALTER TABLE payment ALTER COLUMN previous_balance TYPE NUMERIC(10,2)"))
                db.session.commit()
            except Exception:
                db.session.rollback()

        # --- Create default admin user if no users exist ---
        try:
            user_count = User.query.count()
        except Exception as e:
            logger.warning(f"Could not query users: {e}")
            user_count = 1  # Assume users exist to avoid duplicate creation

        if user_count == 0:
            import secrets
            is_dev = os.environ.get("FLASK_ENV") == "development"
            admin_pw = os.environ.get("ADMIN_PASSWORD")

            if not admin_pw:
                if is_dev:
                    admin_pw = secrets.token_urlsafe(16)
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

        # --- Fix any None balances ---
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

        logger.info("init_db completed successfully")

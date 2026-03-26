import logging
import os
from datetime import datetime, timezone

from app import db
from app.models import (ActivityLog, Announcement, AuditLog, Customer, Payment,
                        RouteStop, RouteTemplate, RouteTemplateStop, Setting, User)

logger = logging.getLogger(__name__)


def _add_column(table, column_def, label=None):
    """Try to add a column; silently skip if it already exists."""
    from sqlalchemy import text
    try:
        db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_def}"))
        db.session.commit()
        logger.info(f"Added column: {label or column_def}")
    except Exception as e:
        db.session.rollback()
        err = str(e).lower()
        if "duplicate" in err or "already exists" in err or "duplicate column" in err:
            pass  # Column already exists — expected
        else:
            logger.debug(f"Column may already exist ({label}): {e}")


def init_db(app):
    """Initialize database tables and fix any data issues."""
    with app.app_context():
        # Create all tables (new tables like AuditLog, Announcement, Setting,
        # RouteTemplate, RouteTemplateStop are created here automatically)
        db.create_all()

        is_postgres = "postgresql" in app.config.get("SQLALCHEMY_DATABASE_URI", "")

        # --- User table migrations ---
        qt = '"user"' if is_postgres else "user"
        _add_column(qt, "role VARCHAR(20) DEFAULT 'sales'", "user.role")
        _add_column(qt, "is_active_user BOOLEAN DEFAULT " + ("TRUE" if is_postgres else "1"), "user.is_active_user")
        _add_column(qt, "last_login " + ("TIMESTAMP" if is_postgres else "DATETIME"), "user.last_login")

        # Set admin role on existing admin user if role was just added
        from sqlalchemy import text
        try:
            db.session.execute(text(f'UPDATE {qt} SET role=\'admin\' WHERE username=\'admin\' AND role IS NULL'))
            db.session.commit()
        except Exception:
            db.session.rollback()

        # --- Payment table migrations ---
        _add_column("payment", "receipt_number VARCHAR(20)", "payment.receipt_number")
        _add_column("payment", "previous_balance NUMERIC(10,2)", "payment.previous_balance")

        # --- Customer table migrations ---
        _add_column("customer", "status VARCHAR(20) DEFAULT 'active'", "customer.status")
        _add_column("customer", "tax_exempt BOOLEAN DEFAULT " + ("FALSE" if is_postgres else "0"), "customer.tax_exempt")
        _add_column("customer", "lead_source VARCHAR(50)", "customer.lead_source")
        _add_column("customer", "assigned_to INTEGER", "customer.assigned_to")

        # Set status on existing customers
        try:
            db.session.execute(text("UPDATE customer SET status = 'active' WHERE status IS NULL"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        # --- PostgreSQL-only: fix money column types ---
        if is_postgres:
            try:
                db.session.execute(text("ALTER TABLE customer ALTER COLUMN balance TYPE NUMERIC(10,2)"))
                db.session.execute(text("ALTER TABLE payment ALTER COLUMN amount TYPE NUMERIC(10,2)"))
                db.session.execute(text("ALTER TABLE payment ALTER COLUMN previous_balance TYPE NUMERIC(10,2)"))
                db.session.commit()
            except Exception:
                db.session.rollback()

        # --- Create default admin user if no users exist ---
        if User.query.count() == 0:
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

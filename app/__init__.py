import logging
import os
import sys

from flask import Flask, render_template
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

# --- 6. Logging ---
_is_dev = os.environ.get("FLASK_ENV") == "development"
logging.basicConfig(
    level=logging.DEBUG if _is_dev else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()
limiter = Limiter(get_remote_address, default_limits=[], storage_uri="memory://")
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"


def create_app():
    app = Flask(__name__, template_folder="../templates", static_folder="../static")

    is_dev = os.environ.get("FLASK_ENV") == "development"

    # --- 7. Debug mode lockdown ---
    app.config["DEBUG"] = is_dev

    # --- Database URL ---
    # Supports: Turso/libSQL, PostgreSQL, SQLite
    database_url = os.environ.get("DATABASE_URL", "sqlite:///candy_route.db")
    turso_token = os.environ.get("TURSO_AUTH_TOKEN")
    engine_options = {}

    if database_url.startswith("libsql://"):
        import libsql_experimental as libsql
        _libsql_url = database_url
        _libsql_token = turso_token
        engine_options["creator"] = lambda: libsql.connect(_libsql_url, auth_token=_libsql_token)
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite+libsql://"
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options

    # --- 4. Secret key validation ---
    _secret_key = os.environ.get("SECRET_KEY")
    if not _secret_key or _secret_key == "dev-secret-key-change-in-production":
        if is_dev:
            _secret_key = "dev-secret-key-change-in-production"
            logger.warning("No SECRET_KEY set — using insecure default.")
        else:
            logger.critical("FATAL: SECRET_KEY is missing or is the dev default. Refusing to start in production.")
            sys.exit(1)
    app.config["SECRET_KEY"] = _secret_key

    if not os.environ.get("ADMIN_PASSWORD") and not is_dev:
        logger.warning("ADMIN_PASSWORD not set — default admin will get a random password.")

    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600

    # --- 2. Session hardening ---
    app.config["SESSION_COOKIE_SECURE"] = not is_dev
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = 28800  # 8 hours

    # --- Initialize extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    # --- 1. Security headers (Talisman) ---
    if not is_dev:
        from flask_talisman import Talisman
        csp = {
            "default-src": "'self'",
            "script-src": "'self' 'unsafe-inline'",
            "style-src": "'self' 'unsafe-inline'",
            "img-src": "'self' data:",
            "font-src": "'self'",
            "connect-src": "'self'",
        }
        Talisman(
            app,
            force_https=True,
            strict_transport_security=True,
            content_security_policy=csp,
            frame_options="DENY",
            content_security_policy_nonce_in=[],
            referrer_policy="strict-origin-when-cross-origin",
        )

    # Import models
    from app import models  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id):
        return models.User.query.get(int(user_id))

    # Register blueprints
    from app.routes import register_blueprints
    register_blueprints(app)

    # --- 5. Error handlers ---
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        logger.exception("500 Internal Server Error")
        return render_template("errors/500.html"), 500

    @app.errorhandler(429)
    def ratelimit_error(error):
        return render_template("errors/429.html"), 429

    return app

import logging
import os
import pathlib
import sys

from flask import Flask, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

_is_dev = os.environ.get("FLASK_ENV") == "development"
logging.basicConfig(
    level=logging.DEBUG if _is_dev else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()
limiter = Limiter(get_remote_address, default_limits=[], storage_uri="memory://")
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"


def create_app():
    base_dir = pathlib.Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=str(base_dir / "templates"),
        static_folder=str(base_dir / "static"),
    )

    is_dev = os.environ.get("FLASK_ENV") == "development"
    app.config["DEBUG"] = is_dev

    # Database
    database_url = os.environ.get("DATABASE_URL", "sqlite:///candy_route.db")
    turso_token = os.environ.get("TURSO_AUTH_TOKEN")
    engine_options = {}

    if database_url.startswith("libsql://"):
        import libsql_experimental as libsql
        from sqlalchemy.pool import StaticPool
        engine_options["creator"] = lambda: libsql.connect(database_url, auth_token=turso_token)
        engine_options["poolclass"] = StaticPool
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite+libsql://"
    elif database_url.startswith("postgres://"):
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url.replace("postgres://", "postgresql://", 1)
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options

    # Secret key
    _secret_key = os.environ.get("SECRET_KEY")
    if not _secret_key or _secret_key == "dev-secret-key-change-in-production":
        if is_dev:
            _secret_key = "dev-secret-key-change-in-production"
            logger.warning("No SECRET_KEY set — using insecure default.")
        else:
            logger.critical("FATAL: SECRET_KEY is missing. Refusing to start in production.")
            sys.exit(1)
    app.config["SECRET_KEY"] = _secret_key

    if not os.environ.get("ADMIN_PASSWORD") and not is_dev:
        logger.warning("ADMIN_PASSWORD not set — default admin will get a random password.")

    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    app.config["WTF_CSRF_TIME_LIMIT"] = 3600

    # Session
    app.config["SESSION_COOKIE_SECURE"] = not is_dev
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = 28800

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    # Talisman (production only)
    if not is_dev:
        from flask_talisman import Talisman
        Talisman(
            app,
            force_https=True,
            strict_transport_security=True,
            content_security_policy={
                "default-src": "'self'",
                "script-src": "'self' 'unsafe-inline'",
                "style-src": "'self' 'unsafe-inline'",
                "img-src": "'self' data:",
                "font-src": "'self'",
                "connect-src": "'self'",
            },
            frame_options="DENY",
            content_security_policy_nonce_in=[],
            referrer_policy="strict-origin-when-cross-origin",
        )

    from app import models  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id):
        return models.User.query.get(int(user_id))

    from app.routes import register_blueprints
    register_blueprints(app)

    # Error handlers
    for code, template in [(403, "errors/403.html"), (404, "errors/404.html"), (429, "errors/429.html")]:
        app.register_error_handler(code, lambda e, t=template: (render_template(t), e.code))

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        logger.exception("500 Internal Server Error")
        return render_template("errors/500.html"), 500

    return app


app = create_app()

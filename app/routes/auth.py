import logging
from datetime import datetime, timezone

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import db, limiter
from app.helpers import is_safe_redirect_url, log_audit
from app.models import User

logger = logging.getLogger(__name__)
bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10/minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        client_ip = request.remote_addr

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if not user.is_active_user:
                logger.warning(f"Login BLOCKED (deactivated) user={username} ip={client_ip}")
                return render_template("login.html", error="Account is deactivated. Contact an admin.")

            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            login_user(user, remember=request.form.get("remember"))
            log_audit(user.id, "login", f"Login from {client_ip}")
            db.session.commit()
            logger.info(f"Login SUCCESS user={username} ip={client_ip}")
            next_page = request.args.get("next")
            if not is_safe_redirect_url(next_page):
                next_page = None
            return redirect(next_page or url_for("dashboard.dashboard"))

        logger.warning(f"Login FAILED user={username} ip={client_ip}")
        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    log_audit(current_user.id, "logout")
    db.session.commit()
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_user.check_password(current_password):
            return render_template("change_password.html", error="Current password is incorrect")

        if len(new_password) < 12:
            return render_template("change_password.html", error="New password must be at least 12 characters")

        if new_password != confirm_password:
            return render_template("change_password.html", error="New passwords do not match")

        current_user.set_password(new_password)
        db.session.commit()
        logger.info(f"Password changed for user {current_user.username}")
        return render_template("change_password.html", success="Password changed successfully")

    return render_template("change_password.html")

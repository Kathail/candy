import logging
from datetime import datetime, timezone

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import db, limiter
from app.helpers import is_safe_redirect_url
from app.models import User

logger = logging.getLogger(__name__)
bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10/minute")
def login():
    """Login page. GET renders form, POST authenticates."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))

    if request.method != "POST":
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        return render_template("login.html", error="Username and password required")

    # Single DB query
    try:
        user = db.session.execute(
            db.select(User).filter_by(username=username)
        ).scalar_one_or_none()
    except Exception as e:
        logger.error(f"Login DB error: {e}")
        db.session.rollback()
        return render_template("login.html", error="Something went wrong. Try again.")

    if not user or not user.check_password(password):
        logger.warning(f"Login FAILED user={username} ip={request.remote_addr}")
        return render_template("login.html", error="Invalid username or password")

    # Check if deactivated (safe if column doesn't exist)
    try:
        if not user.is_active_user:
            return render_template("login.html", error="Account is deactivated. Contact an admin.")
    except AttributeError:
        pass

    # Update last_login (non-blocking — don't fail login if this errors)
    try:
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()
    except Exception:
        db.session.rollback()

    login_user(user, remember=bool(request.form.get("remember")))
    logger.info(f"Login OK user={username}")

    next_page = request.args.get("next")
    if not is_safe_redirect_url(next_page):
        next_page = None
    return redirect(next_page or url_for("dashboard.dashboard"))


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method != "POST":
        return render_template("change_password.html")

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
    return render_template("change_password.html", success="Password changed successfully")

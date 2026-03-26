import logging

from flask import Blueprint, flash, redirect, request, url_for
from flask_login import current_user, login_required

from app import db, limiter
from app.helpers import admin_required, log_audit
from app.models import ActivityLog, Customer, Payment, RouteStop

logger = logging.getLogger(__name__)
bp = Blueprint("danger", __name__, url_prefix="/danger")
danger_limit = limiter.shared_limit("5/minute", scope="danger")


def _require_confirm():
    if request.form.get("confirm") != "CONFIRM":
        flash("You must type CONFIRM to proceed.", "error")
        return True
    return False


@bp.route("/clear-payments", methods=["POST"])
@danger_limit
@login_required
@admin_required
def clear_payments():
    if _require_confirm():
        return redirect(url_for("admin.admin_users"))

    with db.session.no_autoflush:
        payment_count = Payment.query.count()
        Payment.query.delete()
        Customer.query.update({Customer.balance: 0})
        db.session.commit()

    log_audit(current_user.id, "clear_payments", f"Cleared {payment_count} payments")
    db.session.commit()
    logger.warning(f"DANGER: {current_user.username} cleared all payments ({payment_count} records)")
    flash(f"Cleared {payment_count} payments and reset all customer balances to $0.", "success")
    return redirect(url_for("admin.admin_users"))


@bp.route("/clear-routes", methods=["POST"])
@danger_limit
@login_required
@admin_required
def clear_routes():
    if _require_confirm():
        return redirect(url_for("admin.admin_users"))

    route_count = RouteStop.query.count()
    RouteStop.query.delete()
    db.session.commit()

    log_audit(current_user.id, "clear_routes", f"Cleared {route_count} route stops")
    db.session.commit()
    logger.warning(f"DANGER: {current_user.username} cleared all route history ({route_count} records)")
    flash(f"Cleared {route_count} route stops.", "success")
    return redirect(url_for("admin.admin_users"))


@bp.route("/clear-customers", methods=["POST"])
@danger_limit
@login_required
@admin_required
def clear_customers():
    if _require_confirm():
        return redirect(url_for("admin.admin_users"))

    counts = {
        "activities": ActivityLog.query.delete(),
        "routes": RouteStop.query.delete(),
        "payments": Payment.query.delete(),
        "customers": Customer.query.delete(),
    }
    db.session.commit()

    log_audit(current_user.id, "clear_customers", f"Cleared {counts['customers']} customers and related data")
    db.session.commit()
    logger.warning(f"DANGER: {current_user.username} cleared all customers {counts}")
    flash(f"Cleared {counts['customers']} customers, {counts['payments']} payments, "
          f"{counts['routes']} routes, {counts['activities']} activity logs.", "success")
    return redirect(url_for("admin.admin_users"))


@bp.route("/clear-everything", methods=["POST"])
@danger_limit
@login_required
@admin_required
def clear_everything():
    if _require_confirm():
        return redirect(url_for("admin.admin_users"))

    counts = {
        "activities": ActivityLog.query.delete(),
        "routes": RouteStop.query.delete(),
        "payments": Payment.query.delete(),
        "customers": Customer.query.delete(),
    }
    db.session.commit()
    total = sum(counts.values())

    log_audit(current_user.id, "clear_everything", f"Full reset: {total} records cleared")
    db.session.commit()
    logger.warning(f"DANGER: {current_user.username} cleared EVERYTHING ({total} records, users preserved)")
    flash(f"Full reset: {total} records cleared. User accounts preserved.", "success")
    return redirect(url_for("admin.admin_users"))

import logging

from flask import Blueprint, flash, redirect, request, url_for
from flask_login import current_user, login_required

from app import db, limiter
from app.helpers import admin_required
from app.models import ActivityLog, Customer, Payment, RouteStop

logger = logging.getLogger(__name__)
bp = Blueprint("danger", __name__, url_prefix="/danger")
danger_limit = limiter.shared_limit("5/minute", scope="danger")


@bp.route("/clear-payments", methods=["POST"])
@danger_limit
@login_required
@admin_required
def clear_payments():
    if request.form.get("confirm") != "CONFIRM":
        flash("You must type CONFIRM to proceed.", "error")
        return redirect(url_for("admin.admin_users"))

    with db.session.no_autoflush:
        payment_count = Payment.query.count()
        Payment.query.delete()
        Customer.query.update({Customer.balance: 0})
        db.session.commit()

    logger.warning(f"DANGER: {current_user.username} cleared all payments ({payment_count} records)")
    flash(f"Cleared {payment_count} payments and reset all customer balances to $0.", "success")
    return redirect(url_for("admin.admin_users"))


@bp.route("/clear-routes", methods=["POST"])
@danger_limit
@login_required
@admin_required
def clear_routes():
    if request.form.get("confirm") != "CONFIRM":
        flash("You must type CONFIRM to proceed.", "error")
        return redirect(url_for("admin.admin_users"))

    route_count = RouteStop.query.count()
    RouteStop.query.delete()
    db.session.commit()

    logger.warning(f"DANGER: {current_user.username} cleared all route history ({route_count} records)")
    flash(f"Cleared {route_count} route stops.", "success")
    return redirect(url_for("admin.admin_users"))


@bp.route("/clear-customers", methods=["POST"])
@danger_limit
@login_required
@admin_required
def clear_customers():
    if request.form.get("confirm") != "CONFIRM":
        flash("You must type CONFIRM to proceed.", "error")
        return redirect(url_for("admin.admin_users"))

    activity_count = ActivityLog.query.count()
    route_count = RouteStop.query.count()
    payment_count = Payment.query.count()
    customer_count = Customer.query.count()

    ActivityLog.query.delete()
    RouteStop.query.delete()
    Payment.query.delete()
    Customer.query.delete()
    db.session.commit()

    total = activity_count + route_count + payment_count + customer_count
    logger.warning(f"DANGER: {current_user.username} cleared all customers ({customer_count} customers, {payment_count} payments, {route_count} routes, {activity_count} activities)")
    flash(f"Cleared {customer_count} customers, {payment_count} payments, {route_count} routes, {activity_count} activity logs ({total} total records).", "success")
    return redirect(url_for("admin.admin_users"))


@bp.route("/clear-everything", methods=["POST"])
@danger_limit
@login_required
@admin_required
def clear_everything():
    if request.form.get("confirm") != "CONFIRM":
        flash("You must type CONFIRM to proceed.", "error")
        return redirect(url_for("admin.admin_users"))

    activity_count = ActivityLog.query.count()
    route_count = RouteStop.query.count()
    payment_count = Payment.query.count()
    customer_count = Customer.query.count()

    ActivityLog.query.delete()
    RouteStop.query.delete()
    Payment.query.delete()
    Customer.query.delete()
    db.session.commit()

    total = activity_count + route_count + payment_count + customer_count
    logger.warning(f"DANGER: {current_user.username} cleared EVERYTHING ({total} total records, users preserved)")
    flash(f"Full reset: cleared {customer_count} customers, {payment_count} payments, {route_count} routes, {activity_count} activity logs. User accounts preserved.", "success")
    return redirect(url_for("admin.admin_users"))

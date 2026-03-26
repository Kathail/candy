import logging
import math
from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.helpers import admin_required, is_safe_redirect_url
from app.models import ActivityLog, Customer, Payment, RouteStop

logger = logging.getLogger(__name__)
bp = Blueprint("customers", __name__)


@bp.route("/customers")
@login_required
def customers():
    query = request.args.get("query", "")
    filter_type = request.args.get("filter", "")
    status_filter = request.args.get("status", "active")
    sort_by = request.args.get("sort", "name")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 50

    # Single query for all stats
    thirty_days_ago = datetime.now(timezone.utc).date() - timedelta(days=30)
    stats = db.session.query(
        db.func.count(Customer.id).filter(Customer.status == 'active'),
        db.func.count(Customer.id).filter(Customer.balance > 0, Customer.status == 'active'),
        db.func.count(Customer.id).filter(Customer.last_visit == None, Customer.status == 'active'),
        db.func.count(Customer.id).filter(
            Customer.last_visit != None, Customer.last_visit < thirty_days_ago, Customer.status == 'active'
        ),
    ).first()
    total_customers, customers_with_balance, never_visited, needs_visit = stats

    # Build filtered query - apply status filter
    if status_filter == "all":
        customers_query = Customer.query
    elif status_filter == "inactive":
        customers_query = Customer.query.filter_by(status='inactive')
    else:
        customers_query = Customer.query.filter_by(status='active')

    if query:
        customers_query = customers_query.filter(
            db.or_(
                Customer.name.ilike(f"%{query}%"),
                Customer.city.ilike(f"%{query}%"),
                Customer.notes.ilike(f"%{query}%"),
            )
        )

    if filter_type == "never":
        customers_query = customers_query.filter(Customer.last_visit == None)
    elif filter_type == "30":
        customers_query = customers_query.filter(Customer.last_visit < thirty_days_ago)
    elif filter_type == "60":
        customers_query = customers_query.filter(
            Customer.last_visit < datetime.now(timezone.utc).date() - timedelta(days=60)
        )

    # Apply sorting
    if sort_by == "name":
        customers_query = customers_query.order_by(Customer.name)
    elif sort_by == "city":
        customers_query = customers_query.order_by(Customer.city, Customer.name)
    elif sort_by == "balance_high":
        customers_query = customers_query.order_by(Customer.balance.desc())
    elif sort_by == "balance_low":
        customers_query = customers_query.order_by(Customer.balance)
    elif sort_by == "last_visit_recent":
        customers_query = customers_query.order_by(
            Customer.last_visit.desc().nullslast()
        )
    elif sort_by == "last_visit_oldest":
        customers_query = customers_query.order_by(Customer.last_visit.nullsfirst())
    else:
        customers_query = customers_query.order_by(Customer.name)

    # Paginate
    pagination = customers_query.paginate(page=page, per_page=per_page, error_out=False)
    customers_list = pagination.items

    # Return partial for HTMX requests (search/filter/sort)
    if request.headers.get("HX-Request"):
        return render_template(
            "partials/customers_table_rows.html",
            customers=customers_list,
            now=datetime.now(timezone.utc).date(),
        )

    return render_template(
        "customers.html",
        customers=customers_list,
        pagination=pagination,
        total_customers=total_customers,
        customers_with_balance=customers_with_balance,
        never_visited=never_visited,
        needs_visit=needs_visit,
        now=datetime.now(timezone.utc).date(),
    )


@bp.route("/api/customers/search")
@login_required
def api_customer_search():
    """Quick customer search API for global search feature"""
    query = request.args.get("q", "").strip()
    if not query or len(query) < 2:
        return jsonify([])

    results = Customer.query.filter(
        Customer.status == 'active',
        db.or_(
            Customer.name.ilike(f"%{query}%"),
            Customer.city.ilike(f"%{query}%"),
            Customer.phone.ilike(f"%{query}%"),
        )
    ).order_by(Customer.name).limit(8).all()

    return jsonify([{
        "id": c.id,
        "name": c.name,
        "city": c.city or "",
        "phone": c.phone or "",
        "balance": float(c.balance),
    } for c in results])


@bp.route("/customers/<int:customer_id>")
@login_required
def customer_details(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    now = datetime.now(timezone.utc).date()

    if request.headers.get("HX-Request"):
        return render_template(
            "partials/customer_details.html",
            customer=customer,
            now=now,
        )
    else:
        return render_template(
            "customer_profile.html",
            customer=customer,
            now=now,
        )


@bp.route("/customers/<int:customer_id>/edit")
@login_required
def customer_edit(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    return render_template(
        "partials/customer_edit_modal.html",
        customer=customer,
        now=datetime.now(timezone.utc),
    )


@bp.route("/customers/add", methods=["POST"])
@login_required
def customer_add():
    name = request.form.get("name")
    phone = request.form.get("phone")
    address = request.form.get("address")
    city = request.form.get("city")
    notes = request.form.get("notes")

    if not name:
        return "Name is required", 400

    new_customer = Customer(
        name=name,
        phone=phone or None,
        address=address or None,
        city=city or None,
        notes=notes or None,
        balance=0.0,
    )

    db.session.add(new_customer)
    db.session.flush()
    activity = ActivityLog(
        customer_id=new_customer.id,
        action="created",
        description="Customer created"
    )
    db.session.add(activity)
    db.session.commit()
    logger.info(f"Customer added: {name}")

    return redirect(url_for("customers.customers"))


@bp.route("/customers/<int:customer_id>/update", methods=["POST"])
@login_required
def customer_update(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    customer.name = request.form.get("name") or customer.name
    customer.phone = request.form.get("phone") or None
    customer.address = request.form.get("address") or None
    customer.city = request.form.get("city") or None
    customer.notes = request.form.get("notes") or None

    balance_str = request.form.get("balance")
    if balance_str:
        try:
            balance_value = float(balance_str)
            if balance_value < 0:
                return "Balance cannot be negative", 400
            customer.balance = balance_value
        except ValueError:
            return "Invalid balance value", 400

    customer.tax_exempt = request.form.get("tax_exempt") == "on"

    db.session.commit()
    logger.info(f"Customer updated: {customer.name}")

    redirect_to = request.form.get("redirect_to")
    if not is_safe_redirect_url(redirect_to):
        redirect_to = url_for("customers.customers")
    return redirect(redirect_to)


@bp.route("/customers/<int:customer_id>/delete", methods=["POST"])
@login_required
@admin_required
def customer_delete(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer_name = customer.name

    # Delete related records first
    RouteStop.query.filter_by(customer_id=customer_id).delete()
    Payment.query.filter_by(customer_id=customer_id).delete()
    ActivityLog.query.filter_by(customer_id=customer_id).delete()

    db.session.delete(customer)
    db.session.commit()
    logger.info(f"Customer deleted: {customer_name}")

    return redirect(url_for("customers.customers"))


@bp.route("/customers/<int:customer_id>/archive", methods=["POST"])
@login_required
def customer_archive(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.status = 'inactive'
    db.session.commit()
    logger.info(f"Customer archived: {customer.name}")
    return redirect(url_for("customers.customers"))


@bp.route("/customers/<int:customer_id>/reactivate", methods=["POST"])
@login_required
def customer_reactivate(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.status = 'active'
    db.session.commit()
    logger.info(f"Customer reactivated: {customer.name}")
    return redirect(url_for("customers.customers", status="inactive"))


@bp.route("/customers/<int:customer_id>/add-payment", methods=["POST"])
@login_required
def customer_add_payment(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    try:
        amount = float(request.form.get("amount", 0))
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Amount must be a positive number")
    except (ValueError, TypeError):
        flash("Invalid payment amount", "error")
        return redirect(url_for("customers.customer_details", customer_id=customer.id))
    payment_date_str = request.form.get("payment_date")
    notes = request.form.get("notes", "").strip()

    if payment_date_str:
        try:
            payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format", "error")
            return redirect(url_for("customers.customer_details", customer_id=customer.id))
    else:
        payment_date = datetime.now(timezone.utc).date()

    payment = Payment(
        customer_id=customer.id,
        amount=amount,
        payment_date=payment_date,
        notes=notes if notes else None,
        previous_balance=customer.balance,
    )

    customer.balance = max(0, customer.balance - amount)

    db.session.add(payment)
    activity = ActivityLog(
        customer_id=customer.id,
        action="payment",
        description=f"Payment of ${amount:.2f} recorded"
    )
    db.session.add(activity)
    db.session.commit()

    logger.info(f"Payment recorded for {customer.name}: ${amount:.2f}")
    flash(f"Payment of ${amount:.2f} recorded", "success")

    redirect_to = request.form.get("redirect_to")
    if is_safe_redirect_url(redirect_to):
        return redirect(redirect_to)
    return redirect(url_for("customers.customer_details", customer_id=customer.id))


@bp.route("/customers/<int:customer_id>/delete-payment/<int:payment_id>", methods=["POST"])
@login_required
@admin_required
def customer_delete_payment(customer_id, payment_id):
    customer = Customer.query.get_or_404(customer_id)
    payment = Payment.query.get_or_404(payment_id)

    if payment.customer_id != customer_id:
        flash("Invalid payment", "error")
        return redirect(url_for("customers.customers"))

    customer.balance += payment.amount

    db.session.delete(payment)
    db.session.commit()

    logger.info(f"Payment deleted for {customer.name}: ${payment.amount:.2f}")
    flash(f"Payment of ${payment.amount:.2f} deleted", "success")

    return redirect(url_for("customers.customer_details", customer_id=customer.id))


@bp.route("/customers/<int:customer_id>/activity")
@login_required
def customer_activity(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    activities = (
        ActivityLog.query
        .filter_by(customer_id=customer_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template(
        "partials/activity.html",
        customer=customer,
        activities=activities,
    )

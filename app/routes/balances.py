import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.helpers import is_safe_redirect_url
from app.models import ActivityLog, Customer, Payment

logger = logging.getLogger(__name__)
bp = Blueprint("balances", __name__)


@bp.route("/balances")
@login_required
def balances():
    query = request.args.get("query", "")
    sort_type = request.args.get("sort", "balance_desc")

    balances_query = Customer.query.filter(Customer.balance > 0, Customer.status == 'active')

    if query:
        balances_query = balances_query.filter(
            db.or_(Customer.name.ilike(f"%{query}%"), Customer.city.ilike(f"%{query}%"))
        )

    # Apply sorting
    if sort_type == "balance_asc":
        balances_query = balances_query.order_by(Customer.balance.asc())
    elif sort_type == "name":
        balances_query = balances_query.order_by(Customer.name.asc())
    elif sort_type == "visit":
        balances_query = balances_query.order_by(Customer.last_visit.asc().nullsfirst())
    else:  # balance_desc (default)
        balances_query = balances_query.order_by(Customer.balance.desc())

    # Calculate stats using SQL aggregation (before pagination)
    stats = db.session.query(
        db.func.sum(Customer.balance),
        db.func.avg(Customer.balance),
        db.func.max(Customer.balance),
        db.func.count(Customer.id),
    ).filter(Customer.balance > 0, Customer.status == 'active').first()

    total_owed = (stats[0] or 0) if stats else 0
    avg_balance = (stats[1] or 0) if stats else 0
    highest_balance = (stats[2] or 0) if stats else 0

    # Compute aging buckets based on last payment date
    today = datetime.now(timezone.utc).date()
    all_with_balance = Customer.query.filter(Customer.balance > 0, Customer.status == 'active').all()
    aging_buckets = {"0_30": 0, "31_60": 0, "61_90": 0, "90_plus": 0, "never": 0}
    aging_amounts = {"0_30": 0.0, "31_60": 0.0, "61_90": 0.0, "90_plus": 0.0, "never": 0.0}
    for c in all_with_balance:
        last_payment = max(c.payments, key=lambda p: p.payment_date, default=None) if c.payments else None
        if last_payment is None:
            aging_buckets["never"] += 1
            aging_amounts["never"] += float(c.balance)
        else:
            days = (today - last_payment.payment_date).days
            if days <= 30:
                aging_buckets["0_30"] += 1
                aging_amounts["0_30"] += float(c.balance)
            elif days <= 60:
                aging_buckets["31_60"] += 1
                aging_amounts["31_60"] += float(c.balance)
            elif days <= 90:
                aging_buckets["61_90"] += 1
                aging_amounts["61_90"] += float(c.balance)
            else:
                aging_buckets["90_plus"] += 1
                aging_amounts["90_plus"] += float(c.balance)

    # Paginate results
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 50
    pagination = balances_query.paginate(page=page, per_page=per_page, error_out=False)
    balances_list = pagination.items

    return render_template(
        "balances.html",
        balances=balances_list,
        pagination=pagination,
        total_owed=f"{total_owed:.2f}",
        avg_balance=f"{avg_balance:.2f}",
        highest_balance=f"{highest_balance:.2f}",
        now=today,
        aging_buckets=aging_buckets,
        aging_amounts=aging_amounts,
    )


@bp.route("/balances/<int:balance_id>")
@login_required
def balance_details(balance_id):
    customer = Customer.query.get_or_404(balance_id)
    return render_template(
        "partials/balance_details.html",
        customer=customer,
        now=datetime.now(timezone.utc).date(),
    )


@bp.route("/balances/record-payment", methods=["POST"])
@login_required
def record_payment():
    customer_id = request.form.get("customer_id")
    amount_str = request.form.get("amount")
    payment_date_str = request.form.get("payment_date")
    notes = request.form.get("notes")

    if not customer_id or not amount_str:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        customer = Customer.query.get_or_404(int(customer_id))
        amount = float(amount_str)

        if amount <= 0:
            return jsonify({"error": "Amount must be positive"}), 400

        # Parse payment date
        if payment_date_str:
            payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()
        else:
            payment_date = datetime.now(timezone.utc).date()

        # Store previous balance before updating
        previous_balance = customer.balance

        # Generate receipt number (format: RCP-YYYYMMDD-XXXX)
        today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        max_receipt = db.session.query(db.func.max(Payment.receipt_number)).filter(
            Payment.receipt_number.like(f"RCP-{today_str}-%")
        ).scalar()
        next_seq = int(max_receipt.split("-")[-1]) + 1 if max_receipt else 1
        receipt_number = f"RCP-{today_str}-{next_seq:04d}"

        # Create payment record with receipt info
        new_payment = Payment(
            customer_id=customer.id,
            amount=amount,
            payment_date=payment_date,
            notes=notes or None,
            receipt_number=receipt_number,
            previous_balance=previous_balance,
        )

        # Update customer balance
        customer.balance = max(0, customer.balance - amount)

        db.session.add(new_payment)
        activity = ActivityLog(
            customer_id=customer.id,
            action="payment",
            description=f"Payment of ${amount:.2f} recorded (Receipt: {receipt_number})"
        )
        db.session.add(activity)
        db.session.commit()
        logger.info(f"Payment recorded: ${amount} from {customer.name} (Receipt: {receipt_number})")
        flash(f"Payment of ${amount:.2f} recorded for {customer.name}", "success")

        # Redirect back to where the user came from
        redirect_to = request.form.get("redirect_to")
        if is_safe_redirect_url(redirect_to):
            return redirect(redirect_to)
        referrer = request.referrer
        if referrer and is_safe_redirect_url(urlparse(referrer).path):
            return redirect(referrer)
        return redirect(url_for("balances.balances"))
    except ValueError:
        return jsonify({"error": "Invalid amount value"}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error recording payment: {str(e)}")
        return jsonify({"error": "Error recording payment"}), 500

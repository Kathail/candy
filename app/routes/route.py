import io
import logging
import math
import zipfile
from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.helpers import generate_receipt_pdf
from app.models import ActivityLog, Customer, Payment, RouteStop

logger = logging.getLogger(__name__)
bp = Blueprint("route", __name__)


@bp.route("/route")
@login_required
def route():
    today = datetime.now(timezone.utc).date()
    stops = (
        RouteStop.query.options(db.joinedload(RouteStop.customer))
        .filter_by(route_date=today).order_by(RouteStop.sequence).all()
    )

    completed = sum(1 for s in stops if s.completed)
    total = len(stops)
    outstanding_balance = sum(float(s.customer.balance) for s in stops)

    collected_today = db.session.query(
        db.func.sum(Payment.amount)
    ).filter(Payment.payment_date == today).scalar() or 0

    cities = set(s.customer.city for s in stops if s.customer.city)
    num_cities = len(cities)
    travel_between_cities = max(0, num_cities - 1) * 15
    time_at_stops = total * 10
    total_est_minutes = time_at_stops + travel_between_cities
    est_hours = total_est_minutes // 60
    est_minutes = total_est_minutes % 60
    stops_with_balance = sum(1 for s in stops if s.customer.balance > 0)

    return render_template(
        "route.html",
        completed=completed,
        total=total,
        stops=stops,
        outstanding_balance=f"{outstanding_balance:.2f}",
        collected_today=f"{collected_today:.2f}",
        now=datetime.now(timezone.utc).date(),
        num_cities=num_cities,
        est_hours=est_hours,
        est_minutes=est_minutes,
        total_est_minutes=total_est_minutes,
        stops_with_balance=stops_with_balance,
    )


@bp.route("/route/stop/<int:stop_id>")
@login_required
def route_stop_details(stop_id):
    stop = RouteStop.query.options(db.joinedload(RouteStop.customer)).get_or_404(stop_id)
    return render_template("partials/stop_details.html", stop=stop)


@bp.route("/route/stop/<int:stop_id>/complete", methods=["POST"])
@login_required
def complete_stop(stop_id):
    stop = RouteStop.query.get_or_404(stop_id)
    stop.completed = True
    stop.customer.last_visit = datetime.now(timezone.utc).date()
    notes = request.form.get("notes", "").strip()
    if notes:
        stop.notes = notes
    activity = ActivityLog(
        customer_id=stop.customer.id,
        action="visited",
        description=f"Route stop completed" + (f": {notes}" if notes else "")
    )
    db.session.add(activity)
    db.session.commit()
    logger.info(f"Stop {stop_id} completed for customer {stop.customer.name}")
    return render_template("partials/stop_details.html", stop=stop)


@bp.route("/route/stop/<int:stop_id>/uncomplete", methods=["POST"])
@login_required
def uncomplete_stop(stop_id):
    stop = RouteStop.query.get_or_404(stop_id)
    stop.completed = False
    db.session.commit()
    return render_template("partials/stop_details.html", stop=stop)


@bp.route("/route/stop/<int:stop_id>/payment", methods=["POST"])
@login_required
def stop_payment(stop_id):
    stop = RouteStop.query.get_or_404(stop_id)
    try:
        amount = float(request.form.get("amount", 0))
        if not math.isfinite(amount):
            amount = 0
    except (ValueError, TypeError):
        amount = 0
    if amount > 0:
        payment = Payment(
            customer_id=stop.customer.id,
            amount=amount,
            payment_date=datetime.now(timezone.utc).date(),
            notes="Collected on route"
        )
        db.session.add(payment)
        stop.customer.balance = max(0, stop.customer.balance - amount)
        activity = ActivityLog(
            customer_id=stop.customer.id,
            action="payment",
            description=f"Payment of ${amount:.2f} collected on route"
        )
        db.session.add(activity)
        db.session.commit()
        logger.info(f"Payment of ${amount:.2f} recorded for {stop.customer.name} on route")
    return render_template("partials/stop_details.html", stop=stop)


@bp.route("/route/quick-add-customer", methods=["POST"])
@login_required
def route_quick_add_customer():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Customer name is required.", "error")
        return redirect(url_for("route.route"))

    city = request.form.get("city", "").strip() or None
    phone = request.form.get("phone", "").strip() or None

    customer = Customer(name=name, city=city, phone=phone)
    db.session.add(customer)
    db.session.flush()

    today = datetime.now(timezone.utc).date()
    max_seq = db.session.query(db.func.max(RouteStop.sequence)).filter_by(route_date=today).scalar() or 0
    stop = RouteStop(
        customer_id=customer.id,
        route_date=today,
        sequence=max_seq + 1,
        completed=False,
    )
    db.session.add(stop)
    db.session.commit()
    logger.info(f"Quick-added customer '{name}' and added to today's route as stop #{max_seq + 1}")
    flash(f"Added {name} to today's route.", "success")
    return redirect(url_for("route.route"))


@bp.route("/route/receipts-zip")
@login_required
def route_receipts_zip():
    date_str = request.args.get("date")
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            target_date = datetime.now(timezone.utc).date()
    else:
        target_date = datetime.now(timezone.utc).date()

    payments = Payment.query.options(
        db.joinedload(Payment.customer)
    ).filter_by(payment_date=target_date).all()

    if not payments:
        flash("No receipts found for this date.", "error")
        return redirect(url_for("route.route"))

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for payment in payments:
            pdf_buffer = generate_receipt_pdf(payment)
            filename = f"receipt_{payment.receipt_number or payment.id}.pdf"
            zf.writestr(filename, pdf_buffer.read())

    zip_buffer.seek(0)
    return Response(
        zip_buffer.read(),
        mimetype="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=receipts_{target_date.isoformat()}.zip"
        },
    )


@bp.route("/route/summary")
@login_required
def route_summary():
    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)

    stops = (
        RouteStop.query.options(db.joinedload(RouteStop.customer))
        .filter_by(route_date=today).order_by(RouteStop.sequence).all()
    )

    completed_stops = [s for s in stops if s.completed]
    skipped_stops = [s for s in stops if not s.completed]
    completed = len(completed_stops)
    total = len(stops)

    collected_today = db.session.query(
        db.func.sum(Payment.amount)
    ).filter(Payment.payment_date == today).scalar() or 0

    outstanding_balance = sum(float(s.customer.balance) for s in stops)

    tomorrow_stops = (
        RouteStop.query.options(db.joinedload(RouteStop.customer))
        .filter_by(route_date=tomorrow).order_by(RouteStop.sequence).all()
    )

    return render_template(
        "route_summary.html",
        today=today,
        completed=completed,
        total=total,
        completed_stops=completed_stops,
        skipped_stops=skipped_stops,
        collected_today=f"{collected_today:.2f}",
        outstanding_balance=f"{outstanding_balance:.2f}",
        tomorrow_stops=tomorrow_stops,
    )


@bp.route("/offline")
def offline():
    return render_template("errors/offline.html")


@bp.route("/sw.js")
def service_worker():
    from flask import current_app
    response = current_app.send_static_file("sw.js")
    response.headers["Content-Type"] = "application/javascript"
    response.headers["Cache-Control"] = "no-cache"
    return response


@bp.route("/receipts/<int:payment_id>/pdf")
@login_required
def download_receipt(payment_id):
    """Download PDF receipt for a payment"""
    payment = Payment.query.options(
        db.joinedload(Payment.customer)
    ).get_or_404(payment_id)

    pdf_buffer = generate_receipt_pdf(payment)

    filename = f"receipt_{payment.receipt_number or payment_id}.pdf"
    return Response(
        pdf_buffer.getvalue(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

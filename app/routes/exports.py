import csv
import io
from datetime import datetime, timezone

from flask import Blueprint, Response, request
from flask_login import login_required

from app import db
from app.models import Customer, Payment, RouteStop

bp = Blueprint("exports", __name__)


@bp.route("/export/customers")
@login_required
def export_customers():
    """Export all customers as CSV"""
    customers_list = Customer.query.order_by(Customer.name).all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "Name", "City", "Address", "Phone", "Notes",
        "Balance", "Last Visit", "Created At"
    ])

    for c in customers_list:
        writer.writerow([
            c.id,
            c.name,
            c.city or "",
            c.address or "",
            c.phone or "",
            c.notes or "",
            f"{c.balance:.2f}",
            c.last_visit.strftime("%Y-%m-%d") if c.last_visit else "",
            c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else ""
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=\"customers_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv\""
        }
    )


@bp.route("/export/payments")
@login_required
def export_payments():
    """Export all payments as CSV"""
    payments_list = Payment.query.options(
        db.joinedload(Payment.customer)
    ).order_by(Payment.payment_date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "Receipt Number", "Customer Name", "Customer City",
        "Amount", "Previous Balance", "Payment Date", "Notes"
    ])

    for p in payments_list:
        writer.writerow([
            p.id,
            p.receipt_number or "",
            p.customer.name if p.customer else "",
            p.customer.city if p.customer else "",
            f"{p.amount:.2f}",
            f"{p.previous_balance:.2f}" if p.previous_balance is not None else "",
            p.payment_date.strftime("%Y-%m-%d"),
            p.notes or ""
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=\"payments_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv\""
        }
    )


@bp.route("/export/routes")
@login_required
def export_routes():
    """Export route history as CSV with optional date filter"""
    start_date = request.args.get("start")
    end_date = request.args.get("end")

    query = RouteStop.query.options(
        db.joinedload(RouteStop.customer)
    ).order_by(RouteStop.route_date.desc(), RouteStop.sequence)

    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            query = query.filter(RouteStop.route_date >= start)
        except ValueError:
            pass

    if end_date:
        try:
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(RouteStop.route_date <= end)
        except ValueError:
            pass

    stops_list = query.all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "ID", "Route Date", "Sequence", "Customer Name", "Customer City",
        "Completed", "Notes"
    ])

    for s in stops_list:
        writer.writerow([
            s.id,
            s.route_date.strftime("%Y-%m-%d"),
            s.sequence,
            s.customer.name if s.customer else "",
            s.customer.city if s.customer else "",
            "Yes" if s.completed else "No",
            s.notes or ""
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=\"routes_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv\""
        }
    )

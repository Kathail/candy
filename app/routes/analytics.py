import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, request
from flask_login import login_required

from app import db
from app.models import Customer, Payment, RouteStop

bp = Blueprint("analytics", __name__)


@bp.route("/analytics")
@login_required
def analytics():

    # Get date range from query params
    date_range = request.args.get("range", "30")
    today = datetime.now(timezone.utc).date()

    if date_range == "7":
        start_date = today - timedelta(days=7)
        range_label = "Last 7 Days"
    elif date_range == "30":
        start_date = today - timedelta(days=30)
        range_label = "Last 30 Days"
    elif date_range == "90":
        start_date = today - timedelta(days=90)
        range_label = "Last 90 Days"
    elif date_range == "365":
        start_date = today - timedelta(days=365)
        range_label = "This Year"
    else:
        start_date = None
        range_label = "All Time"

    # Get counts and aggregations efficiently (active customers)
    total_customers = Customer.query.filter_by(status='active').count()

    # Use eager loading for payments to avoid N+1
    payments_query = Payment.query.options(db.joinedload(Payment.customer))
    stops_query = RouteStop.query

    if start_date:
        payments_query = payments_query.filter(Payment.payment_date >= start_date)
        stops_query = stops_query.filter(RouteStop.route_date >= start_date)

    all_payments = payments_query.all()
    all_stops = stops_query.all()

    # Key metrics using SQL aggregation where possible
    collected_query = db.session.query(db.func.sum(Payment.amount))
    if start_date:
        collected_query = collected_query.filter(Payment.payment_date >= start_date)
    total_collected = collected_query.scalar() or 0

    outstanding_stats = db.session.query(
        db.func.sum(Customer.balance),
        db.func.count(Customer.id)
    ).filter(Customer.balance > 0, Customer.status == 'active').first()

    total_outstanding = (outstanding_stats[0] or 0) if outstanding_stats else 0
    outstanding_count = (outstanding_stats[1] or 0) if outstanding_stats else 0

    total_stops = len(all_stops)
    avg_per_stop = (total_collected / total_stops) if total_stops > 0 else 0

    completed_stops = sum(1 for s in all_stops if s.completed)
    visit_rate = int((completed_stops / total_stops * 100)) if total_stops > 0 else 0

    # Top customers by revenue - use the eager-loaded relationships
    customer_payments = defaultdict(
        lambda: {"total": 0, "count": 0, "name": "", "city": ""}
    )
    for payment in all_payments:
        if payment.customer:
            customer_payments[payment.customer_id]["total"] += float(payment.amount)
            customer_payments[payment.customer_id]["count"] += 1
            customer_payments[payment.customer_id]["name"] = payment.customer.name
            customer_payments[payment.customer_id]["city"] = payment.customer.city

    top_customers = [
        {
            "name": data["name"],
            "city": data["city"],
            "total_paid": data["total"],
            "payment_count": data["count"],
        }
        for cid, data in customer_payments.items()
    ]
    top_customers.sort(key=lambda x: x["total_paid"], reverse=True)

    # Recent activity (last 7 days)
    seven_days_ago = datetime.now(timezone.utc).date() - timedelta(days=7)
    thirty_days_ago = datetime.now(timezone.utc).date() - timedelta(days=30)

    completed_this_week = sum(
        1 for s in all_stops if s.completed and s.route_date >= seven_days_ago
    )
    payments_this_week = sum(
        1 for p in all_payments if p.payment_date >= seven_days_ago
    )

    # New customers count using efficient query (active only)
    new_customers = Customer.query.filter(
        Customer.created_at != None,
        Customer.created_at >= datetime.combine(thirty_days_ago, datetime.min.time(), tzinfo=timezone.utc),
        Customer.status == 'active'
    ).count()

    # City breakdown using efficient query (active customers only)
    city_counts = db.session.query(
        Customer.city,
        db.func.count(Customer.id)
    ).filter(Customer.city != None, Customer.status == 'active').group_by(Customer.city).all()

    cities = [{"name": city, "count": count} for city, count in city_counts]
    cities.sort(key=lambda x: x["count"], reverse=True)

    # Revenue over time (last 30 days)
    revenue_by_date = defaultdict(float)
    for payment in all_payments:
        if payment.payment_date >= thirty_days_ago:
            date_str = payment.payment_date.strftime("%m/%d")
            revenue_by_date[date_str] += float(payment.amount)

    # Fill in missing dates
    revenue_labels = []
    revenue_data = []
    for i in range(30):
        date = datetime.now(timezone.utc).date() - timedelta(days=29 - i)
        date_str = date.strftime("%m/%d")
        revenue_labels.append(date_str)
        revenue_data.append(float(revenue_by_date.get(date_str, 0)))

    # Customer distribution - use efficient queries (active customers)
    paid_up = Customer.query.filter(
        Customer.balance == 0,
        Customer.last_visit != None,
        Customer.status == 'active'
    ).count()
    with_balance = outstanding_count
    never_visited = Customer.query.filter(Customer.last_visit == None, Customer.status == 'active').count()
    customer_distribution = [paid_up, with_balance, never_visited]

    # Payment analysis
    total_payments = len(all_payments)
    avg_payment = (total_collected / total_payments) if total_payments > 0 else 0
    largest_payment = max((p.amount for p in all_payments), default=0)

    # Calculate collection rate (collected vs outstanding)
    total_potential = total_collected + total_outstanding
    collection_rate = (
        int((total_collected / total_potential * 100)) if total_potential > 0 else 100
    )

    # Route efficiency
    route_dates = set(s.route_date for s in all_stops)
    total_routes = len(route_dates)
    avg_stops_per_route = (total_stops / total_routes) if total_routes > 0 else 0
    completion_rate = visit_rate

    # Find busiest day
    day_counts = defaultdict(int)
    for stop in all_stops:
        day_name = stop.route_date.strftime("%A")
        day_counts[day_name] += 1
    busiest_day = (
        max(day_counts.items(), key=lambda x: x[1])[0] if day_counts else "N/A"
    )

    return render_template(
        "analytics.html",
        # Key metrics
        total_collected=f"{total_collected:.2f}",
        total_outstanding=f"{total_outstanding:.2f}",
        outstanding_count=outstanding_count,
        total_stops=total_stops,
        avg_per_stop=f"{avg_per_stop:.2f}",
        visit_rate=visit_rate,
        total_customers=total_customers,
        # Top performers
        top_customers=top_customers,
        # Recent activity
        completed_this_week=completed_this_week,
        payments_this_week=payments_this_week,
        new_customers=new_customers,
        # Location data
        cities=cities,
        # Charts data
        revenue_labels=json.dumps(revenue_labels),
        revenue_data=json.dumps(revenue_data),
        customer_distribution=json.dumps(customer_distribution),
        # Payment analysis
        total_payments=total_payments,
        avg_payment=f"{avg_payment:.2f}",
        largest_payment=f"{largest_payment:.2f}",
        collection_rate=collection_rate,
        # Route efficiency
        total_routes=total_routes,
        avg_stops_per_route=f"{avg_stops_per_route:.1f}",
        completion_rate=completion_rate,
        busiest_day=busiest_day,
        # Date range
        current_range=date_range,
        range_label=range_label,
    )

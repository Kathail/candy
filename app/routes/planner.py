import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from app import db
from app.models import Customer, Payment, RouteStop

logger = logging.getLogger(__name__)
bp = Blueprint("planner", __name__)


@bp.route("/planner")
@login_required
def planner():
    today = datetime.now(timezone.utc).date()

    # Get all customers not already scheduled in future
    future_stops = RouteStop.query.filter(RouteStop.route_date >= today).all()
    scheduled_customer_ids = [s.customer_id for s in future_stops]

    available_customers = (
        Customer.query.filter(
            Customer.status == 'active',
            ~Customer.id.in_(scheduled_customer_ids) if scheduled_customer_ids else db.true()
        )
        .order_by(Customer.name)
        .all()
    )

    # Calculate customers needing visit
    thirty_days_ago = today - timedelta(days=30)
    needs_visit = sum(
        1
        for c in available_customers
        if c.last_visit and c.last_visit < thirty_days_ago
    )

    # Get upcoming routes (next 7 days) — single query instead of 7
    week_start = today
    week_end_date = today + timedelta(days=7)
    all_upcoming_stops = (
        RouteStop.query
        .filter(RouteStop.route_date >= week_start, RouteStop.route_date < week_end_date)
        .order_by(RouteStop.route_date, RouteStop.sequence)
        .all()
    )
    stops_by_day = defaultdict(list)
    for stop in all_upcoming_stops:
        stops_by_day[stop.route_date].append(stop)

    upcoming_routes = []
    for i in range(7):
        check_date = today + timedelta(days=i)
        day_stops = stops_by_day.get(check_date, [])

        if day_stops or i == 0:  # Always show today
            upcoming_routes.append(
                {
                    "date": check_date.strftime("%Y-%m-%d"),
                    "date_formatted": check_date.strftime("%b %d, %Y"),
                    "day_name": check_date.strftime("%A"),
                    "stop_count": len(day_stops),
                    "first_customer": day_stops[0].customer.name if day_stops else None,
                }
            )

    # Calculate weekly stats (reuse already-fetched data)
    weekly_routes = len(stops_by_day)
    total_planned_stops = len(all_upcoming_stops)

    # Prepare customer data for Alpine.js
    customers_data = []
    for c in available_customers:
        days_since = (today - c.last_visit).days if c.last_visit else None
        customers_data.append(
            {
                "id": c.id,
                "name": c.name,
                "city": c.city or "",
                "balance": float(c.balance) if c.balance is not None else 0.0,
                "last_visit": c.last_visit.strftime("%b %d") if c.last_visit else None,
                "needs_visit": days_since > 30 if days_since else False,
            }
        )

    return render_template(
        "planner.html",
        customers=available_customers,
        customers_json=json.dumps(customers_data),
        upcoming_routes=upcoming_routes,
        weekly_routes=weekly_routes,
        total_planned_stops=total_planned_stops,
        needs_visit=needs_visit,
        now=today,
        timedelta=timedelta,
    )


@bp.route("/planner/date/<date_str>")
@login_required
def planner_date_details(date_str):
    try:
        route_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return "Invalid date format", 400

    stops = (
        RouteStop.query.filter_by(route_date=route_date)
        .order_by(RouteStop.sequence)
        .all()
    )

    return render_template(
        "partials/route_builder.html",
        stops=stops,
        route_date=date_str,
        date_formatted=route_date.strftime("%b %d, %Y"),
        day_name=route_date.strftime("%A"),
    )


@bp.route("/planner/add-stop", methods=["POST"])
@login_required
def add_stop_to_route():
    customer_id = request.form.get("customer_id")
    route_date_str = request.form.get("route_date")

    if not customer_id or not route_date_str:
        return jsonify({"success": False, "error": "Missing parameters"}), 400

    try:
        route_date = datetime.strptime(route_date_str, "%Y-%m-%d").date()
        customer = Customer.query.get_or_404(int(customer_id))

        max_seq = (
            db.session.query(db.func.max(RouteStop.sequence))
            .filter_by(route_date=route_date)
            .scalar()
            or 0
        )

        new_stop = RouteStop(
            customer_id=customer.id,
            route_date=route_date,
            sequence=max_seq + 1,
            completed=False,
        )

        db.session.add(new_stop)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "stop_id": new_stop.id,
                "customer_name": customer.name,
                "customer_city": customer.city,
            }
        )
    except Exception as e:
        logger.error(f"Error adding stop: {str(e)}")
        return jsonify({"success": False, "error": "Failed to add stop"}), 500


@bp.route("/planner/stop/<int:stop_id>/remove", methods=["POST"])
@login_required
def remove_stop_from_route(stop_id):
    stop = RouteStop.query.get_or_404(stop_id)

    db.session.delete(stop)
    db.session.commit()

    return jsonify({"success": True})


@bp.route("/planner/route/<route_date>/clear", methods=["POST"])
@login_required
def clear_route(route_date):
    try:
        date_obj = datetime.strptime(route_date, "%Y-%m-%d").date()
        RouteStop.query.filter_by(route_date=date_obj).delete()
        db.session.commit()

        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error clearing route: {str(e)}")
        return jsonify({"success": False, "error": "Failed to clear route"}), 500


@bp.route("/customer/<int:customer_id>/details")
@login_required
def get_customer_details(customer_id):
    """Get detailed customer information for modal"""
    customer = Customer.query.get_or_404(customer_id)

    payments = (
        Payment.query.filter_by(customer_id=customer_id)
        .order_by(Payment.payment_date.desc())
        .limit(10)
        .all()
    )

    visits = (
        RouteStop.query.filter_by(customer_id=customer_id)
        .order_by(RouteStop.route_date.desc())
        .limit(10)
        .all()
    )

    return jsonify(
        {
            "customer": {
                "id": customer.id,
                "name": customer.name,
                "address": customer.address,
                "city": customer.city,
                "phone": customer.phone,
                "notes": customer.notes,
                "balance": float(customer.balance),
                "last_visit": customer.last_visit.strftime("%Y-%m-%d")
                if customer.last_visit
                else None,
                "created_at": customer.created_at.strftime("%Y-%m-%d")
                if customer.created_at
                else None,
            },
            "payments": [
                {
                    "id": p.id,
                    "amount": float(p.amount),
                    "date": p.payment_date.strftime("%Y-%m-%d"),
                    "notes": p.notes,
                }
                for p in payments
            ],
            "visits": [
                {
                    "id": v.id,
                    "date": v.route_date.strftime("%Y-%m-%d"),
                    "completed": v.completed,
                }
                for v in visits
            ],
        }
    )


@bp.route("/planner/all-stops")
@login_required
def get_all_stops():
    """Return all stops grouped by date for the calendar"""
    today = datetime.now(timezone.utc).date()
    future_date = today + timedelta(days=60)

    stops = (
        RouteStop.query.filter(
            RouteStop.route_date >= today, RouteStop.route_date <= future_date
        )
        .order_by(RouteStop.sequence)
        .all()
    )

    stops_by_date = {}
    for stop in stops:
        date_str = stop.route_date.strftime("%Y-%m-%d")
        if date_str not in stops_by_date:
            stops_by_date[date_str] = []

        stops_by_date[date_str].append(
            {
                "id": stop.id,
                "customer_id": stop.customer_id,
                "customer_name": stop.customer.name,
                "customer_city": stop.customer.city,
                "sequence": stop.sequence,
            }
        )

    return jsonify({"stops": stops_by_date})


@bp.route("/planner/route/<route_date>/optimize", methods=["POST"])
@login_required
def optimize_route(route_date):
    """Optimize route using nearest-neighbor algorithm grouped by city"""
    try:
        date_obj = datetime.strptime(route_date, "%Y-%m-%d").date()
        stops = RouteStop.query.filter_by(route_date=date_obj).all()

        if len(stops) <= 1:
            return render_template(
                "partials/route_builder.html",
                stops=stops,
                route_date=route_date,
                date_formatted=date_obj.strftime("%b %d, %Y"),
                day_name=date_obj.strftime("%A"),
            )

        # Group stops by city
        city_groups = {}
        for stop in stops:
            city = stop.customer.city or "Unknown"
            if city not in city_groups:
                city_groups[city] = []
            city_groups[city].append(stop)

        # Sort cities by number of stops (visit cities with more stops first)
        sorted_cities = sorted(
            city_groups.items(), key=lambda x: len(x[1]), reverse=True
        )

        # Within each city, sort by customer name for consistency
        optimized_stops = []
        for city, city_stops in sorted_cities:
            sorted_city_stops = sorted(city_stops, key=lambda s: s.customer.name)
            optimized_stops.extend(sorted_city_stops)

        # Update sequences
        for idx, stop in enumerate(optimized_stops, start=1):
            stop.sequence = idx

        db.session.commit()

        # Reload stops in new order and return as JSON
        stops = (
            RouteStop.query.filter_by(route_date=date_obj)
            .order_by(RouteStop.sequence)
            .all()
        )

        stops_data = [
            {
                "id": stop.id,
                "customer_id": stop.customer_id,
                "customer_name": stop.customer.name,
                "customer_city": stop.customer.city,
                "sequence": stop.sequence,
            }
            for stop in stops
        ]

        return jsonify({"success": True, "stops": stops_data})
    except Exception as e:
        logger.error(f"Error optimizing route: {str(e)}")
        return jsonify({"success": False, "error": "Failed to optimize route"}), 500

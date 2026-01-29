import os
from datetime import datetime, timedelta

from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///instance/candy_route.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# Models
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(100))
    address = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    notes = db.Column(db.Text)
    balance = db.Column(db.Float, default=0.0)
    last_visit = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class RouteStop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    route_date = db.Column(db.Date, nullable=False)
    sequence = db.Column(db.Integer)
    completed = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    customer = db.relationship("Customer", backref="stops")


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    acknowledged = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    customer = db.relationship("Customer", backref="payments")


# Dashboard Route
@app.route("/")
def dashboard():
    total_customers = Customer.query.count()

    # Calculate balances
    customers_with_balance = Customer.query.filter(Customer.balance > 0).all()
    total_owed = sum(c.balance for c in customers_with_balance)
    urgent_customers = len(customers_with_balance)

    # Today's collections
    today = datetime.now().date()
    todays_payments = Payment.query.filter_by(payment_date=today).all()
    todays_collections = sum(p.amount for p in todays_payments)

    # Average balance
    avg_balance = total_owed / urgent_customers if urgent_customers > 0 else 0

    # Customer health
    never_visited = Customer.query.filter(Customer.last_visit == None).count()
    thirty_days_ago = today - timedelta(days=30)
    sixty_days_ago = today - timedelta(days=60)

    thirty_plus = Customer.query.filter(
        Customer.last_visit < thirty_days_ago, Customer.last_visit >= sixty_days_ago
    ).count()

    sixty_plus = Customer.query.filter(Customer.last_visit < sixty_days_ago).count()

    # Today's route
    todays_stops = RouteStop.query.filter_by(route_date=today).all()
    completed = sum(1 for s in todays_stops if s.completed)
    total = len(todays_stops)
    outstanding = sum(
        s.customer.balance for s in todays_stops if s.customer.balance > 0
    )

    return render_template(
        "dashboard.html",
        completed=completed,
        total=total,
        outstanding=f"{outstanding:.2f}",
        urgent_customers=urgent_customers,
        total_customers=total_customers,
        total_owed=f"{total_owed:.2f}",
        todays_collections=f"{todays_collections:.2f}",
        avg_balance=f"{avg_balance:.2f}",
        never_visited=never_visited,
        thirty_plus=thirty_plus,
        sixty_plus=sixty_plus,
    )


# Route Page
@app.route("/route")
def route():
    today = datetime.now().date()
    stops = (
        RouteStop.query.filter_by(route_date=today).order_by(RouteStop.sequence).all()
    )

    completed = sum(1 for s in stops if s.completed)
    total = len(stops)
    outstanding_balance = sum(s.customer.balance for s in stops)

    return render_template(
        "route.html",
        completed=completed,
        total=total,
        stops=stops,
        outstanding_balance=f"{outstanding_balance:.2f}",
    )


@app.route("/route/stop/<int:stop_id>")
def route_stop_details(stop_id):
    stop = RouteStop.query.get_or_404(stop_id)
    return render_template(
        "partials/stop_details.html",
        stop=stop,
    )


@app.route("/route/stop/<int:stop_id>/complete", methods=["POST"])
def complete_stop(stop_id):
    stop = RouteStop.query.get_or_404(stop_id)
    stop.completed = True
    stop.customer.last_visit = datetime.now().date()
    db.session.commit()
    return render_template("partials/stop_details.html", stop=stop)


@app.route("/route/stop/<int:stop_id>/uncomplete", methods=["POST"])
def uncomplete_stop(stop_id):
    stop = RouteStop.query.get_or_404(stop_id)
    stop.completed = False
    db.session.commit()
    return render_template("partials/stop_details.html", stop=stop)


# Customers Page
@app.route("/customers")
def customers():
    query = request.args.get("query", "")
    filter_type = request.args.get("filter", "")

    # Get all customers for stats
    all_customers = Customer.query.all()
    total_customers = len(all_customers)
    customers_with_balance = sum(1 for c in all_customers if (c.balance or 0) > 0)

    never_visited = sum(1 for c in all_customers if c.last_visit is None)

    # Calculate needs_visit (30+ days)
    thirty_days_ago = datetime.now().date() - timedelta(days=30)
    needs_visit = sum(
        1 for c in all_customers if c.last_visit and c.last_visit < thirty_days_ago
    )

    # Build filtered query
    customers_query = Customer.query

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
        thirty_days_ago = datetime.now().date() - timedelta(days=30)
        customers_query = customers_query.filter(Customer.last_visit < thirty_days_ago)
    elif filter_type == "60":
        sixty_days_ago = datetime.now().date() - timedelta(days=60)
        customers_query = customers_query.filter(Customer.last_visit < sixty_days_ago)

    customers_list = customers_query.order_by(Customer.name).all()

    return render_template(
        "customers.html",
        customers=customers_list,
        total_customers=total_customers,
        customers_with_balance=customers_with_balance,
        never_visited=never_visited,
        needs_visit=needs_visit,
        now=datetime.now().date(),
    )


@app.route("/customers/<int:customer_id>")
def customer_details(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    return render_template(
        "partials/customer_details.html",
        customer=customer,
        now=datetime.now().date(),
    )


@app.route("/customers/<int:customer_id>/edit")
def customer_edit(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    return render_template(
        "partials/customer_edit_modal.html",
        customer=customer,
    )


@app.route("/customers/add", methods=["POST"])
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
    db.session.commit()

    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>/update", methods=["POST"])
def customer_update(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    customer.name = request.form.get("name") or customer.name
    customer.phone = request.form.get("phone") or None
    customer.address = request.form.get("address") or None
    customer.city = request.form.get("city") or None
    customer.notes = request.form.get("notes") or None

    # Update balance if provided
    balance_str = request.form.get("balance")
    if balance_str:
        try:
            customer.balance = float(balance_str)
        except ValueError:
            pass

    db.session.commit()

    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>/delete")
def customer_delete(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    # Delete related records first
    RouteStop.query.filter_by(customer_id=customer_id).delete()
    Payment.query.filter_by(customer_id=customer_id).delete()

    db.session.delete(customer)
    db.session.commit()

    return redirect(url_for("customers"))


# Balances Page
@app.route("/balances")
def balances():
    query = request.args.get("query", "")
    sort_type = request.args.get("sort", "balance_desc")

    balances_query = Customer.query.filter(Customer.balance > 0)

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

    balances_list = balances_query.all()

    # Calculate stats
    if balances_list:
        total_owed = sum(c.balance for c in balances_list)
        avg_balance = total_owed / len(balances_list)
        highest_balance = max(c.balance for c in balances_list)
    else:
        total_owed = 0
        avg_balance = 0
        highest_balance = 0

    return render_template(
        "balances.html",
        balances=balances_list,
        total_owed=f"{total_owed:.2f}",
        avg_balance=f"{avg_balance:.2f}",
        highest_balance=f"{highest_balance:.2f}",
        now=datetime.now().date(),
    )


@app.route("/balances/<int:balance_id>")
def balance_details(balance_id):
    customer = Customer.query.get_or_404(balance_id)
    return render_template(
        "partials/balance_details.html",
        customer=customer,
        now=datetime.now().date(),
    )


# Planner Page
@app.route("/planner")
def planner():
    today = datetime.now().date()

    # Get all customers not already scheduled in future
    future_stops = RouteStop.query.filter(RouteStop.route_date >= today).all()
    scheduled_customer_ids = [s.customer_id for s in future_stops]

    available_customers = (
        Customer.query.filter(
            ~Customer.id.in_(scheduled_customer_ids) if scheduled_customer_ids else True
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

    # Get upcoming routes (next 7 days)
    upcoming_routes = []
    for i in range(7):
        check_date = today + timedelta(days=i)
        stops = (
            RouteStop.query.filter_by(route_date=check_date)
            .order_by(RouteStop.sequence)
            .all()
        )

        if stops or i == 0:  # Always show today
            upcoming_routes.append(
                {
                    "date": check_date.strftime("%Y-%m-%d"),
                    "date_formatted": check_date.strftime("%b %d, %Y"),
                    "day_name": check_date.strftime("%A"),
                    "stop_count": len(stops),
                    "first_customer": stops[0].customer.name if stops else None,
                }
            )

    # Calculate weekly stats
    week_end = today + timedelta(days=7)
    weekly_stops = RouteStop.query.filter(
        RouteStop.route_date >= today, RouteStop.route_date < week_end
    ).all()

    weekly_routes = len(set(s.route_date for s in weekly_stops))
    total_planned_stops = len(weekly_stops)

    # Prepare customer data for Alpine.js
    import json

    customers_data = []
    for c in available_customers:
        days_since = (today - c.last_visit).days if c.last_visit else None
        customers_data.append(
            {
                "id": c.id,
                "name": c.name,
                "city": c.city,
                "balance": float(c.balance),
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


@app.route("/planner/date/<date_str>")
def planner_date_details(date_str):
    try:
        route_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except:
        return "Invalid date", 400

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


@app.route("/planner/route/<int:route_id>")
def planner_route_details(route_id):
    return render_template(
        "partials/planner_route_details.html",
        route_id=route_id,
    )


@app.route("/planner/add-stop", methods=["POST"])
def add_stop_to_route():
    customer_id = request.form.get("customer_id")
    route_date_str = request.form.get("route_date")

    if not customer_id or not route_date_str:
        return jsonify({"success": False, "error": "Missing parameters"}), 400

    try:
        route_date = datetime.strptime(route_date_str, "%Y-%m-%d").date()
        customer = Customer.query.get_or_404(int(customer_id))

        # Get current max sequence for this route
        max_seq = (
            db.session.query(db.func.max(RouteStop.sequence))
            .filter_by(route_date=route_date)
            .scalar()
            or 0
        )

        # Create new stop
        new_stop = RouteStop(
            customer_id=customer.id,
            route_date=route_date,
            sequence=max_seq + 1,
            completed=False,
        )

        db.session.add(new_stop)
        db.session.commit()

        # Return updated route builder HTML
        stops = (
            RouteStop.query.filter_by(route_date=route_date)
            .order_by(RouteStop.sequence)
            .all()
        )
        return render_template(
            "partials/route_builder.html",
            stops=stops,
            route_date=route_date_str,
            date_formatted=route_date.strftime("%b %d, %Y"),
            day_name=route_date.strftime("%A"),
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/planner/stop/<int:stop_id>/remove", methods=["POST"])
def remove_stop_from_route():
    stop = RouteStop.query.get_or_404(stop_id)
    route_date = stop.route_date
    route_date_str = route_date.strftime("%Y-%m-%d")

    db.session.delete(stop)
    db.session.commit()

    # Return updated route builder HTML
    stops = (
        RouteStop.query.filter_by(route_date=route_date)
        .order_by(RouteStop.sequence)
        .all()
    )
    return render_template(
        "partials/route_builder.html",
        stops=stops,
        route_date=route_date_str,
        date_formatted=route_date.strftime("%b %d, %Y"),
        day_name=route_date.strftime("%A"),
    )


@app.route("/planner/route/<route_date>/clear", methods=["POST"])
def clear_route(route_date):
    try:
        date_obj = datetime.strptime(route_date, "%Y-%m-%d").date()
        RouteStop.query.filter_by(route_date=date_obj).delete()
        db.session.commit()

        return render_template(
            "partials/route_builder.html",
            stops=[],
            route_date=route_date,
            date_formatted=date_obj.strftime("%b %d, %Y"),
            day_name=date_obj.strftime("%A"),
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/planner/route/<route_date>/optimize", methods=["POST"])
def optimize_route(route_date):
    """Optimize route using nearest-neighbor algorithm grouped by city"""
    try:
        date_obj = datetime.strptime(route_date, "%Y-%m-%d").date()
        stops = RouteStop.query.filter_by(route_date=date_obj).all()

        if len(stops) <= 1:
            # Nothing to optimize
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

        # Reload stops in new order
        stops = (
            RouteStop.query.filter_by(route_date=date_obj)
            .order_by(RouteStop.sequence)
            .all()
        )

        return render_template(
            "partials/route_builder.html",
            stops=stops,
            route_date=route_date,
            date_formatted=date_obj.strftime("%b %d, %Y"),
            day_name=date_obj.strftime("%A"),
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# Analytics Page
@app.route("/analytics")
def analytics():
    import json
    from collections import defaultdict

    # Get all data
    all_customers = Customer.query.all()
    all_payments = Payment.query.all()
    all_stops = RouteStop.query.all()

    # Key metrics
    total_customers = len(all_customers)
    total_collected = sum(p.amount for p in all_payments)
    outstanding_customers = [c for c in all_customers if c.balance > 0]
    total_outstanding = sum(c.balance for c in outstanding_customers)
    outstanding_count = len(outstanding_customers)

    total_stops = len(all_stops)
    avg_per_stop = (total_collected / total_stops) if total_stops > 0 else 0

    completed_stops = sum(1 for s in all_stops if s.completed)
    visit_rate = int((completed_stops / total_stops * 100)) if total_stops > 0 else 0

    # Top customers by revenue
    customer_payments = defaultdict(
        lambda: {"total": 0, "count": 0, "name": "", "city": ""}
    )
    for payment in all_payments:
        customer = Customer.query.get(payment.customer_id)
        if customer:
            customer_payments[customer.id]["total"] += payment.amount
            customer_payments[customer.id]["count"] += 1
            customer_payments[customer.id]["name"] = customer.name
            customer_payments[customer.id]["city"] = customer.city

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
    seven_days_ago = datetime.now().date() - timedelta(days=7)
    thirty_days_ago = datetime.now().date() - timedelta(days=30)

    completed_this_week = sum(
        1 for s in all_stops if s.completed and s.route_date >= seven_days_ago
    )
    payments_this_week = sum(
        1 for p in all_payments if p.payment_date >= seven_days_ago
    )
    new_customers = sum(
        1
        for c in all_customers
        if c.created_at and c.created_at.date() >= thirty_days_ago
    )

    # City breakdown
    city_counts = defaultdict(int)
    for customer in all_customers:
        if customer.city:
            city_counts[customer.city] += 1

    cities = [{"name": city, "count": count} for city, count in city_counts.items()]
    cities.sort(key=lambda x: x["count"], reverse=True)

    # Revenue over time (last 30 days)
    revenue_by_date = defaultdict(float)
    for payment in all_payments:
        if payment.payment_date >= thirty_days_ago:
            date_str = payment.payment_date.strftime("%m/%d")
            revenue_by_date[date_str] += payment.amount

    # Fill in missing dates
    revenue_labels = []
    revenue_data = []
    for i in range(30):
        date = datetime.now().date() - timedelta(days=29 - i)
        date_str = date.strftime("%m/%d")
        revenue_labels.append(date_str)
        revenue_data.append(float(revenue_by_date.get(date_str, 0)))

    # Customer distribution
    paid_up = sum(1 for c in all_customers if c.balance == 0 and c.last_visit)
    with_balance = len(outstanding_customers)
    never_visited = sum(1 for c in all_customers if not c.last_visit)
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
    )


# Initialize database
@app.before_request
def create_tables():
    if not hasattr(app, "db_initialized"):
        db.create_all()
        app.db_initialized = True


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        # Add sample data if database is empty
        if Customer.query.count() == 0:
            print("Adding sample data...")

            # Create customers
            sample_customers = [
                Customer(
                    name="ABC Convenience",
                    city="Springfield",
                    balance=45.50,
                    last_visit=datetime.now().date() - timedelta(days=5),
                ),
                Customer(
                    name="Joe's Market",
                    city="Shelbyville",
                    balance=0,
                    last_visit=datetime.now().date() - timedelta(days=2),
                ),
                Customer(
                    name="Quick Stop",
                    city="Springfield",
                    balance=125.00,
                    last_visit=datetime.now().date() - timedelta(days=35),
                ),
                Customer(
                    name="Corner Store", city="Capital City", balance=0, last_visit=None
                ),
                Customer(
                    name="Main Street Deli",
                    city="Springfield",
                    balance=75.00,
                    last_visit=datetime.now().date() - timedelta(days=15),
                ),
                Customer(
                    name="Park Plaza Store",
                    city="Shelbyville",
                    balance=0,
                    last_visit=datetime.now().date() - timedelta(days=8),
                ),
            ]
            db.session.add_all(sample_customers)
            db.session.commit()

            # Create today's route
            today = datetime.now().date()
            today_stops = [
                RouteStop(
                    customer_id=sample_customers[0].id,
                    route_date=today,
                    sequence=1,
                    completed=True,
                ),
                RouteStop(
                    customer_id=sample_customers[1].id,
                    route_date=today,
                    sequence=2,
                    completed=True,
                ),
                RouteStop(
                    customer_id=sample_customers[4].id,
                    route_date=today,
                    sequence=3,
                    completed=False,
                ),
                RouteStop(
                    customer_id=sample_customers[5].id,
                    route_date=today,
                    sequence=4,
                    completed=False,
                ),
            ]
            db.session.add_all(today_stops)

            # Create a future route (tomorrow)
            tomorrow = today + timedelta(days=1)
            tomorrow_stops = [
                RouteStop(
                    customer_id=sample_customers[2].id,
                    route_date=tomorrow,
                    sequence=1,
                    completed=False,
                ),
            ]
            db.session.add_all(tomorrow_stops)

            # Add some payment history
            sample_payments = [
                Payment(
                    customer_id=sample_customers[0].id,
                    amount=50.00,
                    payment_date=today - timedelta(days=10),
                ),
                Payment(
                    customer_id=sample_customers[1].id,
                    amount=120.00,
                    payment_date=today - timedelta(days=5),
                ),
                Payment(
                    customer_id=sample_customers[4].id,
                    amount=25.00,
                    payment_date=today - timedelta(days=20),
                ),
                Payment(
                    customer_id=sample_customers[2].id,
                    amount=75.00,
                    payment_date=today - timedelta(days=15),
                ),
            ]
            db.session.add_all(sample_payments)

            db.session.commit()
            print("Sample data added with routes and payments!")

    app.run(debug=True, host="0.0.0.0", port=5000)

from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template
from flask_login import login_required

from app import db
from app.models import Customer, Payment, RouteStop

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def dashboard():
    total_customers = Customer.query.filter_by(status='active').count()
    total_leads = Customer.query.filter_by(status='lead').count()

    # Calculate balances efficiently using SQL aggregation (active customers only)
    balance_stats = db.session.query(
        db.func.sum(Customer.balance),
        db.func.count(Customer.id)
    ).filter(Customer.balance > 0, Customer.status == 'active').first()

    total_owed = balance_stats[0] or 0
    urgent_customers = balance_stats[1] or 0

    # Today's collections using SQL aggregation
    today = datetime.now(timezone.utc).date()
    todays_collections = db.session.query(
        db.func.sum(Payment.amount)
    ).filter(Payment.payment_date == today).scalar() or 0

    # Average balance
    avg_balance = float(total_owed) / urgent_customers if urgent_customers > 0 else 0

    # Customer health - efficient queries (active customers only)
    never_visited = Customer.query.filter(Customer.last_visit == None, Customer.status == 'active').count()
    thirty_days_ago = today - timedelta(days=30)
    sixty_days_ago = today - timedelta(days=60)

    thirty_plus = Customer.query.filter(
        Customer.last_visit < thirty_days_ago, Customer.last_visit >= sixty_days_ago, Customer.status == 'active'
    ).count()

    sixty_plus = Customer.query.filter(Customer.last_visit < sixty_days_ago, Customer.status == 'active').count()

    # Today's route
    todays_stops = RouteStop.query.options(db.joinedload(RouteStop.customer)).filter_by(route_date=today).all()
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
        total_leads=total_leads,
        total_owed=f"{total_owed:.2f}",
        todays_collections=f"{todays_collections:.2f}",
        avg_balance=f"{avg_balance:.2f}",
        never_visited=never_visited,
        thirty_plus=thirty_plus,
        sixty_plus=sixty_plus,
    )

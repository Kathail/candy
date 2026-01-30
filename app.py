import csv
import io
import logging
import os
from datetime import datetime, timedelta, timezone

from flask import Flask, Response, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Fix Render's PostgreSQL URL (postgres:// -> postgresql://)
database_url = os.environ.get("DATABASE_URL", "sqlite:///candy_route.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max request size
app.config["WTF_CSRF_TIME_LIMIT"] = None  # CSRF tokens don't expire

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"


# User model for authentication
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="sales", nullable=False)  # admin, sales
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == "admin"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template("errors/404.html"), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template("errors/500.html"), 500


# Models with indexes for better query performance
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    city = db.Column(db.String(100), index=True)
    address = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    notes = db.Column(db.Text)
    balance = db.Column(db.Float, default=0.0, index=True)
    last_visit = db.Column(db.Date, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(20), default='active', nullable=False, index=True)  # lead, active, inactive


class RouteStop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False, index=True)
    route_date = db.Column(db.Date, nullable=False, index=True)
    sequence = db.Column(db.Integer)
    completed = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    customer = db.relationship("Customer", backref="stops")


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False, index=True)
    acknowledged = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    receipt_number = db.Column(db.String(20), unique=True, index=True)
    previous_balance = db.Column(db.Float)
    customer = db.relationship("Customer", backref="payments")


# Service Worker route (must be served from root)
@app.route("/sw.js")
def service_worker():
    return app.send_static_file("sw.js")


# Authentication Routes
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=request.form.get("remember"))
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# Admin decorator
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function


@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users)


@app.route("/admin/users/add", methods=["POST"])
@login_required
@admin_required
def admin_add_user():
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "sales")

    if not username or not email or not password:
        return jsonify({"error": "All fields required"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 400

    user = User(username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    logger.info(f"Admin {current_user.username} created user {username}")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({"error": "Cannot delete yourself"}), 400

    user = User.query.get_or_404(user_id)
    username = user.username
    db.session.delete(user)
    db.session.commit()
    logger.info(f"Admin {current_user.username} deleted user {username}")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/toggle-role", methods=["POST"])
@login_required
@admin_required
def admin_toggle_role(user_id):
    if user_id == current_user.id:
        return jsonify({"error": "Cannot change your own role"}), 400

    user = User.query.get_or_404(user_id)
    user.role = "sales" if user.role == "admin" else "admin"
    db.session.commit()
    logger.info(f"Admin {current_user.username} changed {user.username} role to {user.role}")
    return redirect(url_for("admin_users"))


@app.route("/admin/import", methods=["GET", "POST"])
@login_required
@admin_required
def admin_import():
    if request.method == "POST":
        if "file" not in request.files:
            return render_template("admin/import.html", error="No file selected")

        file = request.files["file"]
        if file.filename == "":
            return render_template("admin/import.html", error="No file selected")

        if not file.filename.endswith(".csv"):
            return render_template("admin/import.html", error="File must be a CSV")

        clear_existing = request.form.get("clear_existing") == "on"

        try:
            # Read CSV content
            import io
            stream = io.StringIO(file.stream.read().decode("utf-8"))
            reader = csv.DictReader(stream)

            # Validate columns
            required_columns = {"name"}
            if not required_columns.issubset(set(reader.fieldnames or [])):
                return render_template("admin/import.html", error="CSV must have 'name' column")

            if clear_existing:
                RouteStop.query.delete()
                Payment.query.delete()
                Customer.query.delete()
                db.session.commit()

            imported = 0
            skipped = 0

            for row in reader:
                # Check for duplicate
                existing = Customer.query.filter_by(
                    name=row.get("name", ""),
                    phone=row.get("phone", "")
                ).first()

                if existing:
                    skipped += 1
                    continue

                customer = Customer(
                    name=row.get("name", ""),
                    address=row.get("address", ""),
                    city=row.get("city", ""),
                    phone=row.get("phone", ""),
                    notes=row.get("notes", ""),
                    balance=float(row.get("balance", 0) or 0),
                    created_at=datetime.now(timezone.utc),
                )
                db.session.add(customer)
                imported += 1

                if imported % 50 == 0:
                    db.session.commit()

            db.session.commit()
            logger.info(f"Admin {current_user.username} imported {imported} customers")
            return render_template("admin/import.html",
                                   success=f"Imported {imported} customers ({skipped} skipped as duplicates)")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Import error: {e}")
            return render_template("admin/import.html", error=f"Import failed: {str(e)}")

    return render_template("admin/import.html",
                           customer_count=Customer.query.count(),
                           payment_count=Payment.query.count(),
                           route_count=RouteStop.query.count())


@app.route("/admin/import-leads", methods=["GET", "POST"])
@login_required
@admin_required
def admin_import_leads():
    if request.method == "POST":
        if "file" not in request.files:
            return render_template("admin/import_leads.html", error="No file selected")

        file = request.files["file"]
        if file.filename == "":
            return render_template("admin/import_leads.html", error="No file selected")

        if not file.filename.endswith(".csv"):
            return render_template("admin/import_leads.html", error="File must be a CSV")

        try:
            stream = io.StringIO(file.stream.read().decode("utf-8"))
            reader = csv.DictReader(stream)

            # Validate columns - name is required
            if "name" not in (reader.fieldnames or []):
                return render_template("admin/import_leads.html", error="CSV must have 'name' column")

            imported = 0
            skipped = 0

            for row in reader:
                name = row.get("name", "").strip()
                if not name:
                    skipped += 1
                    continue

                # Clean phone number
                phone = row.get("phone", "").strip()
                if phone:
                    if phone.startswith("Phone Number"):
                        phone = phone.replace("Phone Number", "").strip()
                    if phone.lower() in ["call", "phone", "n/a", "none", "-", ""]:
                        phone = None
                phone = phone or None

                # Check for duplicate by name+phone
                existing = Customer.query.filter_by(name=name, phone=phone if phone else None).first()
                if existing:
                    skipped += 1
                    continue

                lead = Customer(
                    name=name,
                    address=row.get("address", "").strip() or None,
                    city=row.get("city", "").strip() or None,
                    phone=phone or None,
                    notes=row.get("notes", "").strip() or row.get("source", "").strip() or None,
                    balance=0.0,
                    status='lead',
                    created_at=datetime.now(timezone.utc),
                )
                db.session.add(lead)
                imported += 1

                if imported % 50 == 0:
                    db.session.commit()

            db.session.commit()
            logger.info(f"Admin {current_user.username} imported {imported} leads")
            return render_template("admin/import_leads.html",
                                   success=f"Imported {imported} leads ({skipped} skipped as duplicates)")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Lead import error: {e}")
            return render_template("admin/import_leads.html", error=f"Import failed: {str(e)}")

    return render_template("admin/import_leads.html",
                           lead_count=Customer.query.filter_by(status='lead').count())


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_user.check_password(current_password):
            return render_template("change_password.html", error="Current password is incorrect")

        if len(new_password) < 6:
            return render_template("change_password.html", error="New password must be at least 6 characters")

        if new_password != confirm_password:
            return render_template("change_password.html", error="New passwords do not match")

        current_user.set_password(new_password)
        db.session.commit()
        logger.info(f"Password changed for user {current_user.username}")
        return render_template("change_password.html", success="Password changed successfully")

    return render_template("change_password.html")


# Dashboard Route
@app.route("/")
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
    today = datetime.now().date()
    todays_collections = db.session.query(
        db.func.sum(Payment.amount)
    ).filter(Payment.payment_date == today).scalar() or 0

    # Average balance
    avg_balance = total_owed / urgent_customers if urgent_customers > 0 else 0

    # Customer health - efficient queries (active customers only)
    never_visited = Customer.query.filter(Customer.last_visit == None, Customer.status == 'active').count()
    thirty_days_ago = today - timedelta(days=30)
    sixty_days_ago = today - timedelta(days=60)

    thirty_plus = Customer.query.filter(
        Customer.last_visit < thirty_days_ago, Customer.last_visit >= sixty_days_ago, Customer.status == 'active'
    ).count()

    sixty_plus = Customer.query.filter(Customer.last_visit < sixty_days_ago, Customer.status == 'active').count()

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
        total_leads=total_leads,
        total_owed=f"{total_owed:.2f}",
        todays_collections=f"{todays_collections:.2f}",
        avg_balance=f"{avg_balance:.2f}",
        never_visited=never_visited,
        thirty_plus=thirty_plus,
        sixty_plus=sixty_plus,
    )


# Route Page
@app.route("/route")
@login_required
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
@login_required
def route_stop_details(stop_id):
    stop = RouteStop.query.get_or_404(stop_id)
    return render_template(
        "partials/stop_details.html",
        stop=stop,
    )


@app.route("/route/stop/<int:stop_id>/complete", methods=["POST"])
@login_required
def complete_stop(stop_id):
    stop = RouteStop.query.get_or_404(stop_id)
    stop.completed = True
    stop.customer.last_visit = datetime.now().date()
    db.session.commit()
    logger.info(f"Stop {stop_id} completed for customer {stop.customer.name}")
    return render_template("partials/stop_details.html", stop=stop)


@app.route("/route/stop/<int:stop_id>/uncomplete", methods=["POST"])
@login_required
def uncomplete_stop(stop_id):
    stop = RouteStop.query.get_or_404(stop_id)
    stop.completed = False
    db.session.commit()
    return render_template("partials/stop_details.html", stop=stop)


# Customers Page
@app.route("/customers")
@login_required
def customers():
    query = request.args.get("query", "")
    filter_type = request.args.get("filter", "")
    status_filter = request.args.get("status", "active")  # Default to active
    sort_by = request.args.get("sort", "name")
    page = int(request.args.get("page", 1))
    per_page = 50  # Show 50 customers per page

    # Get stats efficiently using SQL aggregation (active customers only)
    total_customers = Customer.query.filter_by(status='active').count()
    customers_with_balance = Customer.query.filter(Customer.balance > 0, Customer.status == 'active').count()
    never_visited = Customer.query.filter(Customer.last_visit == None, Customer.status == 'active').count()

    # Calculate needs_visit (30+ days)
    thirty_days_ago = datetime.now().date() - timedelta(days=30)
    needs_visit = Customer.query.filter(
        Customer.last_visit != None,
        Customer.last_visit < thirty_days_ago,
        Customer.status == 'active'
    ).count()

    # Build filtered query - apply status filter
    if status_filter == "all":
        customers_query = Customer.query
    elif status_filter == "inactive":
        customers_query = Customer.query.filter_by(status='inactive')
    else:  # default to active
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
        thirty_days_ago = datetime.now().date() - timedelta(days=30)
        customers_query = customers_query.filter(Customer.last_visit < thirty_days_ago)
    elif filter_type == "60":
        sixty_days_ago = datetime.now().date() - timedelta(days=60)
        customers_query = customers_query.filter(Customer.last_visit < sixty_days_ago)

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
            now=datetime.now().date(),
        )

    return render_template(
        "customers.html",
        customers=customers_list,
        pagination=pagination,
        total_customers=total_customers,
        customers_with_balance=customers_with_balance,
        never_visited=never_visited,
        needs_visit=needs_visit,
        now=datetime.now().date(),
    )


@app.route("/customers/<int:customer_id>")
@login_required
def customer_details(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    return render_template(
        "partials/customer_details.html",
        customer=customer,
        now=datetime.now().date(),
    )


@app.route("/customers/<int:customer_id>/edit")
@login_required
def customer_edit(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    return render_template(
        "partials/customer_edit_modal.html",
        customer=customer,
        now=datetime.now(),
    )


@app.route("/customers/add", methods=["POST"])
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
    db.session.commit()
    logger.info(f"Customer added: {name}")

    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>/update", methods=["POST"])
@login_required
def customer_update(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    customer.name = request.form.get("name") or customer.name
    customer.phone = request.form.get("phone") or None
    customer.address = request.form.get("address") or None
    customer.city = request.form.get("city") or None
    customer.notes = request.form.get("notes") or None

    # Update balance if provided with proper validation
    balance_str = request.form.get("balance")
    if balance_str:
        try:
            balance_value = float(balance_str)
            if balance_value < 0:
                return "Balance cannot be negative", 400
            customer.balance = balance_value
        except ValueError:
            return "Invalid balance value", 400

    db.session.commit()
    logger.info(f"Customer updated: {customer.name}")

    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>/delete", methods=["POST"])
@login_required
def customer_delete(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer_name = customer.name

    # Delete related records first
    RouteStop.query.filter_by(customer_id=customer_id).delete()
    Payment.query.filter_by(customer_id=customer_id).delete()

    db.session.delete(customer)
    db.session.commit()
    logger.info(f"Customer deleted: {customer_name}")

    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>/archive", methods=["POST"])
@login_required
def customer_archive(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.status = 'inactive'
    db.session.commit()
    logger.info(f"Customer archived: {customer.name}")
    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>/reactivate", methods=["POST"])
@login_required
def customer_reactivate(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.status = 'active'
    db.session.commit()
    logger.info(f"Customer reactivated: {customer.name}")
    return redirect(url_for("customers", status="inactive"))


@app.route("/customers/<int:customer_id>/add-payment", methods=["POST"])
@login_required
def customer_add_payment(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    amount = float(request.form.get("amount", 0))
    payment_date_str = request.form.get("payment_date")
    notes = request.form.get("notes", "").strip()

    if payment_date_str:
        payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()
    else:
        payment_date = datetime.now().date()

    # Create payment
    payment = Payment(
        customer_id=customer.id,
        amount=amount,
        payment_date=payment_date,
        notes=notes if notes else None,
        previous_balance=customer.balance,
    )

    # Update customer balance
    customer.balance = max(0, customer.balance - amount)

    db.session.add(payment)
    db.session.commit()

    logger.info(f"Payment recorded for {customer.name}: ${amount:.2f}")
    flash(f"Payment of ${amount:.2f} recorded", "success")

    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>/delete-payment/<int:payment_id>", methods=["POST"])
@login_required
def customer_delete_payment(customer_id, payment_id):
    customer = Customer.query.get_or_404(customer_id)
    payment = Payment.query.get_or_404(payment_id)

    # Make sure payment belongs to this customer
    if payment.customer_id != customer_id:
        flash("Invalid payment", "error")
        return redirect(url_for("customers"))

    # Restore the balance
    customer.balance += payment.amount

    db.session.delete(payment)
    db.session.commit()

    logger.info(f"Payment deleted for {customer.name}: ${payment.amount:.2f}")
    flash(f"Payment of ${payment.amount:.2f} deleted", "success")

    return redirect(url_for("customers"))


# Leads Page
@app.route("/leads")
@login_required
def leads():
    query = request.args.get("query", "")
    sort_by = request.args.get("sort", "name")
    page = int(request.args.get("page", 1))
    per_page = 50

    # Get stats
    total_leads = Customer.query.filter_by(status='lead').count()

    # Build query
    leads_query = Customer.query.filter_by(status='lead')

    if query:
        leads_query = leads_query.filter(
            db.or_(
                Customer.name.ilike(f"%{query}%"),
                Customer.city.ilike(f"%{query}%"),
                Customer.notes.ilike(f"%{query}%"),
            )
        )

    # Apply sorting
    if sort_by == "name":
        leads_query = leads_query.order_by(Customer.name)
    elif sort_by == "city":
        leads_query = leads_query.order_by(Customer.city, Customer.name)
    elif sort_by == "newest":
        leads_query = leads_query.order_by(Customer.created_at.desc())
    elif sort_by == "oldest":
        leads_query = leads_query.order_by(Customer.created_at)
    else:
        leads_query = leads_query.order_by(Customer.name)

    # Paginate
    pagination = leads_query.paginate(page=page, per_page=per_page, error_out=False)
    leads_list = pagination.items

    # Return partial for HTMX requests
    if request.headers.get("HX-Request"):
        return render_template(
            "partials/leads_table_rows.html",
            leads=leads_list,
            now=datetime.now().date(),
        )

    return render_template(
        "leads.html",
        leads=leads_list,
        pagination=pagination,
        total_leads=total_leads,
        now=datetime.now().date(),
    )


@app.route("/leads/add", methods=["POST"])
@login_required
def lead_add():
    name = request.form.get("name")
    phone = request.form.get("phone")
    address = request.form.get("address")
    city = request.form.get("city")
    notes = request.form.get("notes")

    if not name:
        return "Name is required", 400

    new_lead = Customer(
        name=name,
        phone=phone or None,
        address=address or None,
        city=city or None,
        notes=notes or None,
        balance=0.0,
        status='lead',
    )

    db.session.add(new_lead)
    db.session.commit()
    logger.info(f"Lead added: {name}")

    return redirect(url_for("leads"))


@app.route("/leads/<int:lead_id>/edit")
@login_required
def lead_edit(lead_id):
    lead = Customer.query.get_or_404(lead_id)
    if lead.status != 'lead':
        return "Not a lead", 400
    return render_template(
        "partials/lead_edit_modal.html",
        lead=lead,
    )


@app.route("/leads/<int:lead_id>/update", methods=["POST"])
@login_required
def lead_update(lead_id):
    lead = Customer.query.get_or_404(lead_id)

    lead.name = request.form.get("name") or lead.name
    lead.phone = request.form.get("phone") or None
    lead.address = request.form.get("address") or None
    lead.city = request.form.get("city") or None
    lead.notes = request.form.get("notes") or None

    db.session.commit()
    logger.info(f"Lead updated: {lead.name}")

    return redirect(url_for("leads"))


@app.route("/leads/<int:lead_id>/convert", methods=["POST"])
@login_required
def lead_convert(lead_id):
    lead = Customer.query.get_or_404(lead_id)
    if lead.status != 'lead':
        return "Not a lead", 400

    lead.status = 'active'
    db.session.commit()
    logger.info(f"Lead converted to customer: {lead.name}")

    return redirect(url_for("leads"))


@app.route("/leads/<int:lead_id>/delete", methods=["POST"])
@login_required
def lead_delete(lead_id):
    lead = Customer.query.get_or_404(lead_id)
    if lead.status != 'lead':
        return "Not a lead", 400

    lead_name = lead.name
    db.session.delete(lead)
    db.session.commit()
    logger.info(f"Lead deleted: {lead_name}")

    return redirect(url_for("leads"))


# Balances Page
@app.route("/balances")
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
@login_required
def balance_details(balance_id):
    customer = Customer.query.get_or_404(balance_id)
    return render_template(
        "partials/balance_details.html",
        customer=customer,
        now=datetime.now().date(),
    )


@app.route("/balances/record-payment", methods=["POST"])
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
            payment_date = datetime.now().date()

        # Store previous balance before updating
        previous_balance = customer.balance

        # Generate receipt number (format: RCP-YYYYMMDD-XXXX)
        today_str = datetime.now().strftime("%Y%m%d")
        today_count = Payment.query.filter(
            Payment.receipt_number.like(f"RCP-{today_str}-%")
        ).count()
        receipt_number = f"RCP-{today_str}-{today_count + 1:04d}"

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
        db.session.commit()
        logger.info(f"Payment recorded: ${amount} from {customer.name} (Receipt: {receipt_number})")

        return redirect(url_for("balances"))
    except ValueError:
        return jsonify({"error": "Invalid amount value"}), 400
    except Exception as e:
        logger.error(f"Error recording payment: {str(e)}")
        return jsonify({"error": "Error recording payment"}), 500


# Planner Page
@app.route("/planner")
@login_required
def planner():
    today = datetime.now().date()

    # Get all customers not already scheduled in future
    future_stops = RouteStop.query.filter(RouteStop.route_date >= today).all()
    scheduled_customer_ids = [s.customer_id for s in future_stops]

    available_customers = (
        Customer.query.filter(
            Customer.status == 'active',
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

    # Prepare customer data for Alpine.js - use tojson filter instead of |safe
    import json

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


@app.route("/planner/date/<date_str>")
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


@app.route("/planner/route/<int:route_id>")
@login_required
def planner_route_details(route_id):
    return render_template(
        "partials/planner_route_details.html",
        route_id=route_id,
    )


@csrf.exempt  # JSON API endpoint
@app.route("/planner/add-stop", methods=["POST"])
@login_required
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

        # Return JSON for new planner
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
        return jsonify({"success": False, "error": str(e)}), 500


@csrf.exempt  # JSON API endpoint
@app.route("/planner/stop/<int:stop_id>/remove", methods=["POST"])
@login_required
def remove_stop_from_route(stop_id):
    stop = RouteStop.query.get_or_404(stop_id)

    db.session.delete(stop)
    db.session.commit()

    return jsonify({"success": True})


@csrf.exempt  # JSON API endpoint
@app.route("/planner/route/<route_date>/clear", methods=["POST"])
@login_required
def clear_route(route_date):
    try:
        date_obj = datetime.strptime(route_date, "%Y-%m-%d").date()
        RouteStop.query.filter_by(route_date=date_obj).delete()
        db.session.commit()

        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error clearing route: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/customer/<int:customer_id>/details")
@login_required
def get_customer_details(customer_id):
    """Get detailed customer information for modal"""
    customer = Customer.query.get_or_404(customer_id)

    # Get payment history
    payments = (
        Payment.query.filter_by(customer_id=customer_id)
        .order_by(Payment.payment_date.desc())
        .limit(10)
        .all()
    )

    # Get visit history
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


@app.route("/planner/all-stops")
@login_required
def get_all_stops():
    """Return all stops grouped by date for the calendar"""
    # Get stops for the next 60 days
    today = datetime.now().date()
    future_date = today + timedelta(days=60)

    stops = (
        RouteStop.query.filter(
            RouteStop.route_date >= today, RouteStop.route_date <= future_date
        )
        .order_by(RouteStop.sequence)
        .all()
    )

    # Group by date
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


@csrf.exempt  # JSON API endpoint
@app.route("/planner/route/<route_date>/optimize", methods=["POST"])
@login_required
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
        return jsonify({"success": False, "error": str(e)}), 500


# Analytics Page
@app.route("/analytics")
@login_required
def analytics():
    import json
    from collections import defaultdict

    # Get date range from query params
    date_range = request.args.get("range", "30")
    today = datetime.now().date()

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

    total_outstanding = outstanding_stats[0] or 0 if outstanding_stats else 0
    outstanding_count = outstanding_stats[1] or 0 if outstanding_stats else 0

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
            customer_payments[payment.customer_id]["total"] += payment.amount
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
    seven_days_ago = datetime.now().date() - timedelta(days=7)
    thirty_days_ago = datetime.now().date() - timedelta(days=30)

    completed_this_week = sum(
        1 for s in all_stops if s.completed and s.route_date >= seven_days_ago
    )
    payments_this_week = sum(
        1 for p in all_payments if p.payment_date >= seven_days_ago
    )

    # New customers count using efficient query (active only)
    new_customers = Customer.query.filter(
        Customer.created_at != None,
        Customer.created_at >= datetime.combine(thirty_days_ago, datetime.min.time()),
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
            revenue_by_date[date_str] += payment.amount

    # Fill in missing dates
    revenue_labels = []
    revenue_data = []
    for i in range(30):
        date = datetime.now().date() - timedelta(days=29 - i)
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


# CSV Export Routes
@app.route("/export/customers")
@login_required
def export_customers():
    """Export all customers as CSV"""
    customers_list = Customer.query.order_by(Customer.name).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        "ID", "Name", "City", "Address", "Phone", "Notes",
        "Balance", "Last Visit", "Created At"
    ])

    # Data rows
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
            "Content-Disposition": f"attachment; filename=customers_{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )


@app.route("/export/payments")
@login_required
def export_payments():
    """Export all payments as CSV"""
    payments_list = Payment.query.options(
        db.joinedload(Payment.customer)
    ).order_by(Payment.payment_date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        "ID", "Receipt Number", "Customer Name", "Customer City",
        "Amount", "Previous Balance", "Payment Date", "Notes"
    ])

    # Data rows
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
            "Content-Disposition": f"attachment; filename=payments_{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )


@app.route("/export/routes")
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

    # Header row
    writer.writerow([
        "ID", "Route Date", "Sequence", "Customer Name", "Customer City",
        "Completed", "Notes"
    ])

    # Data rows
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
            "Content-Disposition": f"attachment; filename=routes_{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )


# PDF Receipt Generation
def generate_receipt_pdf(payment):
    """Generate a PDF receipt for a payment"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    elements = []

    # Custom styles
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=20,
        alignment=1  # Center
    )
    header_style = ParagraphStyle(
        'Header',
        parent=styles['Normal'],
        fontSize=12,
        alignment=1  # Center
    )

    # Header
    elements.append(Paragraph("Candy Route Planner", title_style))
    elements.append(Paragraph("Payment Receipt", header_style))
    elements.append(Spacer(1, 30))

    # Receipt details table
    new_balance = (payment.previous_balance or 0) - payment.amount
    if new_balance < 0:
        new_balance = 0

    receipt_data = [
        ["Receipt Number:", payment.receipt_number or "N/A"],
        ["Date:", payment.payment_date.strftime("%B %d, %Y")],
        ["", ""],
        ["Customer:", payment.customer.name if payment.customer else "N/A"],
        ["City:", payment.customer.city if payment.customer else "N/A"],
        ["", ""],
        ["Previous Balance:", f"${payment.previous_balance:.2f}" if payment.previous_balance is not None else "N/A"],
        ["Payment Amount:", f"${payment.amount:.2f}"],
        ["New Balance:", f"${new_balance:.2f}"],
    ]

    if payment.notes:
        receipt_data.append(["", ""])
        receipt_data.append(["Notes:", payment.notes])

    table = Table(receipt_data, colWidths=[2*inch, 4*inch])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        # Highlight the payment row
        ('BACKGROUND', (0, 7), (-1, 7), colors.Color(0.9, 1, 0.9)),
        ('FONTNAME', (0, 7), (-1, 7), 'Helvetica-Bold'),
    ]))
    elements.append(table)

    elements.append(Spacer(1, 40))

    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.gray,
        alignment=1
    )
    elements.append(Paragraph("Thank you for your payment!", footer_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", footer_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer


@app.route("/receipts/<int:payment_id>/pdf")
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
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


# JSON API for offline mode
@app.route("/api/route/today")
@login_required
def api_route_today():
    """JSON API endpoint for today's route - used by offline mode"""
    today = datetime.now().date()
    stops = (
        RouteStop.query.filter_by(route_date=today)
        .order_by(RouteStop.sequence)
        .all()
    )

    stops_data = []
    for stop in stops:
        stops_data.append({
            "id": stop.id,
            "sequence": stop.sequence,
            "completed": stop.completed,
            "notes": stop.notes,
            "customer": {
                "id": stop.customer.id,
                "name": stop.customer.name,
                "city": stop.customer.city,
                "address": stop.customer.address,
                "phone": stop.customer.phone,
                "balance": float(stop.customer.balance) if stop.customer.balance else 0,
                "last_visit": stop.customer.last_visit.strftime("%Y-%m-%d") if stop.customer.last_visit else None
            }
        })

    return jsonify({
        "date": today.strftime("%Y-%m-%d"),
        "stops": stops_data,
        "total": len(stops),
        "completed": sum(1 for s in stops if s.completed)
    })


# Admin route to reimport customers (clears existing)
@app.route("/admin/reimport-customers", methods=["POST"])
@login_required
def admin_reimport_customers():
    """Clear all customers and reimport from CSV"""
    csv_file = os.path.join(os.path.dirname(__file__), "customers_cleaned.csv")
    if not os.path.exists(csv_file):
        return jsonify({"error": "CSV file not found"}), 404

    try:
        # Clear existing data
        RouteStop.query.delete()
        Payment.query.delete()
        Customer.query.delete()
        db.session.commit()

        # Import from CSV
        imported = 0
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                customer = Customer(
                    name=row["name"],
                    address=row.get("address", ""),
                    city=row.get("city", ""),
                    phone=row.get("phone", ""),
                    balance=0.0,
                    created_at=datetime.now(timezone.utc),
                )
                db.session.add(customer)
                imported += 1
                if imported % 50 == 0:
                    db.session.commit()
        db.session.commit()
        logger.info(f"Reimported {imported} customers from CSV")
        return jsonify({"success": True, "imported": imported})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error reimporting customers: {e}")
        return jsonify({"error": str(e)}), 500


# Initialize database - runs once at startup
def init_db():
    """Initialize database tables and fix any data issues"""
    with app.app_context():
        db.create_all()

        # Run schema migrations (add missing columns)
        from sqlalchemy import text, inspect
        inspector = inspect(db.engine)
        is_postgres = "postgresql" in app.config["SQLALCHEMY_DATABASE_URI"]

        # Helper to check if column exists
        def column_exists(table_name, column_name):
            if table_name in inspector.get_table_names():
                columns = [col["name"] for col in inspector.get_columns(table_name)]
                return column_name in columns
            return False

        # Migrate user table - add role column
        if "user" in inspector.get_table_names() and not column_exists("user", "role"):
            if is_postgres:
                db.session.execute(text('ALTER TABLE "user" ADD COLUMN role VARCHAR(20) DEFAULT \'sales\''))
            else:
                db.session.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR(20) DEFAULT 'sales'"))
            db.session.execute(text("UPDATE \"user\" SET role='admin' WHERE username='admin'"))
            db.session.commit()
            logger.info("Added role column to user table")

        # Migrate payment table - add receipt_number and previous_balance columns
        if "payment" in inspector.get_table_names():
            if not column_exists("payment", "receipt_number"):
                db.session.execute(text("ALTER TABLE payment ADD COLUMN receipt_number VARCHAR(20)"))
                db.session.commit()
                logger.info("Added receipt_number column to payment table")

            if not column_exists("payment", "previous_balance"):
                db.session.execute(text("ALTER TABLE payment ADD COLUMN previous_balance FLOAT"))
                db.session.commit()
                logger.info("Added previous_balance column to payment table")

        # Migrate customer table - add status column
        if "customer" in inspector.get_table_names() and not column_exists("customer", "status"):
            db.session.execute(text("ALTER TABLE customer ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
            db.session.execute(text("UPDATE customer SET status = 'active' WHERE status IS NULL"))
            db.session.commit()
            logger.info("Added status column to customer table")

        # Create default admin user if no users exist
        if User.query.count() == 0:
            admin = User(
                username="admin",
                email="admin@candyroute.local",
                role="admin"
            )
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            logger.info("Created default admin user (username: admin, password: admin123)")

        # Import customers from CSV if database is empty
        if Customer.query.count() == 0:
            csv_file = os.path.join(os.path.dirname(__file__), "customers_cleaned.csv")
            if os.path.exists(csv_file):
                logger.info(f"Importing customers from {csv_file}...")
                imported = 0
                try:
                    with open(csv_file, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            customer = Customer(
                                name=row["name"],
                                address=row.get("address", ""),
                                city=row.get("city", ""),
                                phone=row.get("phone", ""),
                                balance=0.0,
                                created_at=datetime.now(timezone.utc),
                            )
                            db.session.add(customer)
                            imported += 1
                            if imported % 50 == 0:
                                db.session.commit()
                    db.session.commit()
                    logger.info(f"Imported {imported} customers from CSV")
                except Exception as e:
                    logger.error(f"Error importing customers: {e}")
                    db.session.rollback()

        # Fix any None balances
        customers_with_none_balance = Customer.query.filter(
            Customer.balance == None
        ).all()
        for customer in customers_with_none_balance:
            customer.balance = 0.0
        if customers_with_none_balance:
            db.session.commit()
            logger.info(f"Fixed {len(customers_with_none_balance)} customers with None balance")

        # Fix any None created_at dates
        customers_with_none_created = Customer.query.filter(
            Customer.created_at == None
        ).all()
        for customer in customers_with_none_created:
            customer.created_at = datetime.now(timezone.utc)
        if customers_with_none_created:
            db.session.commit()
            logger.info(f"Fixed {len(customers_with_none_created)} customers with None created_at")


# Initialize database on module load (for gunicorn/production)
init_db()


if __name__ == "__main__":

    # Check if we're in development mode
    debug_mode = os.environ.get("FLASK_ENV") == "development" or os.environ.get("FLASK_DEBUG") == "1"
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", 5000))

    # Add sample data if database is empty (development only)
    if debug_mode:
        with app.app_context():
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

    app.run(debug=debug_mode, host=host, port=port)

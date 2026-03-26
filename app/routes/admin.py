import csv
import io
import logging
import zipfile
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.helpers import admin_required, get_setting, log_audit, sanitize_csv_value as _s, set_setting
from app.models import ActivityLog, Announcement, AuditLog, Customer, Payment, RouteStop, Setting, User

logger = logging.getLogger(__name__)
bp = Blueprint("admin", __name__)


@bp.route("/admin/users")
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users)


@bp.route("/admin/users/add", methods=["POST"])
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
    db.session.flush()
    log_audit(current_user.id, "create_user", f"Created user {username}", "user", user.id)
    db.session.commit()
    logger.info(f"Admin {current_user.username} created user {username}")
    return redirect(url_for("admin.admin_users"))


@bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({"error": "Cannot delete yourself"}), 400

    user = User.query.get_or_404(user_id)
    username = user.username
    log_audit(current_user.id, "delete_user", f"Deleted user {username}", "user", user_id)
    db.session.delete(user)
    db.session.commit()
    logger.info(f"Admin {current_user.username} deleted user {username}")
    return redirect(url_for("admin.admin_users"))


@bp.route("/admin/users/<int:user_id>/toggle-role", methods=["POST"])
@login_required
@admin_required
def admin_toggle_role(user_id):
    if user_id == current_user.id:
        return jsonify({"error": "Cannot change your own role"}), 400

    user = User.query.get_or_404(user_id)
    old_role = user.role
    user.role = "sales" if user.role == "admin" else "admin"
    log_audit(current_user.id, "toggle_role", f"Changed {user.username} from {old_role} to {user.role}", "user", user_id)
    db.session.commit()
    logger.info(f"Admin {current_user.username} changed {user.username} role to {user.role}")
    return redirect(url_for("admin.admin_users"))


@bp.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
@login_required
@admin_required
def admin_reset_password(user_id):
    user = User.query.get_or_404(user_id)
    new_password = request.form.get("new_password", "")

    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    user.set_password(new_password)
    log_audit(current_user.id, "reset_password", f"Reset password for {user.username}", "user", user_id)
    db.session.commit()
    logger.info(f"Admin {current_user.username} reset password for {user.username}")
    return redirect(url_for("admin.admin_users"))


@bp.route("/admin/import", methods=["GET", "POST"])
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
            stream = io.StringIO(file.stream.read().decode("utf-8"))
            reader = csv.DictReader(stream)

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
                existing = Customer.query.filter_by(
                    name=row.get("name", ""),
                    phone=row.get("phone", "")
                ).first()

                if existing:
                    skipped += 1
                    continue

                from datetime import datetime, timezone
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


@bp.route("/admin/import-leads", methods=["GET", "POST"])
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

            if "name" not in (reader.fieldnames or []):
                return render_template("admin/import_leads.html", error="CSV must have 'name' column")

            imported = 0
            skipped = 0

            for row in reader:
                name = row.get("name", "").strip()
                if not name:
                    skipped += 1
                    continue

                phone = row.get("phone", "").strip()
                if phone:
                    if phone.startswith("Phone Number"):
                        phone = phone.replace("Phone Number", "").strip()
                    if phone.lower() in ["call", "phone", "n/a", "none", "-", ""]:
                        phone = None
                phone = phone or None

                existing = Customer.query.filter_by(name=name, phone=phone if phone else None).first()
                if existing:
                    skipped += 1
                    continue

                from datetime import datetime, timezone
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


@bp.route("/admin/reimport-customers", methods=["POST"])
@login_required
@admin_required
def admin_reimport_customers():
    """Clear all customers and reimport from CSV"""
    import os
    from datetime import datetime, timezone

    csv_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "customers_cleaned.csv")
    if not os.path.exists(csv_file):
        return jsonify({"error": "CSV file not found"}), 404

    try:
        RouteStop.query.delete()
        Payment.query.delete()
        Customer.query.delete()
        db.session.commit()

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
        return jsonify({"error": "Failed to reimport customers"}), 500


# --- Edit User ---

@bp.route("/admin/users/<int:user_id>/edit", methods=["POST"])
@login_required
@admin_required
def admin_edit_user(user_id):
    user = User.query.get_or_404(user_id)
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()

    if not username or not email:
        return jsonify({"error": "Username and email are required"}), 400

    if username != user.username and User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 400

    if email != user.email and User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 400

    changes = []
    if username != user.username:
        changes.append(f"username {user.username} -> {username}")
        user.username = username
    if email != user.email:
        changes.append(f"email {user.email} -> {email}")
        user.email = email

    if changes:
        log_audit(current_user.id, "edit_user", ", ".join(changes), "user", user_id)
        db.session.commit()

    return redirect(url_for("admin.admin_users"))


# --- Toggle Active ---

@bp.route("/admin/users/<int:user_id>/toggle-active", methods=["POST"])
@login_required
@admin_required
def admin_toggle_active(user_id):
    if user_id == current_user.id:
        return jsonify({"error": "Cannot deactivate yourself"}), 400

    user = User.query.get_or_404(user_id)
    user.is_active_user = not user.is_active_user
    status = "activated" if user.is_active_user else "deactivated"
    log_audit(current_user.id, "toggle_active", f"{status} user {user.username}", "user", user_id)
    db.session.commit()
    logger.info(f"Admin {current_user.username} {status} user {user.username}")
    return redirect(url_for("admin.admin_users"))


# --- Audit Log ---

@bp.route("/admin/audit-log")
@login_required
@admin_required
def admin_audit_log():
    page = request.args.get("page", 1, type=int)
    action_filter = request.args.get("action", "")
    query = AuditLog.query.order_by(AuditLog.created_at.desc())
    if action_filter:
        query = query.filter(AuditLog.action == action_filter)
    logs = query.paginate(page=page, per_page=50, error_out=False)
    actions = db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    action_list = [a[0] for a in actions]
    return render_template("admin/audit_log.html", logs=logs, action_filter=action_filter, action_list=action_list)


# --- Settings ---

@bp.route("/admin/settings", methods=["GET", "POST"])
@login_required
@admin_required
def admin_settings():
    if request.method == "POST":
        for key in ["business_name", "tax_rate", "receipt_prefix", "currency_symbol"]:
            value = request.form.get(key, "").strip()
            set_setting(key, value)
        log_audit(current_user.id, "update_settings", "Updated app settings")
        db.session.commit()
        return render_template("admin/settings.html",
                               settings=_get_all_settings(),
                               success="Settings saved successfully")
    return render_template("admin/settings.html", settings=_get_all_settings())


def _get_all_settings():
    return {
        "business_name": get_setting("business_name", "Candy Route Planner"),
        "tax_rate": get_setting("tax_rate", ""),
        "receipt_prefix": get_setting("receipt_prefix", "RCP"),
        "currency_symbol": get_setting("currency_symbol", "$"),
    }


# --- Announcements ---

@bp.route("/admin/announcements", methods=["GET", "POST"])
@login_required
@admin_required
def admin_announcements():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        if not title:
            return render_template("admin/announcements.html",
                                   announcements=Announcement.query.order_by(Announcement.created_at.desc()).all(),
                                   error="Title is required")
        ann = Announcement(user_id=current_user.id, title=title, body=body)
        db.session.add(ann)
        log_audit(current_user.id, "create_announcement", f"Created announcement: {title}")
        db.session.commit()
        return redirect(url_for("admin.admin_announcements"))

    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("admin/announcements.html", announcements=announcements)


@bp.route("/admin/announcements/<int:ann_id>/toggle", methods=["POST"])
@login_required
@admin_required
def admin_toggle_announcement(ann_id):
    ann = Announcement.query.get_or_404(ann_id)
    ann.is_active = not ann.is_active
    log_audit(current_user.id, "toggle_announcement",
              f"{'Activated' if ann.is_active else 'Deactivated'} announcement: {ann.title}")
    db.session.commit()
    return redirect(url_for("admin.admin_announcements"))


@bp.route("/admin/announcements/<int:ann_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_announcement(ann_id):
    ann = Announcement.query.get_or_404(ann_id)
    log_audit(current_user.id, "delete_announcement", f"Deleted announcement: {ann.title}")
    db.session.delete(ann)
    db.session.commit()
    return redirect(url_for("admin.admin_announcements"))


# --- Per-Rep Activity ---

@bp.route("/admin/activity")
@login_required
@admin_required
def admin_activity():
    users = User.query.order_by(User.username).all()

    today = datetime.now(timezone.utc).date()
    stats = []
    for user in users:
        # Count completed route stops
        routes_completed = RouteStop.query.filter(
            RouteStop.completed == True
        ).count()  # No user_id on RouteStop yet — show global for now

        # Payments collected (also global for now, since Payment has no user_id)
        payments_total = db.session.query(db.func.sum(Payment.amount)).scalar() or 0

        stats.append({
            "user": user,
            "last_login": user.last_login,
            "is_active": user.is_active_user,
        })

    # Global stats (since we don't have per-user tracking on routes/payments yet)
    total_routes = RouteStop.query.filter(RouteStop.completed == True).count()
    total_payments = db.session.query(db.func.sum(Payment.amount)).scalar() or 0
    total_payment_count = Payment.query.count()

    return render_template("admin/activity.html", stats=stats,
                           total_routes=total_routes,
                           total_payments=f"{total_payments:.2f}",
                           total_payment_count=total_payment_count)


# --- Reassign Customers ---

@bp.route("/admin/reassign", methods=["GET", "POST"])
@login_required
@admin_required
def admin_reassign():
    users = User.query.order_by(User.username).all()

    if request.method == "POST":
        source = request.form.get("source", "")
        target = request.form.get("target", "")

        if not target:
            return render_template("admin/reassign.html", users=users, error="Select a target rep")

        target_user = User.query.get(int(target))
        if not target_user:
            return render_template("admin/reassign.html", users=users, error="Invalid target user")

        if source == "unassigned":
            customers = Customer.query.filter(Customer.assigned_to == None, Customer.status == 'active').all()
        elif source:
            customers = Customer.query.filter_by(assigned_to=int(source), status='active').all()
        else:
            return render_template("admin/reassign.html", users=users, error="Select a source")

        count = len(customers)
        for c in customers:
            c.assigned_to = target_user.id

        source_label = "unassigned" if source == "unassigned" else User.query.get(int(source)).username
        log_audit(current_user.id, "reassign_customers",
                  f"Reassigned {count} customers from {source_label} to {target_user.username}")
        db.session.commit()

        return render_template("admin/reassign.html", users=users,
                               success=f"Reassigned {count} customers to {target_user.username}")

    # Get assignment counts
    assignment_counts = {}
    assignment_counts["unassigned"] = Customer.query.filter(
        Customer.assigned_to == None, Customer.status == 'active'
    ).count()
    for user in users:
        assignment_counts[user.id] = Customer.query.filter_by(
            assigned_to=user.id, status='active'
        ).count()

    return render_template("admin/reassign.html", users=users, counts=assignment_counts)


# --- Backup ---

@bp.route("/admin/backup")
@login_required
@admin_required
def admin_backup():
    buffer = io.BytesIO()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Users (no password hashes)
        users_csv = io.StringIO()
        w = csv.writer(users_csv)
        w.writerow(["ID", "Username", "Email", "Role", "Active", "Last Login", "Created At"])
        for u in User.query.order_by(User.id).all():
            w.writerow([u.id, _s(u.username), _s(u.email), u.role, u.is_active_user,
                         u.last_login.strftime("%Y-%m-%d %H:%M:%S") if u.last_login else "",
                         u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else ""])
        zf.writestr("users.csv", users_csv.getvalue())

        # Customers
        cust_csv = io.StringIO()
        w = csv.writer(cust_csv)
        w.writerow(["ID", "Name", "City", "Address", "Phone", "Notes", "Balance",
                     "Last Visit", "Status", "Tax Exempt", "Assigned To", "Created At"])
        for c in Customer.query.order_by(Customer.id).all():
            w.writerow([c.id, _s(c.name), _s(c.city or ""), _s(c.address or ""),
                         _s(c.phone or ""), _s(c.notes or ""), f"{c.balance:.2f}",
                         c.last_visit.strftime("%Y-%m-%d") if c.last_visit else "",
                         c.status, c.tax_exempt, c.assigned_to or "",
                         c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else ""])
        zf.writestr("customers.csv", cust_csv.getvalue())

        # Payments
        pay_csv = io.StringIO()
        w = csv.writer(pay_csv)
        w.writerow(["ID", "Customer ID", "Amount", "Payment Date", "Receipt Number",
                     "Previous Balance", "Acknowledged", "Notes"])
        for p in Payment.query.order_by(Payment.id).all():
            w.writerow([p.id, p.customer_id, f"{p.amount:.2f}",
                         p.payment_date.strftime("%Y-%m-%d"),
                         p.receipt_number or "", f"{p.previous_balance:.2f}" if p.previous_balance else "",
                         p.acknowledged, _s(p.notes or "")])
        zf.writestr("payments.csv", pay_csv.getvalue())

        # Route Stops
        route_csv = io.StringIO()
        w = csv.writer(route_csv)
        w.writerow(["ID", "Customer ID", "Route Date", "Sequence", "Completed", "Notes"])
        for s in RouteStop.query.order_by(RouteStop.id).all():
            w.writerow([s.id, s.customer_id, s.route_date.strftime("%Y-%m-%d"),
                         s.sequence, s.completed, _s(s.notes or "")])
        zf.writestr("route_stops.csv", route_csv.getvalue())

        # Activity Logs
        act_csv = io.StringIO()
        w = csv.writer(act_csv)
        w.writerow(["ID", "Customer ID", "Action", "Description", "Created At"])
        for a in ActivityLog.query.order_by(ActivityLog.id).all():
            w.writerow([a.id, a.customer_id, a.action, _s(a.description or ""),
                         a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else ""])
        zf.writestr("activity_logs.csv", act_csv.getvalue())

    buffer.seek(0)
    log_audit(current_user.id, "backup", "Downloaded full database backup")
    db.session.commit()

    return Response(
        buffer.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="backup_{timestamp}.zip"'}
    )

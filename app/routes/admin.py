import csv
import io
import logging

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.helpers import admin_required
from app.models import Customer, Payment, RouteStop, User

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
    user.role = "sales" if user.role == "admin" else "admin"
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

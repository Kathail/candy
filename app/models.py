from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="sales", nullable=False)  # admin, sales
    is_active_user = db.Column(db.Boolean, default=True, nullable=False)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == "admin"


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    city = db.Column(db.String(100), index=True)
    address = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    notes = db.Column(db.Text)
    balance = db.Column(db.Numeric(10, 2), default=0.0, index=True)
    last_visit = db.Column(db.Date, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(20), default='active', nullable=False, index=True)  # lead, active, inactive
    tax_exempt = db.Column(db.Boolean, default=False, nullable=False, index=True)
    lead_source = db.Column(db.String(50))  # referral, walk-in, cold-call, website, social, other
    assigned_to = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    assigned_user = db.relationship("User", backref="customers")


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
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.Date, nullable=False, index=True)
    acknowledged = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    receipt_number = db.Column(db.String(20), unique=True, index=True)
    previous_balance = db.Column(db.Numeric(10, 2))
    customer = db.relationship("Customer", backref="payments")


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)  # visited, payment, note, balance_update, created
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    customer = db.relationship("Customer", backref="activity_logs")


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    action = db.Column(db.String(50), nullable=False)
    target_type = db.Column(db.String(50))  # user, customer, payment, setting, etc.
    target_id = db.Column(db.Integer)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user = db.relationship("User", backref="audit_logs")


class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    author = db.relationship("User", backref="announcements")


class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

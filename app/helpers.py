import io
import logging
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlparse

from flask import abort, jsonify, request
from flask_login import current_user

logger = logging.getLogger(__name__)


def is_safe_redirect_url(target):
    """Validate that a redirect target is a safe, relative URL."""
    if not target:
        return False
    parsed = urlparse(target)
    return parsed.scheme == "" and parsed.netloc == "" and target.startswith("/")


def admin_required(f):
    """Decorator that requires the current user to be an admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            if request.headers.get("Accept", "").startswith("application/json"):
                return jsonify({"error": "Admin access required"}), 403
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def sanitize_csv_value(value):
    """Prevent CSV formula injection by prefixing dangerous characters."""
    if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def generate_receipt_pdf(payment):
    """Generate a PDF receipt for a payment."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=24, spaceAfter=20, alignment=1)
    header_style = ParagraphStyle("Header", parent=styles["Normal"], fontSize=12, alignment=1)

    elements.append(Paragraph("Candy Route Planner", title_style))
    elements.append(Paragraph("Payment Receipt", header_style))
    elements.append(Spacer(1, 30))

    new_balance = max(0, (payment.previous_balance or 0) - payment.amount)
    customer_name = payment.customer.name if payment.customer else "N/A"
    customer_city = payment.customer.city if payment.customer else "N/A"

    receipt_data = [
        ["Receipt Number:", payment.receipt_number or "N/A"],
        ["Date:", payment.payment_date.strftime("%B %d, %Y")],
        ["", ""],
        ["Customer:", customer_name],
        ["City:", customer_city],
        ["", ""],
        ["Previous Balance:", f"${payment.previous_balance:.2f}" if payment.previous_balance is not None else "N/A"],
        ["Payment Amount:", f"${payment.amount:.2f}"],
        ["New Balance:", f"${new_balance:.2f}"],
    ]

    if payment.notes:
        receipt_data.extend([["", ""], ["Notes:", payment.notes]])

    table = Table(receipt_data, colWidths=[2 * inch, 4 * inch])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("BACKGROUND", (0, 7), (-1, 7), colors.Color(0.9, 1, 0.9)),
        ("FONTNAME", (0, 7), (-1, 7), "Helvetica-Bold"),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 40))

    footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontSize=10, textColor=colors.gray, alignment=1)
    elements.append(Paragraph("Thank you for your payment!", footer_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(f"Generated on {datetime.now(timezone.utc).strftime('%B %d, %Y at %I:%M %p')}", footer_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer

import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, render_template, request
from flask_login import login_required

from app import db
from app.helpers import sanitize_csv_value as _s
from app.models import Customer, Payment

bp = Blueprint("reports", __name__)


# ---- Shared helpers ----

def _today():
    return datetime.now(timezone.utc).date()


def _date_range(period=None, start_str=None, end_str=None):
    """Parse period name or date strings into (start, end) date tuple."""
    today = _today()
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    elif period == "month":
        start = today.replace(day=1)
        end = (today.replace(month=today.month % 12 + 1, day=1) if today.month < 12
               else today.replace(year=today.year + 1, month=1, day=1)) - timedelta(days=1)
        return start, end
    elif period == "quarter":
        q = (today.month - 1) // 3
        start = today.replace(month=q * 3 + 1, day=1)
        end = (today.replace(month=(q + 1) * 3 + 1, day=1) if q < 3
               else today.replace(year=today.year + 1, month=1, day=1)) - timedelta(days=1)
        return start, end
    elif period == "year":
        return today.replace(month=1, day=1), today.replace(month=12, day=31)
    elif start_str and end_str:
        try:
            return datetime.strptime(start_str, "%Y-%m-%d").date(), datetime.strptime(end_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    return None, None


def _period_label(start, end):
    if start and end:
        return f"{start.strftime('%B %d, %Y')} to {end.strftime('%B %d, %Y')}"
    return "All Time"


def _csv_response(output, filename):
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _pdf_response(buffer, filename):
    buffer.seek(0)
    return Response(buffer.getvalue(), mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _pdf_setup(title, start=None, end=None):
    """Common PDF boilerplate — returns (doc, buffer, elements, styles)."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=18, spaceAfter=10, alignment=1)
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=12, spaceAfter=20, alignment=1)

    elements.append(Paragraph(title, title_style))
    elements.append(Paragraph(_period_label(start, end), subtitle_style))
    elements.append(Spacer(1, 20))

    return doc, buf, elements, styles


def _pdf_table(data, col_widths, header_color=None):
    """Build a styled ReportLab table."""
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import Table, TableStyle

    if not header_color:
        header_color = colors.Color(0.2, 0.4, 0.6)

    table = Table(data, colWidths=[w * inch for w in col_widths])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -2), 0.5, colors.grey),
        ("BACKGROUND", (0, -1), (-1, -1), colors.Color(0.9, 0.9, 0.9)),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _filename(prefix, start, end, ext):
    s = start.strftime("%Y%m%d") if start else "all"
    e = end.strftime("%Y%m%d") if end else "time"
    return f"{prefix}_{s}_{e}.{ext}"


def _get_period_stats(start, end):
    payments = Payment.query.filter(Payment.payment_date >= start, Payment.payment_date <= end).all()
    return {"total": sum(p.amount for p in payments), "count": len(payments)}


def _get_tax_exempt_stats(start, end, tax_exempt_ids):
    if not tax_exempt_ids:
        return {"total": 0, "count": 0, "payments": []}
    payments = Payment.query.filter(
        Payment.customer_id.in_(tax_exempt_ids),
        Payment.payment_date >= start, Payment.payment_date <= end
    ).order_by(Payment.payment_date.desc()).all()
    return {"total": sum(p.amount for p in payments), "count": len(payments), "payments": payments}


# ---- Routes ----

@bp.route("/reports")
@login_required
def reports():
    today = _today()
    week_start, week_end = _date_range("week")
    month_start, month_end = _date_range("month")
    quarter_start, quarter_end = _date_range("quarter")
    year_start, year_end = _date_range("year")

    tax_exempt_customers = Customer.query.filter_by(tax_exempt=True, status="active").all()
    tax_exempt_ids = [c.id for c in tax_exempt_customers]

    return render_template(
        "reports.html",
        today=today,
        week_start=week_start, week_end=week_end,
        month_start=month_start, month_end=month_end,
        quarter_start=quarter_start, quarter_end=quarter_end,
        year_start=year_start, year_end=year_end,
        week_stats=_get_period_stats(week_start, week_end),
        month_stats=_get_period_stats(month_start, month_end),
        quarter_stats=_get_period_stats(quarter_start, quarter_end),
        year_stats=_get_period_stats(year_start, year_end),
        tax_exempt_customers=tax_exempt_customers,
        tax_exempt_week=_get_tax_exempt_stats(week_start, week_end, tax_exempt_ids),
        tax_exempt_month=_get_tax_exempt_stats(month_start, month_end, tax_exempt_ids),
        tax_exempt_quarter=_get_tax_exempt_stats(quarter_start, quarter_end, tax_exempt_ids),
        tax_exempt_year=_get_tax_exempt_stats(year_start, year_end, tax_exempt_ids),
    )


@bp.route("/reports/export")
@login_required
def export_report():
    report_type = request.args.get("type", "payments")
    format_type = request.args.get("format", "csv")
    start, end = _date_range(
        period=request.args.get("period"),
        start_str=request.args.get("start"),
        end_str=request.args.get("end"),
    )

    if report_type == "payments":
        payments = _get_payments(start, end)
        return _payments_pdf(payments, start, end) if format_type == "pdf" else _payments_csv(payments, start, end)

    elif report_type == "summary":
        payments = _get_payments(start, end)
        return _summary_pdf(payments, start, end) if format_type == "pdf" else _summary_csv(payments, start, end)

    elif report_type == "balances":
        customers = Customer.query.filter(Customer.balance > 0, Customer.status == "active").order_by(Customer.balance.desc()).all()
        return _balances_pdf(customers, start, end) if format_type == "pdf" else _balances_csv(customers)

    elif report_type == "tax_exempt":
        te_customers = Customer.query.filter_by(tax_exempt=True, status="active").all()
        te_ids = [c.id for c in te_customers]
        query = Payment.query.options(db.joinedload(Payment.customer)).filter(
            Payment.customer_id.in_(te_ids) if te_ids else False
        )
        if start and end:
            query = query.filter(Payment.payment_date >= start, Payment.payment_date <= end)
        payments = query.order_by(Payment.payment_date.desc()).all()

        if format_type == "pdf":
            return _tax_exempt_pdf(payments, te_customers, start, end)
        elif format_type == "excel":
            return _tax_exempt_excel(payments, te_customers, start, end)
        else:
            return _tax_exempt_csv(payments, te_customers, start, end)

    return "Invalid report type", 400


def _get_payments(start, end):
    query = Payment.query.options(db.joinedload(Payment.customer))
    if start and end:
        query = query.filter(Payment.payment_date >= start, Payment.payment_date <= end)
    return query.order_by(Payment.payment_date.desc()).all()


# ---- CSV Generators ----

def _payments_csv(payments, start, end):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([f"Payment Report - {_period_label(start, end)}"])
    w.writerow([])
    w.writerow(["Date", "Receipt #", "Customer", "City", "Amount", "Previous Balance", "Notes"])
    total = 0
    for p in payments:
        w.writerow([p.payment_date.strftime("%Y-%m-%d"), p.receipt_number or "",
                     _s(p.customer.name if p.customer else ""), _s(p.customer.city if p.customer else ""),
                     f"{p.amount:.2f}", f"{p.previous_balance:.2f}" if p.previous_balance else "", _s(p.notes or "")])
        total += float(p.amount)
    w.writerow([])
    w.writerow(["", "", "", "TOTAL:", f"${total:.2f}", "", ""])
    return _csv_response(out, _filename("payments", start, end, "csv"))


def _summary_csv(payments, start, end):
    out = io.StringIO()
    w = csv.writer(out)
    total = sum(float(p.amount) for p in payments)
    w.writerow([f"Financial Summary - {_period_label(start, end)}"])
    w.writerow([])
    w.writerow(["Total Payments", len(payments)])
    w.writerow(["Total Collected", f"${total:.2f}"])
    w.writerow(["Average Payment", f"${(total / len(payments)):.2f}" if payments else "$0.00"])
    w.writerow([])

    for label, key_fn in [("BY CUSTOMER", lambda p: _s(p.customer.name if p.customer else "Unknown")),
                           ("BY CITY", lambda p: _s(p.customer.city if p.customer and p.customer.city else "Unknown"))]:
        groups = defaultdict(lambda: {"count": 0, "total": 0.0})
        for p in payments:
            k = key_fn(p)
            groups[k]["count"] += 1
            groups[k]["total"] += float(p.amount)
        w.writerow([label])
        w.writerow(["Name", "Count", "Total"])
        for name, data in sorted(groups.items(), key=lambda x: x[1]["total"], reverse=True):
            w.writerow([name, data["count"], f"${data['total']:.2f}"])
        w.writerow([])

    return _csv_response(out, _filename("summary", start, end, "csv"))


def _balances_csv(customers):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([f"Outstanding Balances - {_today().strftime('%Y-%m-%d')}"])
    w.writerow([])
    w.writerow(["Customer", "City", "Phone", "Balance", "Last Visit"])
    total = 0
    for c in customers:
        w.writerow([_s(c.name), _s(c.city or ""), _s(c.phone or ""), f"${c.balance:.2f}",
                     c.last_visit.strftime("%Y-%m-%d") if c.last_visit else "Never"])
        total += float(c.balance)
    w.writerow([])
    w.writerow(["", "", "TOTAL:", f"${total:.2f}", ""])
    return _csv_response(out, f"balances_{_today().strftime('%Y%m%d')}.csv")


def _tax_exempt_csv(payments, customers, start, end):
    out = io.StringIO()
    w = csv.writer(out)
    total = sum(float(p.amount) for p in payments)
    w.writerow([f"Tax Exempt Sales - {_period_label(start, end)}"])
    w.writerow([])
    w.writerow(["Tax Exempt Customers:", len(customers)])
    w.writerow(["Total Transactions:", len(payments)])
    w.writerow(["Total Tax Exempt Sales:", f"${total:.2f}"])
    w.writerow([])
    w.writerow(["TAX EXEMPT CUSTOMERS"])
    w.writerow(["Name", "City", "Phone", "Address"])
    for c in customers:
        w.writerow([_s(c.name), _s(c.city or ""), _s(c.phone or ""), _s(c.address or "")])
    w.writerow([])
    w.writerow(["TRANSACTIONS"])
    w.writerow(["Date", "Receipt #", "Customer", "City", "Amount", "Notes"])
    for p in payments:
        w.writerow([p.payment_date.strftime("%Y-%m-%d"), p.receipt_number or "",
                     _s(p.customer.name if p.customer else ""), _s(p.customer.city if p.customer else ""),
                     f"${p.amount:.2f}", _s(p.notes or "")])
    w.writerow([])
    w.writerow(["", "", "", "TOTAL:", f"${total:.2f}", ""])
    return _csv_response(out, _filename("tax_exempt", start, end, "csv"))


# ---- PDF Generators ----

def _payments_pdf(payments, start, end):
    from reportlab.platypus import Paragraph, Spacer
    doc, buf, elements, styles = _pdf_setup("Payment Report", start, end)
    total = sum(float(p.amount) for p in payments)
    elements.append(Paragraph(f"<b>Total Payments:</b> {len(payments)} &nbsp; <b>Collected:</b> ${total:.2f}", styles["Normal"]))
    elements.append(Spacer(1, 20))
    if payments:
        data = [["Date", "Receipt #", "Customer", "City", "Amount"]]
        for p in payments:
            data.append([p.payment_date.strftime("%m/%d/%Y"), p.receipt_number or "-",
                         (p.customer.name if p.customer else "-")[:25], (p.customer.city if p.customer else "-")[:15],
                         f"${p.amount:.2f}"])
        data.append(["", "", "", "TOTAL:", f"${total:.2f}"])
        elements.append(_pdf_table(data, [1, 1, 2.5, 1.5, 1]))
    doc.build(elements)
    return _pdf_response(buf, _filename("payments", start, end, "pdf"))


def _summary_pdf(payments, start, end):
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer
    doc, buf, elements, styles = _pdf_setup("Financial Summary", start, end)
    total = sum(float(p.amount) for p in payments)
    avg = total / len(payments) if payments else 0
    section = ParagraphStyle("Section", parent=styles["Heading2"], fontSize=14, spaceBefore=20, spaceAfter=10)

    elements.append(Paragraph(f"<b>Total:</b> {len(payments)} payments &nbsp; <b>Collected:</b> ${total:.2f} &nbsp; <b>Avg:</b> ${avg:.2f}", styles["Normal"]))
    elements.append(Spacer(1, 20))

    by_customer = defaultdict(lambda: {"count": 0, "total": 0.0})
    for p in payments:
        name = p.customer.name if p.customer else "Unknown"
        by_customer[name]["count"] += 1
        by_customer[name]["total"] += float(p.amount)

    elements.append(Paragraph("Collections by Customer", section))
    data = [["Customer", "Payments", "Total"]]
    for name, d in sorted(by_customer.items(), key=lambda x: x[1]["total"], reverse=True)[:15]:
        data.append([name[:30], str(d["count"]), f"${d['total']:.2f}"])
    elements.append(_pdf_table(data, [3.5, 1, 1.5]))

    doc.build(elements)
    return _pdf_response(buf, _filename("summary", start, end, "pdf"))


def _balances_pdf(customers, start, end):
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Spacer
    doc, buf, elements, styles = _pdf_setup("Outstanding Balances", start, end)
    total = sum(float(c.balance) for c in customers)
    elements.append(Paragraph(f"<b>Customers:</b> {len(customers)} &nbsp; <b>Outstanding:</b> ${total:.2f}", styles["Normal"]))
    elements.append(Spacer(1, 20))
    if customers:
        data = [["Customer", "City", "Phone", "Balance", "Last Visit"]]
        for c in customers:
            data.append([c.name[:25], (c.city or "-")[:15], c.phone or "-", f"${c.balance:.2f}",
                         c.last_visit.strftime("%m/%d/%Y") if c.last_visit else "Never"])
        data.append(["", "", "TOTAL:", f"${total:.2f}", ""])
        elements.append(_pdf_table(data, [2, 1.2, 1.2, 1, 1], header_color=colors.Color(0.6, 0.2, 0.2)))
    doc.build(elements)
    return _pdf_response(buf, f"balances_{_today().strftime('%Y%m%d')}.pdf")


def _tax_exempt_pdf(payments, customers, start, end):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer
    doc, buf, elements, styles = _pdf_setup("Tax Exempt Sales", start, end)
    total = sum(float(p.amount) for p in payments)
    section = ParagraphStyle("Section", parent=styles["Heading2"], fontSize=14, spaceAfter=10, spaceBefore=20)

    elements.append(Paragraph(f"<b>Customers:</b> {len(customers)} &nbsp; <b>Transactions:</b> {len(payments)} &nbsp; <b>Total:</b> ${total:.2f}", styles["Normal"]))
    elements.append(Spacer(1, 20))

    gold = colors.Color(0.8, 0.6, 0.2)
    if customers:
        elements.append(Paragraph("Tax Exempt Customers", section))
        data = [["Name", "City", "Phone"]]
        for c in customers:
            data.append([c.name[:30], (c.city or "-")[:20], c.phone or "-"])
        elements.append(_pdf_table(data, [2.5, 2, 1.5], header_color=gold))
        elements.append(Spacer(1, 20))

    if payments:
        elements.append(Paragraph("Transactions", section))
        data = [["Date", "Receipt #", "Customer", "Amount"]]
        for p in payments:
            data.append([p.payment_date.strftime("%m/%d/%Y"), p.receipt_number or "-",
                         (p.customer.name if p.customer else "-")[:25], f"${p.amount:.2f}"])
        data.append(["", "", "TOTAL:", f"${total:.2f}"])
        elements.append(_pdf_table(data, [1.2, 1.2, 2.5, 1.2], header_color=gold))

    doc.build(elements)
    return _pdf_response(buf, _filename("tax_exempt", start, end, "pdf"))


def _tax_exempt_excel(payments, customers, start, end):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side

    wb = Workbook()
    gold = PatternFill(start_color="D4A84B", end_color="D4A84B", fill_type="solid")
    hfont = Font(bold=True, color="FFFFFF")
    border = Border(left=Side(style="thin"), right=Side(style="thin"), top=Side(style="thin"), bottom=Side(style="thin"))
    total = sum(float(p.amount) for p in payments)

    # Summary sheet
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = "Tax Exempt Sales Report"
    ws["A1"].font = Font(bold=True, size=16)
    ws["A2"] = _period_label(start, end)
    for r, (label, val) in enumerate([("Tax Exempt Customers:", len(customers)),
                                       ("Total Transactions:", len(payments)),
                                       ("Total Tax Exempt Sales:", f"${total:.2f}")], start=4):
        ws[f"A{r}"] = label
        ws[f"A{r}"].font = Font(bold=True)
        ws[f"B{r}"] = val
    ws.column_dimensions["A"].width = 25
    ws.column_dimensions["B"].width = 20

    # Customers sheet
    wsc = wb.create_sheet("Customers")
    for col, h in enumerate(["Name", "City", "Phone", "Address"], 1):
        c = wsc.cell(row=1, column=col, value=h)
        c.fill, c.font, c.border = gold, hfont, border
    for row, c in enumerate(customers, 2):
        for col, val in enumerate([c.name, c.city or "", c.phone or "", c.address or ""], 1):
            wsc.cell(row=row, column=col, value=val).border = border
    for col, w in zip("ABCD", [30, 20, 15, 40]):
        wsc.column_dimensions[col].width = w

    # Transactions sheet
    wst = wb.create_sheet("Transactions")
    for col, h in enumerate(["Date", "Receipt #", "Customer", "City", "Amount", "Notes"], 1):
        c = wst.cell(row=1, column=col, value=h)
        c.fill, c.font, c.border = gold, hfont, border
    for row, p in enumerate(payments, 2):
        for col, val in enumerate([p.payment_date.strftime("%Y-%m-%d"), p.receipt_number or "",
                                    p.customer.name if p.customer else "", p.customer.city if p.customer else "",
                                    float(p.amount), p.notes or ""], 1):
            cell = wst.cell(row=row, column=col, value=val)
            cell.border = border
            if col == 5:
                cell.number_format = "$#,##0.00"
    tr = len(payments) + 2
    wst.cell(row=tr, column=4, value="TOTAL:").font = Font(bold=True)
    wst.cell(row=tr, column=5, value=total).font = Font(bold=True)
    wst.cell(row=tr, column=5).number_format = "$#,##0.00"
    for col, w in zip("ABCDEF", [12, 12, 25, 15, 12, 30]):
        wst.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(buf.getvalue(),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{_filename("tax_exempt", start, end, "xlsx")}"'})

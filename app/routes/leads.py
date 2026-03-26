import logging
from datetime import datetime, timezone

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.models import Customer

logger = logging.getLogger(__name__)
bp = Blueprint("leads", __name__)


@bp.route("/leads")
@login_required
def leads():
    query = request.args.get("query", "")
    sort_by = request.args.get("sort", "name")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
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
            now=datetime.now(timezone.utc).date(),
        )

    return render_template(
        "leads.html",
        leads=leads_list,
        pagination=pagination,
        total_leads=total_leads,
        now=datetime.now(timezone.utc).date(),
    )


@bp.route("/leads/add", methods=["POST"])
@login_required
def lead_add():
    name = request.form.get("name")
    phone = request.form.get("phone")
    address = request.form.get("address")
    city = request.form.get("city")
    notes = request.form.get("notes")
    lead_source = request.form.get("lead_source")

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
        lead_source=lead_source or None,
    )

    db.session.add(new_lead)
    db.session.commit()
    logger.info(f"Lead added: {name} (source: {lead_source})")

    return redirect(url_for("leads.leads"))


@bp.route("/leads/<int:lead_id>/edit")
@login_required
def lead_edit(lead_id):
    lead = Customer.query.get_or_404(lead_id)
    if lead.status != 'lead':
        return "Not a lead", 400
    return render_template(
        "partials/lead_edit_modal.html",
        lead=lead,
    )


@bp.route("/leads/<int:lead_id>/update", methods=["POST"])
@login_required
def lead_update(lead_id):
    lead = Customer.query.get_or_404(lead_id)

    lead.name = request.form.get("name") or lead.name
    lead.phone = request.form.get("phone") or None
    lead.address = request.form.get("address") or None
    lead.city = request.form.get("city") or None
    lead.notes = request.form.get("notes") or None
    lead.lead_source = request.form.get("lead_source") or None

    db.session.commit()
    logger.info(f"Lead updated: {lead.name}")

    return redirect(url_for("leads.leads"))


@bp.route("/leads/<int:lead_id>/convert", methods=["POST"])
@login_required
def lead_convert(lead_id):
    lead = Customer.query.get_or_404(lead_id)
    if lead.status != 'lead':
        return "Not a lead", 400

    lead.status = 'active'
    db.session.commit()
    logger.info(f"Lead converted to customer: {lead.name}")

    return redirect(url_for("leads.leads"))


@bp.route("/leads/<int:lead_id>/delete", methods=["POST"])
@login_required
def lead_delete(lead_id):
    lead = Customer.query.get_or_404(lead_id)
    if lead.status != 'lead':
        return "Not a lead", 400

    lead_name = lead.name
    db.session.delete(lead)
    db.session.commit()
    logger.info(f"Lead deleted: {lead_name}")

    return redirect(url_for("leads.leads"))

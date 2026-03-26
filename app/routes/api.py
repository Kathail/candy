import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import login_required

from app import db, limiter
from app.models import Customer, Payment, RouteStop

logger = logging.getLogger(__name__)
bp = Blueprint("api", __name__)
api_limit = limiter.shared_limit("60/minute", scope="api")


@bp.route("/api/route/today")
@api_limit
@login_required
def api_route_today():
    """JSON API endpoint for today's route - used by offline mode"""
    today = datetime.now(timezone.utc).date()
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


@bp.route("/api/sync", methods=["POST"])
@api_limit
@login_required
def api_sync():
    """Process a batch of queued offline payments."""
    data = request.get_json(silent=True)
    if not data or not isinstance(data.get("payments"), list):
        return jsonify({"error": "Expected JSON with a 'payments' array"}), 400

    payments = data["payments"]
    if len(payments) > 100:
        return jsonify({"error": "Too many payments in a single batch (max 100)"}), 400

    results = []
    for idx, item in enumerate(payments):
        result = {"index": idx, "success": False}
        try:
            customer_id = item.get("customer_id")
            amount_raw = item.get("amount")
            payment_date_str = item.get("payment_date")
            notes = item.get("notes")

            if customer_id is None or amount_raw is None:
                result["error"] = "Missing required fields (customer_id, amount)"
                results.append(result)
                continue

            try:
                customer_id = int(customer_id)
            except (TypeError, ValueError):
                result["error"] = "Invalid customer_id"
                results.append(result)
                continue

            try:
                amount = float(amount_raw)
            except (TypeError, ValueError):
                result["error"] = "Invalid amount"
                results.append(result)
                continue

            if amount <= 0:
                result["error"] = "Amount must be positive"
                results.append(result)
                continue

            if amount > 1_000_000:
                result["error"] = "Amount exceeds maximum allowed"
                results.append(result)
                continue

            if payment_date_str:
                try:
                    payment_date = datetime.strptime(str(payment_date_str), "%Y-%m-%d").date()
                except ValueError:
                    result["error"] = "Invalid payment_date format (expected YYYY-MM-DD)"
                    results.append(result)
                    continue
            else:
                payment_date = datetime.now(timezone.utc).date()

            if notes and len(str(notes)) > 500:
                result["error"] = "Notes too long (max 500 characters)"
                results.append(result)
                continue

            customer = Customer.query.get(customer_id)
            if not customer:
                result["error"] = f"Customer {customer_id} not found"
                results.append(result)
                continue

            previous_balance = customer.balance

            today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
            max_receipt = db.session.query(db.func.max(Payment.receipt_number)).filter(
                Payment.receipt_number.like(f"RCP-{today_str}-%")
            ).scalar()
            next_seq = int(max_receipt.split("-")[-1]) + 1 if max_receipt else 1
            receipt_number = f"RCP-{today_str}-{next_seq:04d}"

            new_payment = Payment(
                customer_id=customer.id,
                amount=amount,
                payment_date=payment_date,
                notes=str(notes).strip() if notes else None,
                receipt_number=receipt_number,
                previous_balance=previous_balance,
            )

            customer.balance = max(0, customer.balance - amount)

            db.session.add(new_payment)
            db.session.commit()

            logger.info(f"Sync payment: ${amount} from {customer.name} (Receipt: {receipt_number})")
            result["success"] = True
            result["receipt_number"] = receipt_number

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing sync payment index {idx}: {str(e)}")
            result["error"] = "Server error processing payment"

        results.append(result)

    succeeded = sum(1 for r in results if r["success"])
    return jsonify({
        "results": results,
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
    })

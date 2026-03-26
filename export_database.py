#!/usr/bin/env python3
"""
Export entire database to JSON for transfer to another instance
Usage: python export_database.py [output_file.json]
"""

import json
import sys
from datetime import datetime

from app import create_app, db
from app.models import Customer, Payment, RouteStop

app = create_app()


def export_database(output_file="database_export.json"):
    """Export all data to JSON file"""
    with app.app_context():
        print("Exporting database...")

        data = {
            "exported_at": datetime.now().isoformat(),
            "customers": [],
            "payments": [],
            "route_stops": []
        }

        # Export all customers (including leads and inactive)
        customers = Customer.query.all()
        for c in customers:
            data["customers"].append({
                "id": c.id,
                "name": c.name,
                "city": c.city,
                "address": c.address,
                "phone": c.phone,
                "notes": c.notes,
                "balance": float(c.balance) if c.balance else 0.0,
                "last_visit": c.last_visit.isoformat() if c.last_visit else None,
                "status": c.status,
                "tax_exempt": c.tax_exempt,
                "lead_source": c.lead_source,
                "created_at": c.created_at.isoformat() if c.created_at else None
            })

        # Export payments
        payments = Payment.query.all()
        for p in payments:
            data["payments"].append({
                "id": p.id,
                "customer_id": p.customer_id,
                "amount": float(p.amount),
                "payment_date": p.payment_date.isoformat() if p.payment_date else None,
                "notes": p.notes,
                "acknowledged": p.acknowledged
            })

        # Export route stops
        stops = RouteStop.query.all()
        for s in stops:
            data["route_stops"].append({
                "id": s.id,
                "customer_id": s.customer_id,
                "route_date": s.route_date.isoformat() if s.route_date else None,
                "sequence": s.sequence,
                "completed": s.completed,
                "notes": s.notes
            })

        # Write to file
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"\nExported to {output_file}:")
        print(f"  - {len(data['customers'])} customers (including leads)")
        print(f"  - {len(data['payments'])} payments")
        print(f"  - {len(data['route_stops'])} route stops")

        # Summary by status
        status_counts = {}
        for c in data["customers"]:
            status = c["status"] or "active"
            status_counts[status] = status_counts.get(status, 0) + 1

        print(f"\nBy status:")
        for status, count in sorted(status_counts.items()):
            print(f"  - {status}: {count}")


if __name__ == "__main__":
    output_file = sys.argv[1] if len(sys.argv) > 1 else "database_export.json"
    export_database(output_file)

#!/usr/bin/env python3
"""
Import database from JSON export file
Usage: python import_database.py database_export.json [--clear]
"""

import json
import sys
from datetime import datetime

from app import create_app, db
from app.models import Customer, Payment, RouteStop

app = create_app()


def clear_database():
    """Delete all existing data"""
    with app.app_context():
        print("Clearing existing data...")
        RouteStop.query.delete()
        Payment.query.delete()
        Customer.query.delete()
        db.session.commit()
        print("Database cleared.")


def import_database(input_file, clear_first=False):
    """Import all data from JSON file"""
    with app.app_context():
        # Load JSON
        print(f"Loading {input_file}...")
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"Export from: {data.get('exported_at', 'unknown')}")
        print(f"Contains: {len(data.get('customers', []))} customers, "
              f"{len(data.get('payments', []))} payments, "
              f"{len(data.get('route_stops', []))} stops")

        if clear_first:
            clear_database()

        # Map old IDs to new IDs
        customer_id_map = {}

        # Import customers
        print("\nImporting customers...")
        for c in data.get("customers", []):
            # Check if already exists (by name + phone)
            existing = Customer.query.filter_by(name=c["name"], phone=c.get("phone")).first()
            if existing:
                customer_id_map[c["id"]] = existing.id
                continue

            customer = Customer(
                name=c["name"],
                city=c.get("city"),
                address=c.get("address"),
                phone=c.get("phone"),
                notes=c.get("notes"),
                balance=c.get("balance", 0.0),
                last_visit=datetime.fromisoformat(c["last_visit"]).date() if c.get("last_visit") else None,
                status=c.get("status", "active"),
                tax_exempt=c.get("tax_exempt", False),
                lead_source=c.get("lead_source"),
                created_at=datetime.fromisoformat(c["created_at"]) if c.get("created_at") else datetime.now()
            )
            db.session.add(customer)
            db.session.flush()  # Get the new ID
            customer_id_map[c["id"]] = customer.id

        db.session.commit()

        # Count by status
        status_counts = {}
        for c in data.get("customers", []):
            status = c.get("status", "active")
            status_counts[status] = status_counts.get(status, 0) + 1

        print(f"  Imported customers by status:")
        for status, count in sorted(status_counts.items()):
            print(f"    - {status}: {count}")

        # Import payments
        print("\nImporting payments...")
        imported_payments = 0
        for p in data.get("payments", []):
            old_customer_id = p["customer_id"]
            new_customer_id = customer_id_map.get(old_customer_id)

            if not new_customer_id:
                continue  # Customer not found/imported

            payment = Payment(
                customer_id=new_customer_id,
                amount=p["amount"],
                payment_date=datetime.fromisoformat(p["payment_date"]).date() if p.get("payment_date") else None,
                notes=p.get("notes"),
                acknowledged=p.get("acknowledged", False)
            )
            db.session.add(payment)
            imported_payments += 1

        db.session.commit()
        print(f"  Imported {imported_payments} payments")

        # Import route stops
        print("\nImporting route stops...")
        imported_stops = 0
        for s in data.get("route_stops", []):
            old_customer_id = s["customer_id"]
            new_customer_id = customer_id_map.get(old_customer_id)

            if not new_customer_id:
                continue  # Customer not found/imported

            stop = RouteStop(
                customer_id=new_customer_id,
                route_date=datetime.fromisoformat(s["route_date"]).date() if s.get("route_date") else None,
                sequence=s.get("sequence", 0),
                completed=s.get("completed", False),
                notes=s.get("notes")
            )
            db.session.add(stop)
            imported_stops += 1

        db.session.commit()
        print(f"  Imported {imported_stops} route stops")

        # Final counts
        print(f"\nDatabase now contains:")
        print(f"  - {Customer.query.count()} total customers")
        print(f"  - {Customer.query.filter_by(status='active').count()} active customers")
        print(f"  - {Customer.query.filter_by(status='lead').count()} leads")
        print(f"  - {Customer.query.filter_by(status='inactive').count()} inactive")
        print(f"  - {Payment.query.count()} payments")
        print(f"  - {RouteStop.query.count()} route stops")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_database.py database_export.json [--clear]")
        print("\nOptions:")
        print("  --clear    Clear existing data before import")
        sys.exit(1)

    input_file = sys.argv[1]
    clear_first = "--clear" in sys.argv

    if clear_first:
        confirm = input("This will DELETE ALL existing data before import. Continue? (yes/no): ")
        if confirm.lower() != "yes":
            print("Cancelled.")
            sys.exit(0)

    import_database(input_file, clear_first)
    print("\nImport complete!")

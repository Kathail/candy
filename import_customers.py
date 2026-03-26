#!/usr/bin/env python3
"""
Import customers from CSV file.
Usage: python3 import_customers.py customers.csv
       python3 import_customers.py customers.csv --no-clear
       python3 import_customers.py customers.csv --clear-only
"""

import csv
import os
import sys
from datetime import datetime, timezone

from app import create_app, db
from app.models import Customer, Payment, RouteStop

app = create_app()


def normalize(value):
    if not value:
        return None
    value = str(value).strip()
    return value if value else None


def clear_customers():
    """Delete all existing customers and related data"""
    with app.app_context():
        print("Clearing existing data...")
        RouteStop.query.delete()
        Payment.query.delete()
        Customer.query.delete()
        db.session.commit()
        print("All customer data cleared.")


def import_customers(csv_file):
    """Import customers from CSV"""
    if not os.path.exists(csv_file):
        print(f"ERROR: CSV file not found: {csv_file}")
        sys.exit(1)

    with app.app_context():
        inserted = 0
        skipped = 0

        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                name = normalize(row.get("name") or row.get("Name"))
                if not name:
                    skipped += 1
                    continue

                address = normalize(row.get("address") or row.get("Address"))
                phone = normalize(row.get("phone") or row.get("Phone"))
                city = normalize(row.get("city") or row.get("City"))

                # Build notes from various fields
                notes_parts = []
                if normalize(row.get("Source")):
                    notes_parts.append(f"Source: {row['Source']}")
                if normalize(row.get("notes") or row.get("Notes")):
                    notes_parts.append(row.get("notes") or row.get("Notes"))
                notes = "\n".join(notes_parts) if notes_parts else normalize(row.get("notes"))

                # Dedupe by name + phone
                existing = Customer.query.filter_by(name=name, phone=phone).first()
                if existing:
                    skipped += 1
                    continue

                customer = Customer(
                    name=name,
                    address=address,
                    city=city,
                    phone=phone,
                    notes=notes,
                    balance=float(row.get("balance", 0) or 0),
                    created_at=datetime.now(timezone.utc),
                )
                db.session.add(customer)
                inserted += 1

                if inserted % 50 == 0:
                    db.session.commit()

        db.session.commit()
        print(f"Import complete. Inserted: {inserted}, Skipped: {skipped}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 import_customers.py <csv_file> [--no-clear|--clear-only]")
        sys.exit(1)

    csv_file = sys.argv[1]
    flag = sys.argv[2] if len(sys.argv) > 2 else None

    if flag == "--clear-only":
        clear_customers()
    elif flag == "--no-clear":
        import_customers(csv_file)
    else:
        clear_customers()
        import_customers(csv_file)


if __name__ == "__main__":
    main()

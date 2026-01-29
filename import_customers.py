#!/usr/bin/env python3
"""
Clear existing customers and import cleaned CSV
Usage: python3 import_customers.py customers_cleaned.csv
"""

import csv
import sys
from datetime import datetime

# Import your Flask app
from app import Customer, Payment, RouteStop, app, db


def clear_customers():
    """Delete all existing customers and related data"""
    with app.app_context():
        print("🗑️  Clearing existing data...")

        # Delete in order (foreign key constraints)
        deleted_stops = RouteStop.query.delete()
        deleted_payments = Payment.query.delete()
        deleted_customers = Customer.query.delete()

        db.session.commit()

        print(f"   Deleted {deleted_customers} customers")
        print(f"   Deleted {deleted_stops} route stops")
        print(f"   Deleted {deleted_payments} payments")


def import_customers(csv_file):
    """Import customers from cleaned CSV"""
    with app.app_context():
        print(f"\n📥 Importing customers from {csv_file}...")

        imported = 0
        skipped = 0

        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Check if customer already exists (by name + phone)
                existing = Customer.query.filter_by(
                    name=row["name"], phone=row["phone"]
                ).first()

                if existing:
                    skipped += 1
                    continue

                customer = Customer(
                    name=row["name"],
                    address=row["address"],
                    city=row["city"],
                    phone=row["phone"],
                    balance=0.0,
                    created_at=datetime.utcnow(),
                )

                db.session.add(customer)
                imported += 1

                # Commit in batches of 50
                if imported % 50 == 0:
                    db.session.commit()
                    print(f"   Imported {imported} customers...")

        # Final commit
        db.session.commit()

        print(f"\n✅ Import complete!")
        print(f"   Imported: {imported} customers")
        print(f"   Skipped: {skipped} duplicates")
        print(f"   Total in database: {Customer.query.count()}")

        # Show city breakdown
        print(f"\n📍 Customers by city:")
        from collections import defaultdict

        cities = defaultdict(int)
        for customer in Customer.query.all():
            cities[customer.city or "Unknown"] += 1

        for city, count in sorted(cities.items(), key=lambda x: -x[1])[:15]:
            print(f"   {city:25} {count:3}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 import_customers.py customers_cleaned.csv")
        print("\nOptions:")
        print("  --clear-only    Just clear existing data (no import)")
        print("  --no-clear      Import without clearing (skip duplicates)")
        sys.exit(1)

    csv_file = sys.argv[1]

    if "--clear-only" in sys.argv:
        confirm = input(
            "⚠️  This will DELETE ALL customers, routes, and payments. Are you sure? (yes/no): "
        )
        if confirm.lower() == "yes":
            clear_customers()
            print("\n✅ Data cleared")
        else:
            print("❌ Cancelled")
    elif "--no-clear" in sys.argv:
        import_customers(csv_file)
    else:
        # Default: clear and import
        confirm = input(
            "⚠️  This will DELETE ALL existing customers and import new ones. Continue? (yes/no): "
        )
        if confirm.lower() == "yes":
            clear_customers()
            import_customers(csv_file)
            print("\n✅ All done!")
        else:
            print("❌ Cancelled")

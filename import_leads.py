#!/usr/bin/env python3
"""
Import leads from CSV file
Usage: python3 import_leads.py leads.csv
       python3 import_leads.py leads.csv --no-confirm
"""

import csv
import os
import sys
from datetime import datetime, timezone

# Import your Flask app
from app import Customer, app, db


def import_leads(csv_file, confirm=True):
    """Import leads from CSV"""
    # Check if file exists
    if not os.path.exists(csv_file):
        print(f"Error: File not found: {csv_file}")
        sys.exit(1)

    with app.app_context():
        # Count existing leads
        existing_leads = Customer.query.filter_by(status='lead').count()
        print(f"Current leads in database: {existing_leads}")

        if confirm:
            response = input(f"\nImport leads from {csv_file}? (yes/no): ")
            if response.lower() != "yes":
                print("Cancelled")
                sys.exit(0)

        print(f"\nImporting leads from {csv_file}...")

        imported = 0
        skipped = 0
        errors = 0

        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                # Validate CSV has required columns
                if "name" not in (reader.fieldnames or []):
                    print("Error: CSV must have 'name' column")
                    sys.exit(1)

                print(f"Columns found: {reader.fieldnames}")

                for row in reader:
                    try:
                        name = row.get("name", "").strip()
                        if not name:
                            skipped += 1
                            continue

                        # Clean phone number
                        phone = row.get("phone", "").strip()
                        if phone:
                            # Remove "Phone Number" prefix
                            if phone.startswith("Phone Number"):
                                phone = phone.replace("Phone Number", "").strip()
                            # Clear useless values
                            if phone.lower() in ["call", "phone", "n/a", "none", "-", ""]:
                                phone = None
                            # Take only first phone if multiple (separated by common patterns)
                            elif phone:
                                import re
                                # Split on 1-800, 1-888, or second area code pattern
                                phone = re.split(r'1-8\d\d|(?<=\d{4})(?=\d{3}-)', phone)[0].strip()
                                # Truncate to 20 chars max
                                if len(phone) > 20:
                                    phone = phone[:20]
                        phone = phone or None
                        address = row.get("address", "").strip() or None
                        city = row.get("city", "").strip() or None

                        # Use source or category as notes if no notes column
                        notes = row.get("notes", "").strip()
                        if not notes:
                            source = row.get("source", "").strip()
                            category = row.get("category", "").strip()
                            if source and category:
                                notes = f"{category} - {source}"
                            elif source:
                                notes = source
                            elif category:
                                notes = category
                        notes = notes or None

                        # Check for duplicate by name+phone
                        existing = Customer.query.filter_by(
                            name=name, phone=phone
                        ).first()

                        if existing:
                            skipped += 1
                            continue

                        lead = Customer(
                            name=name,
                            address=address,
                            city=city,
                            phone=phone,
                            notes=notes,
                            balance=0.0,
                            status='lead',
                            created_at=datetime.now(timezone.utc),
                        )

                        db.session.add(lead)
                        imported += 1

                        # Commit in batches of 50
                        if imported % 50 == 0:
                            db.session.commit()
                            print(f"   Imported {imported} leads...")

                    except Exception as e:
                        errors += 1
                        db.session.rollback()
                        print(f"   Error on row: {e}")
                        continue

            # Final commit
            db.session.commit()

            print(f"\nImport complete!")
            print(f"   Imported: {imported} leads")
            print(f"   Skipped: {skipped} duplicates/empty")
            print(f"   Errors: {errors}")
            print(f"   Total leads in database: {Customer.query.filter_by(status='lead').count()}")

            # Show city breakdown
            if imported > 0:
                print(f"\nLeads by city:")
                from collections import defaultdict

                cities = defaultdict(int)
                for lead in Customer.query.filter_by(status='lead').all():
                    cities[lead.city or "Unknown"] += 1

                for city, count in sorted(cities.items(), key=lambda x: -x[1])[:15]:
                    print(f"   {city:25} {count:3}")

        except csv.Error as e:
            print(f"Error reading CSV file: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error during import: {e}")
            db.session.rollback()
            sys.exit(1)


def clear_leads():
    """Delete all leads"""
    with app.app_context():
        count = Customer.query.filter_by(status='lead').count()
        print(f"Found {count} leads to delete")

        confirm = input("Are you sure you want to delete ALL leads? (yes/no): ")
        if confirm.lower() != "yes":
            print("Cancelled")
            return

        deleted = Customer.query.filter_by(status='lead').delete()
        db.session.commit()
        print(f"Deleted {deleted} leads")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 import_leads.py leads.csv")
        print("\nOptions:")
        print("  --no-confirm    Skip confirmation prompt")
        print("  --clear         Delete all leads (no import)")
        sys.exit(1)

    if "--clear" in sys.argv:
        clear_leads()
    else:
        csv_file = sys.argv[1]
        confirm = "--no-confirm" not in sys.argv
        import_leads(csv_file, confirm=confirm)

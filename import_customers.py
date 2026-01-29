import csv
import os

from app import (
    Customer,  # make sure this matches your model name
    app,
    db,
)

CSV_PATH = "customers.csv"


def run_import():
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is not set. Refusing to import.")

    with app.app_context():
        created = 0

        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                name = row.get("Name", "").strip()
                address = row.get("Address", "").strip()
                phone = row.get("Phone", "").strip()

                if not name:
                    continue

                customer = Customer(
                    name=name,
                    address=address,
                    phone=phone,
                )

                db.session.add(customer)
                created += 1

        db.session.commit()

        print(f"Imported {created} customers.")
        print("Total customers in DB:", Customer.query.count())


if __name__ == "__main__":
    run_import()

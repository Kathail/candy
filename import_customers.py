import csv
import sqlite3

DB_PATH = "instance/candy_route.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

with open("customers.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        cur.execute(
            """
            INSERT INTO customer (name, address, phone)
            VALUES (?, ?, ?)
            """,
            (
                row["Name"].strip(),
                row["Address"].strip(),
                row["Phone"].strip(),
            ),
        )

conn.commit()
conn.close()

print("Import complete.")

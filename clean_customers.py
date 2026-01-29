#!/usr/bin/env python3
"""
Customer Data Cleaning Script
Removes duplicates, standardizes city names, cleans phone numbers
"""

import csv
import re
from collections import defaultdict


def extract_city(address):
    """Extract and standardize city name from address"""
    # Remove postal code (A1A 1A1 format)
    address = re.sub(r"\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b", "", address)

    # Remove province abbreviations
    address = re.sub(r",\s*(On|Qc|Mb)\b", "", address, flags=re.IGNORECASE)

    # Split by comma
    parts = [p.strip() for p in address.split(",")]

    # Filter out non-city parts (Gd, Rr 1, Hwy, Unit, etc.)
    filtered = []
    for p in parts:
        # Skip route/highway designations
        if re.match(r"^(Gd|Rr\s*\d|Hwy|Unit|Road|Route|Con)\b", p, re.IGNORECASE):
            continue
        # Skip if starts with number (street address)
        if re.match(r"^\d", p):
            continue
        filtered.append(p)

    # Get last meaningful part (usually the city)
    if len(filtered) >= 2:
        city = filtered[-1]
    elif len(filtered) == 1:
        city = filtered[0]
    else:
        city = parts[-1] if parts else "Unknown"

    # Clean up
    city = re.sub(r"\s+(Twp|Township)$", "", city, flags=re.IGNORECASE)
    city = city.strip()

    # Standardize major city names
    city_map = {
        "sudbury": "Sudbury",
        "north bay": "North Bay",
        "thunder bay": "Thunder Bay",
        "sault ste marie": "Sault Ste Marie",
        "timmins": "Timmins",
        "parry sound": "Parry Sound",
        "huntsville": "Huntsville",
        "bracebridge": "Bracebridge",
        "kenora": "Kenora",
        "dryden": "Dryden",
        "nipigon": "Nipigon",
        "hearst": "Hearst",
        "kapuskasing": "Kapuskasing",
        "kirkland lake": "Kirkland Lake",
        "elliot lake": "Elliot Lake",
        "espanola": "Espanola",
        "manitoulin": "Manitoulin",
        "algoma": "Algoma",
        "red lake": "Red Lake",
        "timiskaming": "Timiskaming",
        "nipissing": "Nipissing",
        "cochrane": "Cochrane",
        "muskoka": "Muskoka",
        "rainy river": "Rainy River",
        "fort frances": "Fort Frances",
        "sioux lookout": "Sioux Lookout",
        "wawa": "Wawa",
        "blind river": "Blind River",
        "gore bay": "Gore Bay",
        "sturgeon falls": "Sturgeon Falls",
        "midland": "Midland",
        "penetang": "Penetanguishene",
        "new liskeard": "New Liskeard",
        "smooth rock falls": "Smooth Rock Falls",
        "fort albany": "Fort Albany",
        "pickle lake": "Pickle Lake",
        "lively": "Lively",
        "garson": "Garson",
        "chelmsford": "Chelmsford",
        "hanmer": "Hanmer",
        "azilda": "Azilda",
        "onaping": "Onaping",
        "levack": "Levack",
        "dowling": "Dowling",
        "val caron": "Val Caron",
        "copper cliff": "Copper Cliff",
        "callander": "Callander",
        "burks falls": "Burks Falls",
        "bala": "Bala",
        "port carling": "Port Carling",
        "rosseau": "Rosseau",
        "mactier": "Mactier",
        "port loring": "Port Loring",
        "spanish": "Spanish",
        "iron bridge": "Iron Bridge",
        "desbarats": "Desbarats",
        "richards landing": "Richards Landing",
        "kakabeka falls": "Kakabeka Falls",
        "atikokan": "Atikokan",
        "fort hope": "Fort Hope",
        "geraldton": "Geraldton",
        "longlac": "Longlac",
        "emo": "Emo",
        "fort frances": "Fort Frances",
        "devlin": "Devlin",
        "morson": "Morson",
    }

    city_lower = city.lower()
    for key, val in city_map.items():
        if key in city_lower:
            return val

    # Capitalize each word
    return " ".join(word.capitalize() for word in city.split())


def normalize_name(name):
    """Normalize name for duplicate detection"""
    name = name.lower()
    name = re.sub(r"['`']", "", name)  # Remove apostrophes
    name = re.sub(r"\s+", " ", name)  # Normalize spaces
    return name.strip()


def clean_phone(phone):
    """Format phone number consistently"""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"
    return phone


# Main processing
input_file = "customers_input.csv"  # <-- Change this to your input file
output_file = "customers_cleaned.csv"

customers_dict = {}
duplicates = 0

def main():
    global duplicates

    # Check if input file exists
    import os
    if not os.path.exists(input_file):
        print(f"❌ Error: Input file not found: {input_file}")
        return 1

    print("Reading customers...")
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            # Validate CSV has required columns
            required_columns = {"Name", "Address", "Phone"}
            if not required_columns.issubset(set(reader.fieldnames or [])):
                print(f"❌ Error: CSV missing required columns. Expected: {required_columns}")
                return 1

            for row in reader:
                name = row["Name"].strip()
                address = row["Address"].strip()
                phone = row["Phone"].strip()

                city = extract_city(address)
                phone_clean = clean_phone(phone)

                # Create unique key (name + phone)
                key = f"{normalize_name(name)}_{phone_clean}"

                if key in customers_dict:
                    duplicates += 1
                else:
                    customers_dict[key] = {
                        "name": name,
                        "address": address,
                        "city": city,
                        "phone": phone_clean,
                    }

    except csv.Error as e:
        print(f"❌ Error reading CSV file: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error processing input file: {e}")
        return 1

    print(f"Writing cleaned data...")
    try:
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "address", "city", "phone"])
            writer.writeheader()

            for customer in sorted(
                customers_dict.values(), key=lambda x: (x["city"], x["name"])
            ):
                writer.writerow(customer)

    except Exception as e:
        print(f"❌ Error writing output file: {e}")
        return 1

    # Stats
    cities = defaultdict(int)
    for c in customers_dict.values():
        cities[c["city"]] += 1

    print(f"\n✓ Done!")
    print(f"  Duplicates removed: {duplicates}")
    print(f"  Unique customers: {len(customers_dict)}")
    print(f"  Cities found: {len(cities)}")
    print(f"\nTop 15 cities:")
    for city, count in sorted(cities.items(), key=lambda x: -x[1])[:15]:
        print(f"  {city:25} {count:3}")
    print(f"\n✓ Saved to: {output_file}")
    return 0


if __name__ == "__main__":
    exit(main())

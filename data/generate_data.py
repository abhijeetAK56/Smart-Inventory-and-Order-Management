"""
generate_data.py - fill the main database with about 2,000 realistic rows.

    python scripts/setup_db.py      (first, to get an empty database)
    python data/generate_data.py

Important: stock is NOT typed into stock_levels. Everything goes through the
same flow functions the web app uses (opening stock, purchase orders, customer
orders). So the ledger and the stock always agree.

The story walks forward through the last 6 months, one event at a time,
in time order. Seeds are fixed, so every run makes the same data.
"""
import heapq
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mysql.connector  # noqa: E402
from faker import Faker  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from app import flows  # noqa: E402
from app.db import query, query_one, transaction  # noqa: E402

random.seed(42)
Faker.seed(42)
fake = Faker("en_IN")

NOW = datetime.now().replace(microsecond=0)
START = NOW - timedelta(days=180)

# 10 categories, each with 6 base products. Each base product has 2 sizes -> 120 products.
CATALOGUE = {
    "Electrical": ["LED Bulb", "Extension Board", "Ceiling Fan Regulator", "MCB Switch",
                   "Copper Wire Roll", "Tube Light"],
    "Mobile Accessories": ["USB-C Cable", "Fast Charger", "Power Bank", "Phone Cover",
                           "Screen Guard", "Earphones"],
    "Stationery": ["Notebook", "Gel Pen Pack", "A4 Paper Ream", "Stapler", "Marker Set",
                   "File Folder"],
    "Hardware": ["Hammer", "Screwdriver Set", "Measuring Tape", "Drill Bit Set",
                 "Wall Plug Pack", "Spanner Set"],
    "Kitchenware": ["Steel Tumbler Set", "Pressure Cooker", "Non-stick Pan", "Knife Set",
                    "Water Bottle", "Lunch Box"],
    "Cleaning": ["Floor Cleaner", "Dishwash Liquid", "Mop Set", "Broom", "Toilet Cleaner",
                 "Glass Cleaner"],
    "Personal Care": ["Shampoo", "Soap Pack", "Toothpaste", "Hair Oil", "Face Wash",
                      "Hand Sanitizer"],
    "Packaged Food": ["Basmati Rice", "Toor Dal", "Sunflower Oil", "Tea Powder", "Biscuits Pack",
                      "Instant Noodles"],
    "Auto Parts": ["Engine Oil", "Brake Pad Set", "Spark Plug", "Air Filter", "Car Shampoo",
                   "Wiper Blade"],
    "Computer Accessories": ["Wireless Mouse", "Keyboard", "Pen Drive", "HDMI Cable",
                             "Laptop Bag", "Webcam"],
}
SIZES = [("Small", 1.0), ("Large", 1.8)]
WAREHOUSES = [("Central Warehouse", "Delhi"), ("West Hub", "Mumbai"), ("East Hub", "Kolkata")]


def insert_rows(sql, rows):
    with transaction() as cur:
        cur.executemany(sql, rows)


def make_master_data():
    print("Adding users, categories, suppliers, warehouses, customers, products ...")
    insert_rows(
        "INSERT INTO app_users (username, password_hash, role, is_active) VALUES (%s, %s, %s, %s)",
        [
            ("admin", generate_password_hash("admin123"), "ADMIN", True),
            ("staff", generate_password_hash("staff123"), "STAFF", True),
            # "system" did the opening stock. It cannot log in.
            ("system", generate_password_hash(fake.password(length=20)), "ADMIN", False),
        ],
    )
    insert_rows("INSERT INTO categories (name, description) VALUES (%s, %s)",
                [(name, f"{name} products") for name in CATALOGUE])

    insert_rows(
        "INSERT INTO suppliers (name, contact_person, email, phone, city) VALUES (%s, %s, %s, %s, %s)",
        [(fake.company() + " Traders", fake.name(), fake.unique.company_email(),
          fake.phone_number(), fake.city()) for _ in range(25)],
    )
    insert_rows("INSERT INTO warehouses (name, city) VALUES (%s, %s)", WAREHOUSES)
    insert_rows(
        "INSERT INTO customers (name, email, phone, city, created_at) VALUES (%s, %s, %s, %s, %s)",
        [(fake.name(), fake.unique.email(), fake.phone_number(), fake.city(), START)
         for _ in range(120)],
    )

    products = []
    for category_id, (category, items) in enumerate(CATALOGUE.items(), start=1):
        for number, item in enumerate(items, start=1):
            base_price = random.randint(40, 2500)
            for size, factor in SIZES:
                price = round(base_price * factor, -1) or 10
                cost = round(price * random.uniform(0.6, 0.8), 2)
                sku = f"{category[:3].upper()}-{number:02d}{size[0]}"
                products.append((sku, f"{item} ({size})", category_id, random.randint(1, 25),
                                 price, cost, random.randint(5, 15), START))
    insert_rows(
        "INSERT INTO products (sku, name, category_id, default_supplier_id, unit_price, "
        "cost_price, reorder_level, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        products,
    )


def make_opening_stock(system_user):
    print("Adding opening stock (one OPENING movement per product per warehouse) ...")
    for product in query("SELECT product_id FROM products ORDER BY product_id"):
        for warehouse_id in (1, 2, 3):
            flows.add_opening_stock(product["product_id"], warehouse_id,
                                    random.randint(6, 30), system_user, at=START)


def pick_products_to_buy(warehouse_id, how_many):
    """Buy what is running low first (like a real shop), else random products."""
    low = query("SELECT product_id FROM v_low_stock WHERE warehouse_id = %s", (warehouse_id,))
    ids = [row["product_id"] for row in low]
    random.shuffle(ids)
    while len(ids) < how_many:
        product_id = random.randint(1, 120)
        if product_id not in ids:
            ids.append(product_id)
    return ids[:how_many]


def run_story(admin, staff):
    """
    Events wait in a queue sorted by time (heapq). Each event can add later events,
    for example: "order confirmed" adds "ship it 1 to 3 days later".
    """
    print("Running 6 months of orders and purchases in time order ...")
    events = []
    counter = 0  # tie-breaker so two events at the same time never compare their data

    def add_event(when, kind, data=None):
        nonlocal counter
        if when < NOW:
            counter += 1
            heapq.heappush(events, (when, counter, kind, data))

    def random_time():
        return START + timedelta(minutes=random.randint(60, 180 * 24 * 60 - 60))

    def recent_time():
        # the last 3 days, so some orders and POs are still waiting at the end
        return NOW - timedelta(minutes=random.randint(30, 3 * 24 * 60))

    for _ in range(185):
        add_event(random_time(), "new_order")
    for _ in range(15):
        add_event(recent_time(), "new_order")
    for _ in range(36):
        add_event(random_time(), "new_po")
    for _ in range(4):
        add_event(recent_time(), "new_po")
    for _ in range(5):
        add_event(random_time(), "adjustment")

    # Some products sell much more than others, so "best sellers" is interesting
    popularity = [random.paretovariate(2.5) for _ in range(120)]

    while events:
        when, _, kind, data = heapq.heappop(events)

        if kind == "new_order":
            customer_id = random.randint(1, 120)
            warehouse_id = random.randint(1, 3)
            product_ids = set(random.choices(range(1, 121), weights=popularity, k=random.randint(1, 4)))
            items = [(product_id, random.randint(1, 5)) for product_id in product_ids]
            order_id = flows.create_order(customer_id, warehouse_id, items, staff, at=when)
            if random.random() < 0.9:  # most orders get confirmed soon after
                add_event(when + timedelta(minutes=random.randint(5, 120)), "confirm", order_id)

        elif kind == "confirm":
            try:
                flows.confirm_order(data)
            except mysql.connector.Error:
                # Not enough stock: the customer cancels, like in real life
                flows.cancel_order(data)
                continue
            if random.random() < 0.95:
                add_event(when + timedelta(days=random.randint(1, 3)), "ship", data)
            else:
                add_event(when + timedelta(days=1), "cancel", data)

        elif kind == "ship":
            flows.ship_order(data, staff, at=when)

        elif kind == "cancel":
            flows.cancel_order(data)

        elif kind == "new_po":
            warehouse_id = random.randint(1, 3)
            product_ids = pick_products_to_buy(warehouse_id, 3)
            supplier_id = query_one("SELECT default_supplier_id FROM products WHERE product_id = %s",
                                    (product_ids[0],))["default_supplier_id"]
            items = [(product_id, random.randint(15, 40), None) for product_id in product_ids]
            po_id = flows.create_po(supplier_id, warehouse_id, items, admin, at=when)
            if random.random() < 0.95:  # a few stay as DRAFT
                flows.mark_po_ordered(po_id)
                add_event(when + timedelta(days=random.randint(2, 5)), "receive", po_id)

        elif kind == "receive":
            flows.receive_po(data, admin, at=when)

        elif kind == "adjustment":
            product_id, warehouse_id = random.randint(1, 120), random.randint(1, 3)
            change, note = random.choice([(-1, "Damaged in storage"), (-2, "Found broken during count"),
                                          (1, "Stock count found an extra unit")])
            try:
                flows.adjust_stock(product_id, warehouse_id, change, note, admin, at=when)
            except mysql.connector.Error:
                pass  # nothing left to remove, skip it


def print_summary():
    print("\nRows per table:")
    total = 0
    for table in ["app_users", "categories", "suppliers", "warehouses", "customers", "products",
                  "stock_levels", "purchase_orders", "purchase_order_items", "customer_orders",
                  "order_items", "stock_movements", "reorder_alerts"]:
        count = query_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]  # table names are fixed above
        total += count
        print(f"  {table:<22}{count:>6}")
    print(f"  {'TOTAL':<22}{total:>6}")

    mismatches = query("SELECT product_id FROM v_stock_reconciliation")
    print(f"\nReconciliation mismatches: {len(mismatches)}  (must be 0)")


def main():
    if query_one("SELECT COUNT(*) AS n FROM products")["n"] > 0:
        print("The database already has data. Run  python scripts/setup_db.py  first to empty it.")
        return
    make_master_data()
    admin, staff, system = 1, 2, 3  # user_ids in the order they were added
    make_opening_stock(system)
    run_story(admin, staff)
    print_summary()
    print("\nLogin: admin / admin123   or   staff / staff123")


if __name__ == "__main__":
    main()

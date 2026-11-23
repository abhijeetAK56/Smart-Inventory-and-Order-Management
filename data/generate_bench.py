"""
generate_bench.py - a BIG database only for the index experiment.

    python data/generate_bench.py

2,000 rows are too few for indexes to make a difference, so this builds
"stockflow_bench" with about 200,000 movements and 50,000 orders.
It is built WITHOUT sql/05_indexes.sql so we can measure the "before".
Takes about 1 to 3 minutes.
"""
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import get_root_connection  # noqa: E402
from scripts.setup_db import setup_database  # noqa: E402

DB = "stockflow_bench"
PRODUCTS = 200
CUSTOMERS = 2000
SUPPLIERS = 50
MOVEMENTS = 200_000
ORDERS = 50_000
POS = 20_000
BATCH = 5000

random.seed(7)
NOW = datetime.now().replace(microsecond=0)


def random_time(days_back=730):
    return NOW - timedelta(seconds=random.randint(0, days_back * 24 * 3600))


def insert_many(cur, sql, rows):
    """Insert in batches of 5,000 rows (one multi-row INSERT per batch)."""
    for start in range(0, len(rows), BATCH):
        cur.executemany(sql, rows[start:start + BATCH])


def main():
    print(f"Building '{DB}' without the extra indexes ...")
    setup_database(DB, with_indexes=False)
    conn = get_root_connection(DB)
    cur = conn.cursor()

    print("Master data ...")
    cur.execute("INSERT INTO app_users (username, password_hash, role) VALUES ('bench', 'x', 'ADMIN')")
    insert_many(cur, "INSERT INTO categories (name) VALUES (%s)", [(f"Category {i}",) for i in range(1, 11)])
    insert_many(cur, "INSERT INTO warehouses (name, city) VALUES (%s, %s)",
                [("WH North", "Delhi"), ("WH West", "Mumbai"), ("WH East", "Kolkata")])
    insert_many(cur, "INSERT INTO suppliers (name) VALUES (%s)",
                [(f"Supplier {i}",) for i in range(1, SUPPLIERS + 1)])
    insert_many(cur, "INSERT INTO customers (name) VALUES (%s)",
                [(f"Customer {i}",) for i in range(1, CUSTOMERS + 1)])
    insert_many(cur,
                "INSERT INTO products (sku, name, category_id, unit_price, cost_price, reorder_level) "
                "VALUES (%s, %s, %s, %s, %s, 0)",
                [(f"B-{i:04d}", f"Bench product {i}", random.randint(1, 10), 100, 70)
                 for i in range(1, PRODUCTS + 1)])

    print(f"{MOVEMENTS:,} stock movements (the trigger updates stock for each one) ...")
    start = NOW - timedelta(days=731)
    opening = [(p, w, 1_000_000, "OPENING", 1, start)
               for p in range(1, PRODUCTS + 1) for w in (1, 2, 3)]
    moves = []
    for _ in range(MOVEMENTS - len(opening)):
        if random.random() < 0.8:
            moves.append((random.randint(1, PRODUCTS), random.randint(1, 3),
                          -random.randint(1, 5), "SALE_OUT", 1, random_time()))
        else:
            moves.append((random.randint(1, PRODUCTS), random.randint(1, 3),
                          random.randint(10, 50), "PURCHASE_IN", 1, random_time()))
    insert_many(cur,
                "INSERT INTO stock_movements (product_id, warehouse_id, change_qty, movement_type, "
                "performed_by, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                opening + moves)
    conn.commit()

    print(f"{ORDERS:,} customer orders and their items ...")
    orders, items = [], []
    for order_id in range(1, ORDERS + 1):
        status = random.choices(["SHIPPED", "CONFIRMED", "PENDING", "CANCELLED"], [80, 5, 5, 10])[0]
        ordered = random_time()
        orders.append((random.randint(1, CUSTOMERS), random.randint(1, 3), status, ordered,
                       ordered + timedelta(days=1) if status == "SHIPPED" else None, 1))
        for product_id in random.sample(range(1, PRODUCTS + 1), random.randint(1, 5)):
            items.append((order_id, product_id, random.randint(1, 5), 100))
    insert_many(cur,
                "INSERT INTO customer_orders (customer_id, warehouse_id, status, order_date, "
                "shipped_date, created_by) VALUES (%s, %s, %s, %s, %s, %s)", orders)
    insert_many(cur, "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
                     "VALUES (%s, %s, %s, %s)", items)
    conn.commit()

    print(f"{POS:,} purchase orders ...")
    pos = []
    for _ in range(POS):
        status = random.choices(["RECEIVED", "ORDERED", "DRAFT", "CANCELLED"], [85, 5, 5, 5])[0]
        ordered = random_time()
        pos.append((random.randint(1, SUPPLIERS), random.randint(1, 3), status, ordered,
                    ordered + timedelta(days=3) if status == "RECEIVED" else None, 1))
    insert_many(cur,
                "INSERT INTO purchase_orders (supplier_id, warehouse_id, status, order_date, "
                "received_date, created_by) VALUES (%s, %s, %s, %s, %s, %s)", pos)
    conn.commit()
    conn.close()
    print("Done. Now run:  python scripts/index_benchmark.py")


if __name__ == "__main__":
    main()

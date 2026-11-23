"""
race_demo.py - two staff members try to sell the LAST unit at the same moment.

    python scripts/race_demo.py              (runs unsafe, then safe)
    python scripts/race_demo.py --mode unsafe
    python scripts/race_demo.py --mode safe --runs 5

It uses its own database "stockflow_demo", so your real data is safe.

UNSAFE: each order reads the stock with a plain SELECT (no lock), waits a bit,
        then writes "reserved = the number I read + 1".
        Both orders see 1 available, both succeed -> the last unit is sold TWICE.
        This is the classic "lost update" problem.

SAFE:   each order calls sp_reserve_item, which reads with SELECT ... FOR UPDATE.
        The second order has to WAIT for the first to finish, then sees
        0 available and fails cleanly. Exactly one order wins.
"""
import argparse
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mysql.connector  # noqa: E402

from app.db import get_root_connection  # noqa: E402
from scripts.setup_db import setup_database  # noqa: E402

DB = "stockflow_demo"
PRODUCT = 1
WAREHOUSE = 1
START_TIME = time.perf_counter()


def say(who, text):
    print(f"  [{time.perf_counter() - START_TIME:5.2f}s] {who}: {text}")


def build_demo_database():
    """One product with exactly 1 unit in stock, and two pending orders for 1 unit each."""
    print("Building demo database 'stockflow_demo' ...")
    setup_database(DB)
    conn = get_root_connection(DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO app_users (username, password_hash, role) VALUES ('demo', 'x', 'STAFF')")
    cur.execute("INSERT INTO warehouses (name, city) VALUES ('Demo WH', 'Patna')")
    cur.execute("INSERT INTO categories (name) VALUES ('Demo')")
    cur.execute("INSERT INTO customers (name) VALUES ('Customer A'), ('Customer B')")
    cur.execute("INSERT INTO products (sku, name, category_id, unit_price, cost_price, reorder_level) "
                "VALUES ('DEMO-1', 'Last Phone In Stock', 1, 15000, 12000, 0)")
    cur.callproc("sp_add_movement", (PRODUCT, WAREHOUSE, 1, "OPENING", "MANUAL", None, 1, None, None))
    for customer_id in (1, 2):
        cur.execute("INSERT INTO customer_orders (customer_id, warehouse_id, created_by) VALUES (%s, 1, 1)",
                    (customer_id,))
        cur.execute("INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
                    "VALUES (%s, 1, 1, 15000)", (customer_id,))
    conn.commit()
    conn.close()


def reset():
    """Put both orders back to PENDING and nothing reserved, before each run."""
    conn = get_root_connection(DB)
    cur = conn.cursor()
    cur.execute("UPDATE stock_levels SET quantity_reserved = 0")
    cur.execute("UPDATE customer_orders SET status = 'PENDING'")
    conn.commit()
    conn.close()


def unsafe_confirm(order_id, results):
    """WRONG way: read without a lock, then write back an absolute number."""
    who = f"Order {order_id}"
    conn = get_root_connection(DB)
    cur = conn.cursor()
    try:
        conn.start_transaction()
        cur.execute("SELECT quantity_on_hand, quantity_reserved FROM stock_levels "
                    "WHERE product_id = %s AND warehouse_id = %s", (PRODUCT, WAREHOUSE))
        on_hand, reserved = cur.fetchone()
        say(who, f"reads available = {on_hand - reserved} (no lock)")
        time.sleep(0.5)  # the other order reads in this gap
        if on_hand - reserved < 1:
            raise RuntimeError("not enough stock")
        cur.execute("UPDATE stock_levels SET quantity_reserved = %s "
                    "WHERE product_id = %s AND warehouse_id = %s", (reserved + 1, PRODUCT, WAREHOUSE))
        cur.execute("UPDATE customer_orders SET status = 'CONFIRMED' WHERE order_id = %s", (order_id,))
        conn.commit()
        say(who, "CONFIRMED")
        results[order_id] = "CONFIRMED"
    except (RuntimeError, mysql.connector.Error) as error:
        conn.rollback()
        say(who, f"failed: {error}")
        results[order_id] = "FAILED"
    finally:
        conn.close()


def safe_confirm(order_id, results):
    """RIGHT way: the stored procedure locks the row with SELECT ... FOR UPDATE."""
    who = f"Order {order_id}"
    conn = get_root_connection(DB)
    cur = conn.cursor()
    try:
        conn.start_transaction()
        say(who, "asks for the lock ...")
        cur.callproc("sp_reserve_item", (PRODUCT, WAREHOUSE, 1))
        say(who, "got the lock and reserved 1 unit")
        time.sleep(0.5)  # hold the lock a moment, so the other order has to wait
        cur.execute("UPDATE customer_orders SET status = 'CONFIRMED' WHERE order_id = %s", (order_id,))
        conn.commit()
        say(who, "CONFIRMED (lock released)")
        results[order_id] = "CONFIRMED"
    except mysql.connector.Error as error:
        conn.rollback()
        say(who, f"failed: {error.msg}")
        results[order_id] = "FAILED"
    finally:
        conn.close()


def run_once(mode):
    reset()
    results = {}
    worker = unsafe_confirm if mode == "unsafe" else safe_confirm
    threads = [threading.Thread(target=worker, args=(order_id, results)) for order_id in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    conn = get_root_connection(DB)
    cur = conn.cursor()
    cur.execute("SELECT quantity_on_hand, quantity_reserved FROM stock_levels WHERE product_id = %s",
                (PRODUCT,))
    on_hand, reserved = cur.fetchone()
    conn.close()

    confirmed = list(results.values()).count("CONFIRMED")
    oversold = confirmed > on_hand
    print(f"  Result: {confirmed} orders confirmed for {on_hand} unit in stock, "
          f"reserved shows {reserved}  ->  {'OVERSOLD! one unit sold twice' if oversold else 'correct'}")
    return oversold


def main():
    global START_TIME
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["unsafe", "safe", "both"], default="both")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()

    build_demo_database()
    modes = ["unsafe", "safe"] if args.mode == "both" else [args.mode]
    for mode in modes:
        oversold_count = 0
        for run in range(1, args.runs + 1):
            print(f"\n=== {mode.upper()} mode, run {run} of {args.runs} ===")
            START_TIME = time.perf_counter()
            oversold_count += run_once(mode)
        print(f"\n{mode.upper()}: oversold in {oversold_count} of {args.runs} runs")


if __name__ == "__main__":
    main()

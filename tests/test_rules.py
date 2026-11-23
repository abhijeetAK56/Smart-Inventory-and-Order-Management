"""
test_rules.py - checks every safety rule in the database.

    python tests/test_rules.py

It builds a separate database "stockflow_test" (your real data is not touched),
runs each test, and prints PASS or FAIL.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
# Point the app code at the test database, using the admin login
os.environ["DB_NAME"] = "stockflow_test"
os.environ["DB_USER"] = os.getenv("ROOT_USER", "root")
os.environ["DB_PASSWORD"] = os.getenv("ROOT_PASSWORD", "")

import mysql.connector  # noqa: E402

from app import flows  # noqa: E402
from app.db import query, query_one, transaction  # noqa: E402
from scripts.setup_db import setup_database  # noqa: E402

USER = 1        # filled in by make_sample_data()
WAREHOUSE = 1


def make_sample_data():
    """A tiny shop: 1 user, 1 warehouse, 1 customer, 3 products with 10 units each."""
    with transaction() as cur:
        cur.execute("INSERT INTO app_users (username, password_hash, role) VALUES ('tester', 'x', 'ADMIN')")
        cur.execute("INSERT INTO warehouses (name, city) VALUES ('Test WH', 'Patna')")
        cur.execute("INSERT INTO categories (name) VALUES ('Test')")
        cur.execute("INSERT INTO customers (name) VALUES ('Test Customer')")
        cur.execute("INSERT INTO suppliers (name) VALUES ('Test Supplier')")
        for i in (1, 2, 3):
            cur.execute(
                "INSERT INTO products (sku, name, category_id, unit_price, cost_price, reorder_level) "
                "VALUES (%s, %s, 1, 100, 60, 3)",
                (f"T-{i}", f"Test product {i}"),
            )
    for product_id in (1, 2, 3):
        flows.add_opening_stock(product_id, WAREHOUSE, 10, USER)


def stock(product_id):
    return query_one(
        "SELECT quantity_on_hand, quantity_reserved FROM stock_levels "
        "WHERE product_id = %s AND warehouse_id = %s",
        (product_id, WAREHOUSE),
    )


def expect_error(action):
    """Run action(). Return the error message if it failed, or None if it (wrongly) worked."""
    try:
        action()
    except (flows.FlowError, mysql.connector.Error) as error:
        return getattr(error, "msg", str(error))
    return None


def run_sql(sql):
    with transaction() as cur:
        cur.execute(sql)


# ---------------- the tests ----------------

def test_negative_stock_blocked():
    error = expect_error(lambda: flows.adjust_stock(1, WAREHOUSE, -50, "Too much out", USER))
    return error is not None and stock(1)["quantity_on_hand"] == 10


def test_ledger_update_blocked():
    error = expect_error(lambda: run_sql("UPDATE stock_movements SET change_qty = 99"))
    return error is not None and "cannot be changed" in error


def test_ledger_delete_blocked():
    error = expect_error(lambda: run_sql("DELETE FROM stock_movements"))
    return error is not None and "cannot be deleted" in error


def test_reserve_too_much_blocked():
    order_id = flows.create_order(1, WAREHOUSE, [(1, 11)], USER)
    error = expect_error(lambda: flows.confirm_order(order_id))
    return error is not None and "Not enough stock" in error and stock(1)["quantity_reserved"] == 0


def test_multi_item_rollback():
    # items 1 and 2 are fine, item 3 asks for too much -> nothing may be reserved
    order_id = flows.create_order(1, WAREHOUSE, [(1, 2), (2, 2), (3, 50)], USER)
    error = expect_error(lambda: flows.confirm_order(order_id))
    status = query_one("SELECT status FROM customer_orders WHERE order_id = %s", (order_id,))["status"]
    return (error is not None and status == "PENDING"
            and stock(1)["quantity_reserved"] == 0 and stock(2)["quantity_reserved"] == 0)


def test_alert_opens():
    # product 2 has 10, reorder level 3. Sell 8 -> available 2 -> alert
    order_id = flows.create_order(1, WAREHOUSE, [(2, 8)], USER)
    flows.confirm_order(order_id)
    flows.ship_order(order_id, USER)
    alert = query_one("SELECT status FROM reorder_alerts WHERE product_id = 2 AND status = 'OPEN'")
    return alert is not None and stock(2) == {"quantity_on_hand": 2, "quantity_reserved": 0}


def test_alert_resolves():
    po_id = flows.create_po(1, WAREHOUSE, [(2, 20, None)], USER)
    flows.mark_po_ordered(po_id)
    flows.receive_po(po_id, USER)
    still_open = query_one("SELECT alert_id FROM reorder_alerts WHERE product_id = 2 AND status = 'OPEN'")
    return still_open is None and stock(2)["quantity_on_hand"] == 22


def test_delete_product_with_history_blocked():
    error = expect_error(lambda: run_sql("DELETE FROM products WHERE product_id = 1"))
    return error is not None and query_one("SELECT product_id FROM products WHERE product_id = 1") is not None


def test_delete_order_cascades():
    order_id = flows.create_order(1, WAREHOUSE, [(1, 1), (3, 1)], USER)
    flows.delete_order(order_id)
    left = query_one("SELECT COUNT(*) AS n FROM order_items WHERE order_id = %s", (order_id,))
    return left["n"] == 0


def test_receive_po_twice_blocked():
    po_id = flows.create_po(1, WAREHOUSE, [(3, 5, None)], USER)
    flows.mark_po_ordered(po_id)
    flows.receive_po(po_id, USER)
    error = expect_error(lambda: flows.receive_po(po_id, USER))
    return error is not None and stock(3)["quantity_on_hand"] == 15


def test_reconciliation_is_clean():
    return len(query("SELECT product_id FROM v_stock_reconciliation")) == 0


TESTS = [
    ("1. Movement that makes stock negative is blocked", test_negative_stock_blocked),
    ("2. UPDATE on the ledger is blocked", test_ledger_update_blocked),
    ("3. DELETE on the ledger is blocked", test_ledger_delete_blocked),
    ("4. Reserving more than available fails with a clear message", test_reserve_too_much_blocked),
    ("5. 3-item order with one short item saves nothing", test_multi_item_rollback),
    ("6. Low stock opens an alert by itself", test_alert_opens),
    ("7. Restocking resolves the alert by itself", test_alert_resolves),
    ("8. Deleting a product with history is blocked", test_delete_product_with_history_blocked),
    ("9. Deleting an order deletes its items (cascade)", test_delete_order_cascades),
    ("10. Receiving the same PO twice is blocked", test_receive_po_twice_blocked),
    ("11. Stored stock matches the ledger", test_reconciliation_is_clean),
]


def main():
    print("Building test database 'stockflow_test' ...")
    setup_database("stockflow_test")
    make_sample_data()
    print()

    passed = 0
    for name, test in TESTS:
        try:
            ok = test()
        except Exception as error:  # a crash counts as a fail
            print(f"   crashed: {error}")
            ok = False
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        passed += ok

    print(f"\n{passed} of {len(TESTS)} tests passed")


if __name__ == "__main__":
    main()

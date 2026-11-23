"""
flows.py - every action that CHANGES stock or orders lives here.

Each function is one database transaction:
    1. lock the order / PO row with SELECT ... FOR UPDATE
    2. check its status is the right one
    3. go through the items in product_id order and CALL the stored procedures
    4. update the status
    5. COMMIT (done by transaction() in db.py), or ROLLBACK if anything failed

The web pages and the data generator both call these same functions.
The optional "at" argument is only used by the data generator to put
events in the past. In the web app it is always None (= now).
"""
import functools

import mysql.connector

from app.db import transaction


class FlowError(Exception):
    """A business rule was broken, for example shipping an order that is not confirmed."""


def retry_on_deadlock(func):
    """If MySQL stops this transaction because of a deadlock (error 1213), run it once more."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except mysql.connector.Error as error:
            if error.errno != 1213:
                raise
            return func(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------
# Small helpers used inside the transactions below
# ---------------------------------------------------------------------

def merge_items(items):
    """
    items = [(product_id, qty), ...]. If the same product is listed twice,
    add the quantities together. Returns the list sorted by product_id.
    """
    totals = {}
    for product_id, qty in items:
        totals[product_id] = totals.get(product_id, 0) + qty
    return sorted(totals.items())


def lock_order(cur, order_id):
    cur.execute(
        "SELECT order_id, warehouse_id, status FROM customer_orders "
        "WHERE order_id = %s FOR UPDATE",
        (order_id,),
    )
    order = cur.fetchone()
    if order is None:
        raise FlowError(f"Order #{order_id} does not exist.")
    return order


def lock_po(cur, po_id):
    cur.execute(
        "SELECT po_id, warehouse_id, status FROM purchase_orders "
        "WHERE po_id = %s FOR UPDATE",
        (po_id,),
    )
    po = cur.fetchone()
    if po is None:
        raise FlowError(f"Purchase order #{po_id} does not exist.")
    return po


def check_status(kind, row_id, status, allowed, action):
    if status not in allowed:
        raise FlowError(f"{kind} #{row_id} is {status}, so it cannot be {action}.")


def get_order_items(cur, order_id):
    # ORDER BY product_id: every transaction locks products in the same order,
    # so two orders can never wait for each other forever (deadlock).
    cur.execute(
        "SELECT product_id, quantity FROM order_items "
        "WHERE order_id = %s ORDER BY product_id",
        (order_id,),
    )
    return cur.fetchall()


def add_movement(cur, product_id, warehouse_id, change_qty, movement_type,
                 ref_type, ref_id, user_id, note=None, at=None):
    cur.callproc(
        "sp_add_movement",
        (product_id, warehouse_id, change_qty, movement_type,
         ref_type, ref_id, user_id, note, at),
    )


# ---------------------------------------------------------------------
# Customer orders
# ---------------------------------------------------------------------

def insert_order_items(cur, order_id, items):
    """Add items to an order. The price is copied from the product at this moment."""
    for product_id, qty in merge_items(items):
        if qty <= 0:
            raise FlowError("Quantity must be at least 1.")
        cur.execute(
            "SELECT unit_price, is_active FROM products WHERE product_id = %s",
            (product_id,),
        )
        product = cur.fetchone()
        if product is None or not product["is_active"]:
            raise FlowError(f"Product {product_id} does not exist or is inactive.")
        # If the product is already in the order, add to its quantity
        cur.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity)",
            (order_id, product_id, qty, product["unit_price"]),
        )


def create_order(customer_id, warehouse_id, items, user_id, at=None):
    """Save a new PENDING order. Nothing is reserved yet. Returns the new order_id."""
    if not items:
        raise FlowError("Add at least one item to the order.")
    with transaction() as cur:
        cur.execute(
            "INSERT INTO customer_orders (customer_id, warehouse_id, status, order_date, created_by) "
            "VALUES (%s, %s, 'PENDING', COALESCE(%s, NOW()), %s)",
            (customer_id, warehouse_id, at, user_id),
        )
        order_id = cur.lastrowid
        insert_order_items(cur, order_id, items)
    return order_id


def add_items_to_order(order_id, items):
    """Add more items to an order that is still PENDING."""
    if not items:
        raise FlowError("Add at least one item.")
    with transaction() as cur:
        order = lock_order(cur, order_id)
        check_status("Order", order_id, order["status"], ["PENDING"], "changed")
        insert_order_items(cur, order_id, items)


@retry_on_deadlock
def confirm_order(order_id):
    """PENDING -> CONFIRMED. Reserves stock for every item, or for none of them."""
    with transaction() as cur:
        order = lock_order(cur, order_id)
        check_status("Order", order_id, order["status"], ["PENDING"], "confirmed")

        for item in get_order_items(cur, order_id):
            # Fails with "Not enough stock ..." if short. Then transaction() rolls back,
            # so items reserved earlier in this loop are un-reserved too.
            cur.callproc("sp_reserve_item",
                         (item["product_id"], order["warehouse_id"], item["quantity"]))

        cur.execute("UPDATE customer_orders SET status = 'CONFIRMED' WHERE order_id = %s",
                    (order_id,))


@retry_on_deadlock
def ship_order(order_id, user_id, at=None):
    """CONFIRMED -> SHIPPED. Releases the reservation, then takes the stock out."""
    with transaction() as cur:
        order = lock_order(cur, order_id)
        check_status("Order", order_id, order["status"], ["CONFIRMED"], "shipped")

        for item in get_order_items(cur, order_id):
            # Release FIRST. If we deducted first, on_hand could drop below
            # reserved for a moment and the CHECK constraint would fail.
            cur.callproc("sp_release_item",
                         (item["product_id"], order["warehouse_id"], item["quantity"]))
            add_movement(cur, item["product_id"], order["warehouse_id"], -item["quantity"],
                         "SALE_OUT", "ORDER", order_id, user_id, at=at)

        cur.execute(
            "UPDATE customer_orders SET status = 'SHIPPED', shipped_date = COALESCE(%s, NOW()) "
            "WHERE order_id = %s",
            (at, order_id),
        )


@retry_on_deadlock
def cancel_order(order_id):
    """PENDING or CONFIRMED -> CANCELLED. A confirmed order gives its reservation back."""
    with transaction() as cur:
        order = lock_order(cur, order_id)
        check_status("Order", order_id, order["status"], ["PENDING", "CONFIRMED"], "cancelled")

        if order["status"] == "CONFIRMED":
            for item in get_order_items(cur, order_id):
                cur.callproc("sp_release_item",
                             (item["product_id"], order["warehouse_id"], item["quantity"]))

        cur.execute("UPDATE customer_orders SET status = 'CANCELLED' WHERE order_id = %s",
                    (order_id,))


def delete_order(order_id):
    """Only a PENDING order can be deleted. Its items go too (ON DELETE CASCADE)."""
    with transaction() as cur:
        order = lock_order(cur, order_id)
        check_status("Order", order_id, order["status"], ["PENDING"], "deleted")
        cur.execute("DELETE FROM customer_orders WHERE order_id = %s", (order_id,))


# ---------------------------------------------------------------------
# Purchase orders
# ---------------------------------------------------------------------

def create_po(supplier_id, warehouse_id, items, user_id, at=None):
    """
    Save a new DRAFT purchase order.
    items = [(product_id, qty, unit_cost), ...]. unit_cost None = use the product's cost price.
    """
    if not items:
        raise FlowError("Add at least one item to the purchase order.")
    with transaction() as cur:
        cur.execute(
            "INSERT INTO purchase_orders (supplier_id, warehouse_id, status, order_date, created_by) "
            "VALUES (%s, %s, 'DRAFT', COALESCE(%s, NOW()), %s)",
            (supplier_id, warehouse_id, at, user_id),
        )
        po_id = cur.lastrowid
        seen = set()
        for product_id, qty, unit_cost in sorted(items, key=lambda item: item[0]):
            if product_id in seen:
                raise FlowError("Each product can only be listed once in a purchase order.")
            seen.add(product_id)
            if qty <= 0:
                raise FlowError("Quantity must be at least 1.")
            if unit_cost is None:
                cur.execute("SELECT cost_price FROM products WHERE product_id = %s", (product_id,))
                unit_cost = cur.fetchone()["cost_price"]
            cur.execute(
                "INSERT INTO purchase_order_items (po_id, product_id, quantity, unit_cost) "
                "VALUES (%s, %s, %s, %s)",
                (po_id, product_id, qty, unit_cost),
            )
    return po_id


def mark_po_ordered(po_id):
    """DRAFT -> ORDERED (sent to the supplier)."""
    with transaction() as cur:
        po = lock_po(cur, po_id)
        check_status("Purchase order", po_id, po["status"], ["DRAFT"], "marked as ordered")
        cur.execute("UPDATE purchase_orders SET status = 'ORDERED' WHERE po_id = %s", (po_id,))


@retry_on_deadlock
def receive_po(po_id, user_id, at=None):
    """ORDERED -> RECEIVED. Adds the stock. The lock + status check stop receiving twice."""
    with transaction() as cur:
        po = lock_po(cur, po_id)
        check_status("Purchase order", po_id, po["status"], ["ORDERED"], "received")

        cur.execute(
            "SELECT product_id, quantity FROM purchase_order_items "
            "WHERE po_id = %s ORDER BY product_id",
            (po_id,),
        )
        for item in cur.fetchall():
            add_movement(cur, item["product_id"], po["warehouse_id"], item["quantity"],
                         "PURCHASE_IN", "PO", po_id, user_id, at=at)

        cur.execute(
            "UPDATE purchase_orders SET status = 'RECEIVED', received_date = COALESCE(%s, NOW()) "
            "WHERE po_id = %s",
            (at, po_id),
        )


def cancel_po(po_id):
    """DRAFT or ORDERED -> CANCELLED. No stock changes."""
    with transaction() as cur:
        po = lock_po(cur, po_id)
        check_status("Purchase order", po_id, po["status"], ["DRAFT", "ORDERED"], "cancelled")
        cur.execute("UPDATE purchase_orders SET status = 'CANCELLED' WHERE po_id = %s", (po_id,))


# ---------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------

def adjust_stock(product_id, warehouse_id, change_qty, note, user_id, at=None):
    """Manual correction by an admin (damaged goods, stock count). Needs a note."""
    if change_qty == 0:
        raise FlowError("The change cannot be 0.")
    with transaction() as cur:
        add_movement(cur, product_id, warehouse_id, change_qty,
                     "ADJUSTMENT", "MANUAL", None, user_id, note=note, at=at)


def add_opening_stock(product_id, warehouse_id, qty, user_id, at=None):
    """First stock count when a product is set up in a warehouse."""
    with transaction() as cur:
        add_movement(cur, product_id, warehouse_id, qty,
                     "OPENING", "MANUAL", None, user_id, note="Opening stock", at=at)

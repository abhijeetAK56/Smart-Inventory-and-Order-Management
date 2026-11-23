"""
orders.py - customer orders: list, new, detail, and the buttons
Confirm (reserve), Ship (deduct), Cancel (release), Delete (pending only).
The real work happens in app/flows.py.
"""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app import flows
from app.db import query, query_one
from app.helpers import (APP_ERRORS, PAGE_SIZE, current_page, date_range,
                         error_message, read_item_rows, to_int)

bp = Blueprint("orders", __name__)

STATUSES = ["PENDING", "CONFIRMED", "SHIPPED", "CANCELLED"]


def product_choices(warehouse_id=None):
    """Active products for the item dropdowns. With a warehouse, also show available stock."""
    if warehouse_id is None:
        return query("SELECT product_id, sku, name, unit_price, NULL AS available "
                     "FROM products WHERE is_active = TRUE ORDER BY name")
    return query(
        "SELECT p.product_id, p.sku, p.name, p.unit_price, "
        "       COALESCE(ps.available, 0) AS available "
        "FROM products p "
        "LEFT JOIN v_product_stock ps ON ps.product_id = p.product_id AND ps.warehouse_id = %s "
        "WHERE p.is_active = TRUE ORDER BY p.name",
        (warehouse_id,),
    )


@bp.route("/orders")
def list_orders():
    status = request.args.get("status", "")
    warehouse_id = to_int(request.args.get("warehouse_id"))
    date_from, date_to = date_range(default_days=180)
    page = current_page()

    sql = ("SELECT order_id, order_date, customer_name, warehouse_name, item_count, "
           "       total_amount, status "
           "FROM v_order_totals "
           "WHERE order_date >= %s AND order_date < DATE_ADD(%s, INTERVAL 1 DAY)")
    params = [date_from, date_to]
    if status in STATUSES:
        sql += " AND status = %s"
        params.append(status)
    if warehouse_id:
        sql += " AND warehouse_id = %s"
        params.append(warehouse_id)
    sql += " ORDER BY order_id DESC LIMIT %s OFFSET %s"
    params += [PAGE_SIZE + 1, (page - 1) * PAGE_SIZE]

    rows = query(sql, params)
    return render_template(
        "orders/list.html", orders=rows[:PAGE_SIZE], has_next=len(rows) > PAGE_SIZE, page=page,
        statuses=STATUSES, date_from=date_from, date_to=date_to,
        warehouses=query("SELECT warehouse_id, name FROM warehouses ORDER BY name"),
    )


@bp.route("/orders/new", methods=["GET", "POST"])
def new_order():
    if request.method == "POST":
        customer_id = to_int(request.form.get("customer_id"))
        warehouse_id = to_int(request.form.get("warehouse_id"))
        items = read_item_rows(request.form)
        if customer_id is None or warehouse_id is None or not items:
            flash("Pick a customer, a warehouse and at least one product with a quantity.", "error")
        else:
            try:
                order_id = flows.create_order(customer_id, warehouse_id, items, session["user_id"])
                flash(f"Order #{order_id} saved as PENDING. Nothing is reserved until you confirm it.",
                      "success")
                return redirect(url_for("orders.detail", order_id=order_id))
            except APP_ERRORS as error:
                flash(error_message(error), "error")

    return render_template(
        "orders/new.html",
        customers=query("SELECT customer_id, name, city FROM customers ORDER BY name"),
        warehouses=query("SELECT warehouse_id, name FROM warehouses ORDER BY name"),
        products=product_choices(),
        form=request.form,
    )


@bp.route("/orders/<int:order_id>")
def detail(order_id):
    order = query_one(
        "SELECT order_id, order_date, shipped_date, status, customer_name, warehouse_id, "
        "       warehouse_name, item_count, total_amount "
        "FROM v_order_totals WHERE order_id = %s",
        (order_id,),
    )
    if order is None:
        flash(f"Order #{order_id} does not exist.", "error")
        return redirect(url_for("orders.list_orders"))

    items = query(
        "SELECT i.product_id, p.sku, p.name, i.quantity, i.unit_price, "
        "       i.quantity * i.unit_price AS line_total, COALESCE(ps.available, 0) AS available "
        "FROM order_items i "
        "JOIN products p ON p.product_id = i.product_id "
        "LEFT JOIN v_product_stock ps ON ps.product_id = i.product_id AND ps.warehouse_id = %s "
        "WHERE i.order_id = %s ORDER BY p.name",
        (order["warehouse_id"], order_id),
    )
    products = product_choices(order["warehouse_id"]) if order["status"] == "PENDING" else []
    return render_template("orders/detail.html", order=order, items=items, products=products)


@bp.post("/orders/<int:order_id>/items")
def add_items(order_id):
    try:
        flows.add_items_to_order(order_id, read_item_rows(request.form))
        flash("Items added.", "success")
    except APP_ERRORS as error:
        flash(error_message(error), "error")
    return redirect(url_for("orders.detail", order_id=order_id))


@bp.post("/orders/<int:order_id>/confirm")
def confirm(order_id):
    try:
        flows.confirm_order(order_id)
        flash(f"Order #{order_id} confirmed. Stock reserved.", "success")
    except APP_ERRORS as error:
        flash(error_message(error) + " Nothing was reserved.", "error")
    return redirect(url_for("orders.detail", order_id=order_id))


@bp.post("/orders/<int:order_id>/ship")
def ship(order_id):
    try:
        flows.ship_order(order_id, session["user_id"])
        flash(f"Order #{order_id} shipped. Stock deducted.", "success")
    except APP_ERRORS as error:
        flash(error_message(error), "error")
    return redirect(url_for("orders.detail", order_id=order_id))


@bp.route("/orders/<int:order_id>/cancel", methods=["GET", "POST"])
def cancel(order_id):
    if request.method == "GET":
        return render_template(
            "confirm.html",
            title=f"Cancel order #{order_id}?",
            message="If the order is confirmed, its reserved stock goes back to available. "
                    "This cannot be undone.",
            button="Cancel order", danger=True,
            back_url=url_for("orders.detail", order_id=order_id),
        )
    try:
        flows.cancel_order(order_id)
        flash(f"Order #{order_id} cancelled. Reserved stock released.", "success")
    except APP_ERRORS as error:
        flash(error_message(error), "error")
    return redirect(url_for("orders.detail", order_id=order_id))


@bp.route("/orders/<int:order_id>/delete", methods=["GET", "POST"])
def delete(order_id):
    if request.method == "GET":
        return render_template(
            "confirm.html",
            title=f"Delete order #{order_id}?",
            message="Only a PENDING order can be deleted. Its items are deleted with it "
                    "(ON DELETE CASCADE).",
            button="Delete order", danger=True,
            back_url=url_for("orders.detail", order_id=order_id),
        )
    try:
        flows.delete_order(order_id)
        flash(f"Order #{order_id} deleted.", "success")
        return redirect(url_for("orders.list_orders"))
    except APP_ERRORS as error:
        flash(error_message(error), "error")
        return redirect(url_for("orders.detail", order_id=order_id))

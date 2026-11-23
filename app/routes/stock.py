"""
stock.py - stock levels, manual adjustments, the ledger, one product's history,
and the rebuild check (stock calculated again from the ledger).
"""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app import flows
from app.auth import admin_required
from app.db import get_connection, query, query_one
from app.helpers import (APP_ERRORS, PAGE_SIZE, current_page, date_range,
                         error_message, to_int)

bp = Blueprint("stock", __name__)

MOVEMENT_TYPES = ["OPENING", "PURCHASE_IN", "SALE_OUT", "ADJUSTMENT", "RETURN_IN",
                  "TRANSFER_IN", "TRANSFER_OUT"]


@bp.route("/stock")
def levels():
    warehouse_id = to_int(request.args.get("warehouse_id"))
    category_id = to_int(request.args.get("category_id"))
    low_only = request.args.get("low_only") == "on"

    sql = ("SELECT product_id, sku, product_name, category_name, warehouse_id, warehouse_name, "
           "       quantity_on_hand, quantity_reserved, available, reorder_level "
           "FROM v_product_stock WHERE is_active = TRUE")
    params = []
    if warehouse_id:
        sql += " AND warehouse_id = %s"
        params.append(warehouse_id)
    if category_id:
        sql += " AND category_id = %s"
        params.append(category_id)
    if low_only:
        sql += " AND available <= reorder_level"
    sql += " ORDER BY sku, warehouse_name"

    return render_template(
        "stock/levels.html",
        rows=query(sql, params),
        warehouses=query("SELECT warehouse_id, name FROM warehouses ORDER BY name"),
        categories=query("SELECT category_id, name FROM categories ORDER BY name"),
    )


@bp.route("/stock/adjust", methods=["GET", "POST"])
@admin_required
def adjust():
    product_id = to_int(request.values.get("product_id"))
    warehouse_id = to_int(request.values.get("warehouse_id"))
    row = query_one(
        "SELECT product_id, sku, product_name, warehouse_id, warehouse_name, "
        "       quantity_on_hand, quantity_reserved, available "
        "FROM v_product_stock WHERE product_id = %s AND warehouse_id = %s",
        (product_id, warehouse_id),
    )
    if row is None:
        flash("Pick a stock row to adjust from the Stock page.", "error")
        return redirect(url_for("stock.levels"))

    if request.method == "POST":
        change = to_int(request.form.get("change"))
        note = request.form.get("note", "").strip()
        if change is None or change == 0:
            flash("The change must be a whole number like 5 or -2 (not 0).", "error")
        else:
            try:
                flows.adjust_stock(product_id, warehouse_id, change, note, session["user_id"])
                flash(f"Adjustment of {change:+d} saved in the ledger.", "success")
                return redirect(url_for("stock.product_history", product_id=product_id))
            except APP_ERRORS as error:
                flash(error_message(error), "error")
    return render_template("stock/adjust.html", row=row)


@bp.route("/ledger")
def ledger():
    product_id = to_int(request.args.get("product_id"))
    warehouse_id = to_int(request.args.get("warehouse_id"))
    movement_type = request.args.get("movement_type", "")
    date_from, date_to = date_range(default_days=180)
    page = current_page()

    sql = ("SELECT movement_id, created_at, product_id, sku, product_name, warehouse_name, "
           "       movement_type, change_qty, reference_type, reference_id, username, note "
           "FROM v_movement_history "
           "WHERE created_at >= %s AND created_at < DATE_ADD(%s, INTERVAL 1 DAY)")
    params = [date_from, date_to]
    if product_id:
        sql += " AND product_id = %s"
        params.append(product_id)
    if warehouse_id:
        sql += " AND warehouse_id = %s"
        params.append(warehouse_id)
    if movement_type in MOVEMENT_TYPES:
        sql += " AND movement_type = %s"
        params.append(movement_type)
    sql += " ORDER BY created_at DESC, movement_id DESC LIMIT %s OFFSET %s"
    params += [PAGE_SIZE + 1, (page - 1) * PAGE_SIZE]

    rows = query(sql, params)
    return render_template(
        "stock/ledger.html",
        movements=rows[:PAGE_SIZE], has_next=len(rows) > PAGE_SIZE, page=page,
        date_from=date_from, date_to=date_to, movement_types=MOVEMENT_TYPES,
        products=query("SELECT product_id, sku, name FROM products ORDER BY sku"),
        warehouses=query("SELECT warehouse_id, name FROM warehouses ORDER BY name"),
    )


@bp.route("/stock/product/<int:product_id>")
def product_history(product_id):
    product = query_one(
        "SELECT p.product_id, p.sku, p.name, c.name AS category_name, p.reorder_level, p.is_active "
        "FROM products p JOIN categories c ON c.category_id = p.category_id "
        "WHERE p.product_id = %s",
        (product_id,),
    )
    if product is None:
        flash("Product not found.", "error")
        return redirect(url_for("products.list_products"))

    # Stored stock next to stock rebuilt from the ledger (correlated subquery)
    checks = query(
        "SELECT s.warehouse_id, w.name AS warehouse_name, s.quantity_on_hand, s.quantity_reserved, "
        "       (SELECT COALESCE(SUM(m.change_qty), 0) FROM stock_movements m "
        "         WHERE m.product_id = s.product_id AND m.warehouse_id = s.warehouse_id) AS rebuilt_qty "
        "FROM stock_levels s JOIN warehouses w ON w.warehouse_id = s.warehouse_id "
        "WHERE s.product_id = %s ORDER BY w.name",
        (product_id,),
    )

    # Every movement, with a running balance per warehouse (window function)
    movements = query(
        "SELECT m.movement_id, m.created_at, w.name AS warehouse_name, m.movement_type, "
        "       m.change_qty, m.reference_type, m.reference_id, u.username, m.note, "
        "       SUM(m.change_qty) OVER (PARTITION BY m.warehouse_id "
        "                               ORDER BY m.created_at, m.movement_id) AS balance "
        "FROM stock_movements m "
        "JOIN warehouses w ON w.warehouse_id = m.warehouse_id "
        "JOIN app_users u ON u.user_id = m.performed_by "
        "WHERE m.product_id = %s "
        "ORDER BY m.created_at DESC, m.movement_id DESC",
        (product_id,),
    )
    return render_template("stock/product.html", product=product, checks=checks, movements=movements)


@bp.route("/stock/rebuild")
def rebuild():
    """Rebuild stock from the ledger, now or as of a past date and time."""
    as_of = request.args.get("as_of") or None  # from <input type="datetime-local">, e.g. 2026-10-01T09:00

    # Call the stored procedure sp_stock_as_of and read the rows it returns
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.callproc("sp_stock_as_of", (as_of,))
        rebuilt = []
        for result in cur.stored_results():
            columns = [column[0] for column in result.description]
            rebuilt = [dict(zip(columns, row)) for row in result.fetchall()]
    finally:
        conn.close()

    # When rebuilding "now", also show the stored number so they can be compared
    stored = {}
    if as_of is None:
        for row in query("SELECT product_id, warehouse_id, quantity_on_hand FROM stock_levels"):
            stored[(row["product_id"], row["warehouse_id"])] = row["quantity_on_hand"]

    mismatches = query("SELECT product_id FROM v_stock_reconciliation")
    return render_template("stock/rebuild.html", rows=rebuilt, stored=stored, as_of=as_of,
                           mismatch_count=len(mismatches))

"""
purchases.py - purchase orders to suppliers: list, new, detail,
and the buttons Mark as ordered, Receive stock, Cancel.
"""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app import flows
from app.db import query, query_one
from app.helpers import APP_ERRORS, error_message, read_item_rows, to_int

bp = Blueprint("purchases", __name__)


@bp.route("/purchases")
def list_pos():
    status = request.args.get("status", "")
    sql = ("SELECT po.po_id, po.order_date, po.received_date, po.status, "
           "       s.name AS supplier_name, w.name AS warehouse_name, "
           "       COUNT(pi.product_id) AS item_count, "
           "       COALESCE(SUM(pi.quantity * pi.unit_cost), 0) AS total_value "
           "FROM purchase_orders po "
           "JOIN suppliers s ON s.supplier_id = po.supplier_id "
           "JOIN warehouses w ON w.warehouse_id = po.warehouse_id "
           "LEFT JOIN purchase_order_items pi ON pi.po_id = po.po_id ")
    params = []
    if status in ("DRAFT", "ORDERED", "RECEIVED", "CANCELLED"):
        sql += "WHERE po.status = %s "
        params.append(status)
    sql += ("GROUP BY po.po_id, po.order_date, po.received_date, po.status, s.name, w.name "
            "ORDER BY po.po_id DESC")
    return render_template("purchases/list.html", pos=query(sql, params))


@bp.route("/purchases/new", methods=["GET", "POST"])
def new_po():
    if request.method == "POST":
        supplier_id = to_int(request.form.get("supplier_id"))
        warehouse_id = to_int(request.form.get("warehouse_id"))
        items = read_item_rows(request.form, with_cost=True)
        if supplier_id is None or warehouse_id is None or not items:
            flash("Pick a supplier, a warehouse and at least one product with a quantity.", "error")
        else:
            try:
                po_id = flows.create_po(supplier_id, warehouse_id, items, session["user_id"])
                flash(f"Purchase order #{po_id} saved as DRAFT.", "success")
                return redirect(url_for("purchases.detail", po_id=po_id))
            except APP_ERRORS as error:
                flash(error_message(error), "error")

    # The Low stock report links here with ?supplier_id=..&warehouse_id=..&product_id=..
    # so the form starts filled in.
    form = request.form if request.method == "POST" else {
        "supplier_id": request.args.get("supplier_id", ""),
        "warehouse_id": request.args.get("warehouse_id", ""),
        "product_1": request.args.get("product_id", ""),
    }
    return render_template(
        "purchases/new.html",
        suppliers=query("SELECT supplier_id, name FROM suppliers WHERE is_active = TRUE ORDER BY name"),
        warehouses=query("SELECT warehouse_id, name FROM warehouses ORDER BY name"),
        products=query("SELECT product_id, sku, name, cost_price FROM products "
                       "WHERE is_active = TRUE ORDER BY name"),
        form=form,
    )


@bp.route("/purchases/<int:po_id>")
def detail(po_id):
    po = query_one(
        "SELECT po.po_id, po.order_date, po.received_date, po.status, "
        "       s.name AS supplier_name, w.name AS warehouse_name, u.username "
        "FROM purchase_orders po "
        "JOIN suppliers s ON s.supplier_id = po.supplier_id "
        "JOIN warehouses w ON w.warehouse_id = po.warehouse_id "
        "JOIN app_users u ON u.user_id = po.created_by "
        "WHERE po.po_id = %s",
        (po_id,),
    )
    if po is None:
        flash(f"Purchase order #{po_id} does not exist.", "error")
        return redirect(url_for("purchases.list_pos"))
    items = query(
        "SELECT pi.product_id, p.sku, p.name, pi.quantity, pi.unit_cost, "
        "       pi.quantity * pi.unit_cost AS line_total "
        "FROM purchase_order_items pi JOIN products p ON p.product_id = pi.product_id "
        "WHERE pi.po_id = %s ORDER BY p.name",
        (po_id,),
    )
    total = sum(item["line_total"] for item in items)
    return render_template("purchases/detail.html", po=po, items=items, total=total)


@bp.post("/purchases/<int:po_id>/ordered")
def mark_ordered(po_id):
    try:
        flows.mark_po_ordered(po_id)
        flash(f"Purchase order #{po_id} marked as ORDERED.", "success")
    except APP_ERRORS as error:
        flash(error_message(error), "error")
    return redirect(url_for("purchases.detail", po_id=po_id))


@bp.post("/purchases/<int:po_id>/receive")
def receive(po_id):
    try:
        flows.receive_po(po_id, session["user_id"])
        flash(f"Purchase order #{po_id} received. Stock updated.", "success")
    except APP_ERRORS as error:
        flash(error_message(error), "error")
    return redirect(url_for("purchases.detail", po_id=po_id))


@bp.route("/purchases/<int:po_id>/cancel", methods=["GET", "POST"])
def cancel(po_id):
    if request.method == "GET":
        return render_template(
            "confirm.html",
            title=f"Cancel purchase order #{po_id}?",
            message="No stock changes. This cannot be undone.",
            button="Cancel purchase order", danger=True,
            back_url=url_for("purchases.detail", po_id=po_id),
        )
    try:
        flows.cancel_po(po_id)
        flash(f"Purchase order #{po_id} cancelled.", "success")
    except APP_ERRORS as error:
        flash(error_message(error), "error")
    return redirect(url_for("purchases.detail", po_id=po_id))

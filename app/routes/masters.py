"""
masters.py - the simple "master data" lists: suppliers, customers, warehouses, categories.
Each one has a list page and one form page used for both add and edit.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.auth import admin_required
from app.db import query, query_one, transaction
from app.helpers import APP_ERRORS, blank_to_none, error_message

bp = Blueprint("masters", __name__)


def save(insert_sql, update_sql, values, row_id):
    """Run the INSERT (new row) or the UPDATE (existing row). Returns an error text or None."""
    try:
        with transaction() as cur:
            if row_id is None:
                cur.execute(insert_sql, values)
            else:
                cur.execute(update_sql, values + (row_id,))
    except APP_ERRORS as error:
        return error_message(error)
    return None


# ---------------- Suppliers ----------------

@bp.route("/suppliers")
def suppliers():
    rows = query("SELECT supplier_id, name, contact_person, email, phone, city, is_active "
                 "FROM suppliers ORDER BY name")
    return render_template("suppliers/list.html", suppliers=rows)


@bp.route("/suppliers/new", methods=["GET", "POST"])
@bp.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@admin_required
def supplier_form(supplier_id=None):
    if request.method == "POST":
        form = request.form
        values = (form.get("name", "").strip(), blank_to_none(form.get("contact_person")),
                  blank_to_none(form.get("email")), blank_to_none(form.get("phone")),
                  blank_to_none(form.get("city")), form.get("is_active") == "on")
        problem = "Name is required." if not values[0] else save(
            "INSERT INTO suppliers (name, contact_person, email, phone, city, is_active) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            "UPDATE suppliers SET name = %s, contact_person = %s, email = %s, phone = %s, "
            "city = %s, is_active = %s WHERE supplier_id = %s",
            values, supplier_id)
        if problem is None:
            flash("Supplier saved.", "success")
            return redirect(url_for("masters.suppliers"))
        flash(problem, "error")
        item = form
    elif supplier_id is None:
        item = {"is_active": True}
    else:
        item = query_one("SELECT name, contact_person, email, phone, city, is_active "
                         "FROM suppliers WHERE supplier_id = %s", (supplier_id,))
    return render_template("suppliers/form.html", item=item, supplier_id=supplier_id)


# ---------------- Customers (staff may add them) ----------------

@bp.route("/customers")
def customers():
    search = request.args.get("q", "").strip()
    rows = query(
        "SELECT c.customer_id, c.name, c.email, c.phone, c.city, "
        "       (SELECT COUNT(*) FROM customer_orders o WHERE o.customer_id = c.customer_id) AS order_count "
        "FROM customers c WHERE c.name LIKE %s ORDER BY c.name",
        (f"%{search}%",),
    )
    return render_template("customers/list.html", customers=rows)


@bp.route("/customers/new", methods=["GET", "POST"])
@bp.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
def customer_form(customer_id=None):
    if request.method == "POST":
        form = request.form
        values = (form.get("name", "").strip(), blank_to_none(form.get("email")),
                  blank_to_none(form.get("phone")), blank_to_none(form.get("city")))
        problem = "Name is required." if not values[0] else save(
            "INSERT INTO customers (name, email, phone, city) VALUES (%s, %s, %s, %s)",
            "UPDATE customers SET name = %s, email = %s, phone = %s, city = %s WHERE customer_id = %s",
            values, customer_id)
        if problem is None:
            flash("Customer saved.", "success")
            return redirect(url_for("masters.customers"))
        flash(problem, "error")
        item = form
    elif customer_id is None:
        item = {}
    else:
        item = query_one("SELECT name, email, phone, city FROM customers WHERE customer_id = %s",
                         (customer_id,))
    return render_template("customers/form.html", item=item, customer_id=customer_id)


# ---------------- Warehouses (admin) ----------------

@bp.route("/warehouses")
@admin_required
def warehouses():
    rows = query(
        "SELECT w.warehouse_id, w.name, w.city, "
        "       COALESCE(SUM(s.quantity_on_hand), 0) AS units_on_hand "
        "FROM warehouses w LEFT JOIN stock_levels s ON s.warehouse_id = w.warehouse_id "
        "GROUP BY w.warehouse_id, w.name, w.city ORDER BY w.name"
    )
    return render_template("warehouses/list.html", warehouses=rows)


@bp.route("/warehouses/new", methods=["GET", "POST"])
@bp.route("/warehouses/<int:warehouse_id>/edit", methods=["GET", "POST"])
@admin_required
def warehouse_form(warehouse_id=None):
    if request.method == "POST":
        values = (request.form.get("name", "").strip(), request.form.get("city", "").strip())
        problem = "Name and city are required." if not all(values) else save(
            "INSERT INTO warehouses (name, city) VALUES (%s, %s)",
            "UPDATE warehouses SET name = %s, city = %s WHERE warehouse_id = %s",
            values, warehouse_id)
        if problem is None:
            flash("Warehouse saved.", "success")
            return redirect(url_for("masters.warehouses"))
        flash(problem, "error")
        item = request.form
    elif warehouse_id is None:
        item = {}
    else:
        item = query_one("SELECT name, city FROM warehouses WHERE warehouse_id = %s", (warehouse_id,))
    return render_template("warehouses/form.html", item=item, warehouse_id=warehouse_id)


# ---------------- Categories (admin) ----------------

@bp.route("/categories")
@admin_required
def categories():
    rows = query(
        "SELECT c.category_id, c.name, c.description, COUNT(p.product_id) AS product_count "
        "FROM categories c LEFT JOIN products p ON p.category_id = c.category_id "
        "GROUP BY c.category_id, c.name, c.description ORDER BY c.name"
    )
    return render_template("categories/list.html", categories=rows)


@bp.route("/categories/new", methods=["GET", "POST"])
@bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@admin_required
def category_form(category_id=None):
    if request.method == "POST":
        values = (request.form.get("name", "").strip(), blank_to_none(request.form.get("description")))
        problem = "Name is required." if not values[0] else save(
            "INSERT INTO categories (name, description) VALUES (%s, %s)",
            "UPDATE categories SET name = %s, description = %s WHERE category_id = %s",
            values, category_id)
        if problem is None:
            flash("Category saved.", "success")
            return redirect(url_for("masters.categories"))
        flash(problem, "error")
        item = request.form
    elif category_id is None:
        item = {}
    else:
        item = query_one("SELECT name, description FROM categories WHERE category_id = %s",
                         (category_id,))
    return render_template("categories/form.html", item=item, category_id=category_id)

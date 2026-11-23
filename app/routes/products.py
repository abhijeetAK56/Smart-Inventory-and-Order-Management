"""
products.py - list, add, edit, deactivate products.
Products are never deleted once they have history; they are made inactive.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.auth import admin_required
from app.db import query, query_one, transaction
from app.helpers import (APP_ERRORS, PAGE_SIZE, current_page, error_message,
                         to_decimal, to_int)

bp = Blueprint("products", __name__)


@bp.route("/products")
def list_products():
    search = request.args.get("q", "").strip()
    category_id = to_int(request.args.get("category_id"))
    page = current_page()

    # Start with a fixed query and add a filter only when the user typed one.
    # Values always go in as %s, never pasted into the SQL text.
    sql = ("SELECT p.product_id, p.sku, p.name, c.name AS category_name, p.unit_price, "
           "       p.cost_price, p.reorder_level, p.is_active "
           "FROM products p JOIN categories c ON c.category_id = p.category_id "
           "WHERE 1 = 1")
    params = []
    if search:
        sql += " AND (p.name LIKE %s OR p.sku LIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    if category_id:
        sql += " AND p.category_id = %s"
        params.append(category_id)
    sql += " ORDER BY p.sku LIMIT %s OFFSET %s"
    params += [PAGE_SIZE + 1, (page - 1) * PAGE_SIZE]  # ask for 1 extra to know if there is a next page

    rows = query(sql, params)
    categories = query("SELECT category_id, name FROM categories ORDER BY name")
    return render_template("products/list.html", products=rows[:PAGE_SIZE],
                           has_next=len(rows) > PAGE_SIZE, page=page, categories=categories)


def read_product_form(form):
    """Check the form. Returns (values, error_text)."""
    values = (
        form.get("sku", "").strip().upper(),
        form.get("name", "").strip(),
        to_int(form.get("category_id")),
        to_int(form.get("default_supplier_id")),  # may be None
        to_decimal(form.get("unit_price")),
        to_decimal(form.get("cost_price")),
        to_int(form.get("reorder_level")),
    )
    sku, name, category_id, _, price, cost, level = values
    if not sku or not name or category_id is None:
        return values, "SKU, name and category are required."
    if price is None or cost is None or price < 0 or cost < 0:
        return values, "Price and cost must be numbers, 0 or more."
    if level is None or level < 0:
        return values, "Reorder level must be a whole number, 0 or more."
    return values, None


@bp.route("/products/new", methods=["GET", "POST"])
@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def product_form(product_id=None):
    """One page for both adding (no product_id) and editing (with product_id)."""
    categories = query("SELECT category_id, name FROM categories ORDER BY name")
    suppliers = query("SELECT supplier_id, name FROM suppliers WHERE is_active = TRUE ORDER BY name")

    if request.method == "POST":
        values, problem = read_product_form(request.form)
        if problem is None:
            try:
                with transaction() as cur:
                    if product_id is None:
                        cur.execute(
                            "INSERT INTO products (sku, name, category_id, default_supplier_id, "
                            "unit_price, cost_price, reorder_level) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            values,
                        )
                    else:
                        cur.execute(
                            "UPDATE products SET sku = %s, name = %s, category_id = %s, "
                            "default_supplier_id = %s, unit_price = %s, cost_price = %s, "
                            "reorder_level = %s WHERE product_id = %s",
                            values + (product_id,),
                        )
                flash("Product saved.", "success")
                return redirect(url_for("products.list_products"))
            except APP_ERRORS as error:
                problem = error_message(error)
        flash(problem, "error")
        item = request.form
    elif product_id is None:
        item = {"reorder_level": 10}
    else:
        item = query_one(
            "SELECT sku, name, category_id, default_supplier_id, unit_price, cost_price, "
            "reorder_level FROM products WHERE product_id = %s",
            (product_id,),
        )
        if item is None:
            flash("Product not found.", "error")
            return redirect(url_for("products.list_products"))

    return render_template("products/form.html", item=item, product_id=product_id,
                           categories=categories, suppliers=suppliers)


@bp.route("/products/<int:product_id>/toggle", methods=["GET", "POST"])
@admin_required
def toggle_product(product_id):
    product = query_one("SELECT product_id, name, is_active FROM products WHERE product_id = %s",
                        (product_id,))
    if product is None:
        flash("Product not found.", "error")
        return redirect(url_for("products.list_products"))

    if request.method == "GET":
        # Show an "Are you sure?" page first
        action = "Deactivate" if product["is_active"] else "Activate"
        return render_template(
            "confirm.html",
            title=f"{action} {product['name']}?",
            message=("An inactive product cannot be added to new orders. "
                     "Its history is kept." if product["is_active"]
                     else "The product can be ordered again."),
            button=action,
            danger=product["is_active"],
            back_url=url_for("products.list_products"),
        )

    with transaction() as cur:
        cur.execute("UPDATE products SET is_active = NOT is_active WHERE product_id = %s", (product_id,))
    flash("Product updated.", "success")
    return redirect(url_for("products.list_products"))

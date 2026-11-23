"""
reports.py - four reports, all built on the SQL views in sql/04_views.sql.
"""
from datetime import date

from flask import Blueprint, render_template, request

from app.db import query
from app.helpers import date_range, to_int

bp = Blueprint("reports", __name__)


@bp.route("/reports")
@bp.route("/reports/low-stock")
def low_stock():
    rows = query(
        "SELECT product_id, sku, product_name, category_name, warehouse_id, warehouse_name, "
        "       available, reorder_level, default_supplier_id, supplier_name "
        "FROM v_low_stock ORDER BY available, sku"
    )
    return render_template("reports/low_stock.html", rows=rows, tab="low")


@bp.route("/reports/suppliers")
def suppliers():
    this_month = date.today().strftime("%Y-%m")
    month_from = request.args.get("month_from") or f"{date.today().year - 1}-{date.today().month:02d}"
    month_to = request.args.get("month_to") or this_month
    rows = query(
        "SELECT supplier_name, month, po_count, total_quantity, total_value "
        "FROM v_supplier_purchase_summary "
        "WHERE month >= %s AND month <= %s "
        "ORDER BY month DESC, total_value DESC",
        (month_from, month_to),
    )
    return render_template("reports/suppliers.html", rows=rows, tab="suppliers",
                           month_from=month_from, month_to=month_to)


@bp.route("/reports/best-sellers")
def best_sellers():
    date_from, date_to = date_range(default_days=30)
    top = to_int(request.args.get("top"))
    top = top if top in (10, 20, 50) else 10
    rows = query(
        "SELECT sku, product_name, category_name, "
        "       SUM(quantity) AS units_sold, SUM(line_total) AS revenue "
        "FROM v_sales_lines "
        "WHERE shipped_date >= %s AND shipped_date < DATE_ADD(%s, INTERVAL 1 DAY) "
        "GROUP BY product_id, sku, product_name, category_name "
        "ORDER BY units_sold DESC, revenue DESC "
        "LIMIT %s",
        (date_from, date_to, top),
    )
    return render_template("reports/best_sellers.html", rows=rows, tab="best",
                           date_from=date_from, date_to=date_to, top=top)


@bp.route("/reports/daily-sales")
def daily_sales():
    date_from, date_to = date_range(default_days=30)
    rows = query(
        "SELECT sale_date, orders_shipped, revenue FROM v_daily_sales "
        "WHERE sale_date BETWEEN %s AND %s ORDER BY sale_date DESC",
        (date_from, date_to),
    )
    biggest = max((row["revenue"] for row in rows), default=0)
    total = sum(row["revenue"] for row in rows)
    return render_template("reports/daily_sales.html", rows=rows, tab="daily",
                           date_from=date_from, date_to=date_to, biggest=biggest, total=total)

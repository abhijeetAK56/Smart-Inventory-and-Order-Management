"""
dashboard.py - the home page and the alerts page.
"""
from datetime import date

from flask import Blueprint, render_template, request

from app.db import query, query_one

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def home():
    first_of_month = date.today().replace(day=1)
    stats = {
        "products": query_one("SELECT COUNT(*) AS n FROM products WHERE is_active = TRUE")["n"],
        "low_stock": query_one("SELECT COUNT(*) AS n FROM v_low_stock")["n"],
        "open_orders": query_one(
            "SELECT COUNT(*) AS n FROM customer_orders WHERE status IN ('PENDING', 'CONFIRMED')"
        )["n"],
        "sales_month": query_one(
            "SELECT COALESCE(SUM(revenue), 0) AS total FROM v_daily_sales WHERE sale_date >= %s",
            (first_of_month,),
        )["total"],
    }
    alerts = query(
        "SELECT p.name AS product_name, w.name AS warehouse_name, a.available_at_alert, "
        "       a.reorder_level_at_alert, a.created_at "
        "FROM reorder_alerts a "
        "JOIN products p ON p.product_id = a.product_id "
        "JOIN warehouses w ON w.warehouse_id = a.warehouse_id "
        "WHERE a.status = 'OPEN' "
        "ORDER BY a.created_at DESC LIMIT 6"
    )
    movements = query(
        "SELECT created_at, product_id, product_name, movement_type, change_qty, username "
        "FROM v_movement_history ORDER BY created_at DESC, movement_id DESC LIMIT 8"
    )
    return render_template("dashboard.html", stats=stats, alerts=alerts, movements=movements)


@bp.route("/alerts")
def alerts():
    status = "RESOLVED" if request.args.get("status") == "RESOLVED" else "OPEN"
    rows = query(
        "SELECT a.alert_id, a.product_id, p.sku, p.name AS product_name, w.name AS warehouse_name, "
        "       a.available_at_alert, a.reorder_level_at_alert, a.created_at, a.resolved_at "
        "FROM reorder_alerts a "
        "JOIN products p ON p.product_id = a.product_id "
        "JOIN warehouses w ON w.warehouse_id = a.warehouse_id "
        "WHERE a.status = %s "
        "ORDER BY a.created_at DESC, a.alert_id DESC LIMIT 200",
        (status,),
    )
    return render_template("alerts.html", alerts=rows, status=status)

"""
The Flask app is built here. run.py calls create_app().
"""
import os

from flask import Flask, redirect, render_template, request, session, url_for

from app import helpers
from app.db import query_one


def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "dev-only-secret")

    # Each file in routes/ is one part of the site (a "blueprint")
    from app.auth import bp as auth_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.masters import bp as masters_bp
    from app.routes.orders import bp as orders_bp
    from app.routes.products import bp as products_bp
    from app.routes.purchases import bp as purchases_bp
    from app.routes.reports import bp as reports_bp
    from app.routes.stock import bp as stock_bp

    for blueprint in [auth_bp, dashboard_bp, masters_bp, orders_bp,
                      products_bp, purchases_bp, reports_bp, stock_bp]:
        app.register_blueprint(blueprint)

    # Filters and functions the HTML templates can use
    app.jinja_env.filters["money"] = helpers.money
    app.jinja_env.filters["show_date"] = helpers.show_date
    app.jinja_env.globals["page_url"] = helpers.page_url

    @app.before_request
    def require_login():
        """Every page except login (and the CSS file) needs a logged-in user."""
        if request.endpoint in ("auth.login", "static"):
            return None
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return None

    @app.context_processor
    def sidebar_data():
        """The number of open alerts, shown in the sidebar on every page."""
        if "user_id" not in session:
            return {}
        row = query_one("SELECT COUNT(*) AS n FROM reorder_alerts WHERE status = 'OPEN'")
        return {"open_alert_count": row["n"]}

    @app.errorhandler(404)
    def not_found(error):
        return render_template("error.html", code=404, message="This page does not exist."), 404

    return app

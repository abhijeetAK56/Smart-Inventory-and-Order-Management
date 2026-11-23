"""
auth.py - login, logout, the admin-only check, and the Users page.
"""
import functools

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import query, query_one, transaction
from app.helpers import APP_ERRORS, error_message

bp = Blueprint("auth", __name__)


def admin_required(view):
    """Put @admin_required above a page that only an ADMIN may open."""
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if session.get("role") != "ADMIN":
            flash("Only an admin can open this page.", "error")
            return redirect(url_for("dashboard.home"))
        return view(*args, **kwargs)
    return wrapper


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = query_one(
            "SELECT user_id, username, password_hash, role FROM app_users "
            "WHERE username = %s AND is_active = TRUE",
            (request.form.get("username", "").strip(),),
        )
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard.home"))
        # Never say which one was wrong
        flash("Wrong username or password.", "error")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


# ---------------- Users (admin only) ----------------

@bp.route("/users")
@admin_required
def users():
    rows = query("SELECT user_id, username, role, is_active FROM app_users ORDER BY username")
    return render_template("users/list.html", users=rows)


@bp.route("/users/new", methods=["GET", "POST"])
@admin_required
def new_user():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role")
        if len(username) < 3 or len(password) < 6 or role not in ("ADMIN", "STAFF"):
            flash("Username needs 3+ characters, password 6+ characters, and pick a role.", "error")
            return render_template("users/form.html", item=request.form)
        try:
            with transaction() as cur:
                cur.execute(
                    "INSERT INTO app_users (username, password_hash, role) VALUES (%s, %s, %s)",
                    (username, generate_password_hash(password), role),
                )
        except APP_ERRORS as error:
            flash(error_message(error), "error")
            return render_template("users/form.html", item=request.form)
        flash(f"User {username} added.", "success")
        return redirect(url_for("auth.users"))
    return render_template("users/form.html", item={})


@bp.post("/users/<int:user_id>/toggle")
@admin_required
def toggle_user(user_id):
    if user_id == session["user_id"]:
        flash("You cannot deactivate yourself.", "error")
        return redirect(url_for("auth.users"))
    with transaction() as cur:
        cur.execute("UPDATE app_users SET is_active = NOT is_active WHERE user_id = %s", (user_id,))
    flash("User updated.", "success")
    return redirect(url_for("auth.users"))

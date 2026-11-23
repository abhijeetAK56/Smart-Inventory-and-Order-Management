"""
helpers.py - small tools the pages share:
    reading numbers from forms, paging, error messages, money and date format.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import mysql.connector
from flask import request, url_for

from app.flows import FlowError

PAGE_SIZE = 25

# The two kinds of error a page should catch and show to the user
APP_ERRORS = (FlowError, mysql.connector.Error)


# ---------- reading form values ----------

def to_int(value):
    """'12' -> 12. Empty or not a number -> None."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def to_decimal(value):
    """'99.50' -> Decimal('99.50'). Empty or not a number -> None."""
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None


def blank_to_none(value):
    """Empty text -> None, so the database stores NULL."""
    value = (value or "").strip()
    return value or None


def read_item_rows(form, with_cost=False, rows=5):
    """
    The order and PO forms have 5 item rows named product_1, qty_1, ... product_5, qty_5.
    Returns [(product_id, qty), ...] or [(product_id, qty, cost), ...]. Empty rows are skipped.
    """
    items = []
    for n in range(1, rows + 1):
        product_id = to_int(form.get(f"product_{n}"))
        qty = to_int(form.get(f"qty_{n}"))
        if product_id is None or qty is None:
            continue
        if with_cost:
            items.append((product_id, qty, to_decimal(form.get(f"cost_{n}"))))
        else:
            items.append((product_id, qty))
    return items


def date_range(default_days=30):
    """Read date_from / date_to from the URL. Default: the last 30 days."""
    today = date.today()
    date_from = request.args.get("date_from") or (today - timedelta(days=default_days)).isoformat()
    date_to = request.args.get("date_to") or today.isoformat()
    return date_from, date_to


# ---------- paging ----------

def current_page():
    page = to_int(request.args.get("page")) or 1
    return max(page, 1)


def page_url(page):
    """Link to another page of the same list, keeping the filters in the URL."""
    args = request.args.to_dict()
    args["page"] = page
    return url_for(request.endpoint, **request.view_args, **args)


# ---------- error messages ----------

def error_message(error):
    """Turn a database error into a sentence a shop worker can understand."""
    if isinstance(error, FlowError):
        return str(error)
    number = getattr(error, "errno", None)
    if number == 1644:   # our own SIGNAL from a procedure or trigger
        return error.msg
    if number == 3819:   # CHECK constraint failed
        return "This change would make stock invalid (below zero or below reserved). Nothing was saved."
    if number == 1451:   # foreign key stops a delete
        return "This record is used by other records and cannot be deleted."
    if number == 1062:   # UNIQUE value already exists
        return "That value already exists. It must be unique (for example SKU, email or name)."
    if number == 1213:   # deadlock, even after one retry
        return "Too many people updated this at once. Please try again."
    print("Unexpected database error:", error)  # shows in the terminal for you
    return "Something went wrong. Nothing was saved."


# ---------- display filters used in the HTML ----------

def money(value):
    """1234567.5 -> '₹12,34,567.50' (Indian digit grouping)."""
    value = Decimal(value or 0)
    sign = "-" if value < 0 else ""
    whole, paise = f"{abs(value):.2f}".split(".")
    if len(whole) > 3:
        last_three = whole[-3:]
        rest = whole[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        whole = ",".join(groups) + "," + last_three
    return f"{sign}₹{whole}.{paise}"


def show_date(value):
    """datetime -> '22 Nov 2026, 14:05'. date -> '22 Nov 2026'."""
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y, %H:%M")
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    return str(value)

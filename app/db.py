"""
db.py - every connection to MySQL goes through this file.

Three helpers:
    query(sql, params)      -> run a SELECT, get a list of rows (dicts)
    query_one(sql, params)  -> run a SELECT, get one row or None
    transaction()           -> for any change: commits at the end,
                               rolls back if anything goes wrong
"""
import os
from contextlib import contextmanager

import mysql.connector
from dotenv import load_dotenv

load_dotenv()  # reads the .env file in the project folder


def get_connection(database=None):
    """Connect as the app user (limited privileges)."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "stockflow_app"),
        password=os.getenv("DB_PASSWORD", ""),
        database=database or os.getenv("DB_NAME", "stockflow"),
    )


def get_root_connection(database=None):
    """Connect as the MySQL admin (root). Only the setup and demo scripts use this."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("ROOT_USER", "root"),
        password=os.getenv("ROOT_PASSWORD", ""),
        database=database,
    )


def query(sql, params=()):
    """Run a SELECT and return all rows as a list of dicts."""
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def query_one(sql, params=()):
    """Run a SELECT and return the first row (or None)."""
    rows = query(sql, params)
    return rows[0] if rows else None


@contextmanager
def transaction():
    """
    Use like this:

        with transaction() as cur:
            cur.execute(...)
            cur.execute(...)

    If every line works  -> COMMIT  (all changes are saved together)
    If any line fails    -> ROLLBACK (nothing is saved), then the error is raised again
    """
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    conn.start_transaction()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

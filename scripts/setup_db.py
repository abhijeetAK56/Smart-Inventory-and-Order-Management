"""
setup_db.py - build a StockFlow database from zero.

    python scripts/setup_db.py                      -> main database "stockflow"
    python scripts/setup_db.py --db stockflow_demo  -> another database
    python scripts/setup_db.py --db stockflow_bench --no-indexes

What it does:
    1. DROP and CREATE the database (all old data is deleted!)
    2. Run the sql/ files in order: 01 schema, 02 procedures, 03 triggers, 04 views, 05 indexes
    3. For the main database: create the limited app user "stockflow_app"
"""
import argparse
import os
import re
import sys
from pathlib import Path

# Let this script import the "app" folder (project root goes on the import path)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import get_root_connection  # noqa: E402

SQL_DIR = ROOT / "sql"
SQL_FILES = ["01_schema.sql", "02_procedures.sql", "03_triggers.sql", "04_views.sql"]
INDEX_FILE = "05_indexes.sql"


def run_sql_file(cur, path):
    """
    Run every statement in a .sql file.
    It understands "DELIMITER $$" lines the same way MySQL Workbench does,
    so procedures and triggers (which contain ; inside them) work.
    """
    delimiter = ";"
    lines = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        if stripped.upper().startswith("DELIMITER"):
            delimiter = stripped.split()[1]
            continue
        if not lines and (stripped == "" or stripped.startswith("--")):
            continue  # skip blank lines and comments between statements

        lines.append(line)
        if stripped.endswith(delimiter):
            statement = "\n".join(lines).strip()
            statement = statement[: -len(delimiter)]  # remove the ; or $$ at the end
            cur.execute(statement)
            lines = []


def setup_database(db_name, with_indexes=True):
    """Drop, create and fill the database structure."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", db_name):
        raise ValueError("Database name may only have letters, numbers and _")

    conn = get_root_connection()
    cur = conn.cursor()
    # Database names cannot be %s parameters, so we checked the name above
    cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
    cur.execute(f"CREATE DATABASE `{db_name}`")
    cur.execute(f"USE `{db_name}`")

    files = SQL_FILES + ([INDEX_FILE] if with_indexes else [])
    for name in files:
        print(f"  running {name}")
        run_sql_file(cur, SQL_DIR / name)

    conn.commit()
    conn.close()


def create_app_user(db_name):
    """Create the MySQL user the web app logs in with. It cannot delete the ledger."""
    password = os.getenv("DB_PASSWORD", "")
    app_user = os.getenv("DB_USER", "stockflow_app")
    if app_user == os.getenv("ROOT_USER", "root"):
        print("  DB_USER is the same as ROOT_USER, so no separate app user is created")
        return

    conn = get_root_connection()
    cur = conn.cursor()
    account = f"'{app_user}'@'localhost'"
    cur.execute(f"CREATE USER IF NOT EXISTS {account} IDENTIFIED BY %s", (password,))
    cur.execute(f"ALTER USER {account} IDENTIFIED BY %s", (password,))
    cur.execute(f"GRANT SELECT, INSERT, UPDATE, EXECUTE ON `{db_name}`.* TO {account}")
    # DELETE only where it is allowed. No DELETE on stock_movements (the ledger).
    for table in ["customer_orders", "order_items", "purchase_orders", "purchase_order_items"]:
        cur.execute(f"GRANT DELETE ON `{db_name}`.`{table}` TO {account}")
    conn.commit()
    conn.close()
    print(f"  app user {account} is ready")


def main():
    parser = argparse.ArgumentParser(description="Build a StockFlow database from zero")
    parser.add_argument("--db", default=os.getenv("DB_NAME", "stockflow"))
    parser.add_argument("--no-indexes", action="store_true", help="skip 05_indexes.sql")
    parser.add_argument("--yes", action="store_true", help="do not ask before deleting")
    args = parser.parse_args()

    if not args.yes:
        answer = input(f"This deletes the database '{args.db}' if it exists. Type yes to go on: ")
        if answer.strip().lower() != "yes":
            print("Stopped. Nothing was changed.")
            return

    print(f"Building database '{args.db}' ...")
    setup_database(args.db, with_indexes=not args.no_indexes)
    if args.db == os.getenv("DB_NAME", "stockflow"):
        create_app_user(args.db)
    print("Done.")


if __name__ == "__main__":
    main()

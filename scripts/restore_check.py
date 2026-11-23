"""
restore_check.py - prove a backup really works.

    python scripts/restore_check.py                 (uses the newest file in backups/)
    python scripts/restore_check.py backups/x.sql   (uses that file)

Steps:
    1. Create an empty database "stockflow_restore"
    2. Load the backup file into it
    3. Compare the row count of every table with the main database
    4. Check the procedures and triggers came back
    5. Check stock still matches the ledger (v_stock_reconciliation is empty)
    6. Print PASS or FAIL
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import get_root_connection  # noqa: E402
from scripts.backup import BACKUP_DIR, find_tool, login_args  # noqa: E402

MAIN_DB = os.getenv("DB_NAME", "stockflow")
RESTORE_DB = "stockflow_restore"
TABLES = ["app_users", "categories", "suppliers", "warehouses", "customers", "products",
          "stock_levels", "purchase_orders", "purchase_order_items", "customer_orders",
          "order_items", "stock_movements", "reorder_alerts"]


def count_rows(db_name):
    conn = get_root_connection(db_name)
    cur = conn.cursor()
    counts = {}
    for table in TABLES:  # fixed names, not user input
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        counts[table] = cur.fetchone()[0]
    conn.close()
    return counts


def main():
    if len(sys.argv) > 1:
        backup_file = Path(sys.argv[1])
    else:
        files = sorted(BACKUP_DIR.glob(f"{MAIN_DB}_*.sql"))
        if not files:
            sys.exit("No backup found. Run  python scripts/backup.py  first.")
        backup_file = files[-1]
    print(f"Restoring {backup_file.name} into '{RESTORE_DB}' ...")

    conn = get_root_connection()
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {RESTORE_DB}")
    cur.execute(f"CREATE DATABASE {RESTORE_DB}")
    conn.close()

    with open(backup_file, "rb") as sql_input:
        subprocess.run([find_tool("mysql"), *login_args(), RESTORE_DB], stdin=sql_input, check=True)

    ok = True
    print("\nRow counts (main -> restored):")
    main_counts, restored_counts = count_rows(MAIN_DB), count_rows(RESTORE_DB)
    for table in TABLES:
        same = main_counts[table] == restored_counts[table]
        ok = ok and same
        print(f"  {'ok ' if same else 'XX '} {table:<22}{main_counts[table]:>7} -> {restored_counts[table]:>7}")
    print("  (differences are expected if you changed data after taking the backup)")

    conn = get_root_connection(RESTORE_DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM information_schema.routines WHERE routine_schema = %s", (RESTORE_DB,))
    procedures = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema = %s", (RESTORE_DB,))
    triggers = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM v_stock_reconciliation")
    mismatches = cur.fetchone()[0]
    conn.close()

    print(f"\nProcedures restored: {procedures} (expected 4)")
    print(f"Triggers restored:   {triggers} (expected 5)")
    print(f"Stock vs ledger mismatches in restored copy: {mismatches} (expected 0)")
    ok = ok and procedures == 4 and triggers == 5 and mismatches == 0

    print("\nPASS: the backup restores completely." if ok else "\nFAIL: see the lines above.")


if __name__ == "__main__":
    main()

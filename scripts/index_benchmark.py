"""
index_benchmark.py - measure 4 queries BEFORE and AFTER adding the indexes.

    python data/generate_bench.py      (first, once)
    python scripts/index_benchmark.py

For each query it records:
    - the plan from EXPLAIN: access type, index used, estimated rows
    - the median time of 5 runs
Then it adds the indexes from sql/05_indexes.sql and measures again.
The result table is saved to docs/index_results.md for your report.
"""
import statistics
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import get_root_connection  # noqa: E402
from scripts.setup_db import SQL_DIR, run_sql_file  # noqa: E402

DB = "stockflow_bench"
RUNS = 5
NOW = datetime.now()
MONTH_AGO = NOW - timedelta(days=30)
QUARTER_AGO = NOW - timedelta(days=90)

INDEXES = [
    ("stock_movements", "idx_mov_prod_wh_time"),
    ("customer_orders", "idx_orders_status_date"),
    ("customer_orders", "idx_orders_customer_date"),
    ("purchase_orders", "idx_po_status_received"),
]

QUERIES = [
    ("Q1 Movement history of one product in one warehouse",
     "SELECT movement_id, change_qty, movement_type, created_at FROM stock_movements "
     "WHERE product_id = %s AND warehouse_id = %s ORDER BY created_at DESC LIMIT 50",
     (42, 2), "stock_movements"),
    ("Q2 Best sellers in the last 30 days",
     "SELECT oi.product_id, SUM(oi.quantity) AS units FROM customer_orders o "
     "JOIN order_items oi ON oi.order_id = o.order_id "
     "WHERE o.status = 'SHIPPED' AND o.order_date >= %s AND o.order_date < %s "
     "GROUP BY oi.product_id ORDER BY units DESC LIMIT 10",
     (MONTH_AGO, NOW), "o"),
    ("Q3 Order history of one customer",
     "SELECT order_id, order_date, status FROM customer_orders "
     "WHERE customer_id = %s ORDER BY order_date DESC LIMIT 20",
     (123,), "customer_orders"),
    ("Q4 Received POs per supplier in the last 90 days",
     "SELECT supplier_id, COUNT(*) AS pos FROM purchase_orders "
     "WHERE status = 'RECEIVED' AND received_date >= %s AND received_date < %s "
     "GROUP BY supplier_id",
     (QUARTER_AGO, NOW), "purchase_orders"),
]


def indexes_already_added(cur):
    """True if any of the 4 indexes exist (then the 'before' would not be fair)."""
    cur.execute("SELECT COUNT(*) FROM information_schema.statistics "
                "WHERE table_schema = %s AND index_name IN (%s, %s, %s, %s)",
                (DB, *[index for _, index in INDEXES]))
    return cur.fetchone()[0] > 0


def measure(cur):
    """Run each query: read its plan with EXPLAIN, then time it 5 times."""
    results = []
    for name, sql, params, table in QUERIES:
        cur.execute("EXPLAIN " + sql, params)
        columns = [column[0] for column in cur.description]
        plan = [dict(zip(columns, row)) for row in cur.fetchall()]
        # EXPLAIN gives one line per table. Report the line for the main table.
        first_table = next((line for line in plan if line["table"] == table), plan[0])
        times = []
        for _ in range(RUNS):
            start = time.perf_counter()
            cur.execute(sql, params)
            cur.fetchall()
            times.append((time.perf_counter() - start) * 1000)
        results.append({
            "name": name,
            "type": first_table["type"],
            "key": first_table["key"] or "none",
            "rows": first_table["rows"],
            "extra": first_table["Extra"] or "",
            "ms": statistics.median(times),
        })
        print(f"  {name}: {results[-1]['ms']:.1f} ms  (type={first_table['type']}, "
              f"key={first_table['key']}, rows={first_table['rows']})")
    return results


def main():
    conn = get_root_connection(DB)
    cur = conn.cursor()

    if indexes_already_added(cur):
        # Note: MySQL drops its own automatic foreign key index once our bigger
        # index covers the same column, so we cannot simply drop ours again.
        print("The indexes were already added by an earlier run.")
        print("Run  python data/generate_bench.py  again to get a fresh 'before', then this script.")
        conn.close()
        return

    print("BEFORE (no extra indexes)")
    cur.execute("ANALYZE TABLE stock_movements, customer_orders, order_items, purchase_orders")
    cur.fetchall()
    before = measure(cur)

    print("\nAdding indexes from sql/05_indexes.sql ...")
    run_sql_file(cur, SQL_DIR / "05_indexes.sql")
    cur.execute("ANALYZE TABLE stock_movements, customer_orders, order_items, purchase_orders")
    cur.fetchall()

    print("\nAFTER")
    after = measure(cur)
    conn.close()

    lines = [
        "# Index experiment results",
        "",
        f"Database: `{DB}` (about 200,000 movements, 50,000 orders, 20,000 POs).  ",
        f"Measured on {NOW:%d %b %Y %H:%M}. Time = median of {RUNS} runs.",
        "",
        "| Query | Before: access / index / est. rows | After: access / index / est. rows "
        "| Before ms | After ms | Faster |",
        "|---|---|---|---|---|---|",
    ]
    for b, a in zip(before, after):
        speedup = b["ms"] / a["ms"] if a["ms"] > 0 else 0
        lines.append(
            f"| {b['name']} | {b['type']} / {b['key']} / {b['rows']:,} "
            f"| {a['type']} / {a['key']} / {a['rows']:,} "
            f"| {b['ms']:.1f} | {a['ms']:.1f} | {speedup:.1f}x |"
        )
    lines += [
        "",
        "How to read it:",
        "- access `ALL` = full table scan (reads every row).",
        "- access `ref` / `range` = MySQL jumps straight to the matching rows using an index.",
        "- est. rows = how many rows MySQL expects to read. Fewer is better.",
        "",
        "Extra column (before -> after):",
        "",
    ]
    for b, a in zip(before, after):
        lines.append(f"- {b['name']}: `{b['extra'] or '-'}` -> `{a['extra'] or '-'}`")

    out = ROOT / "docs" / "index_results.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()

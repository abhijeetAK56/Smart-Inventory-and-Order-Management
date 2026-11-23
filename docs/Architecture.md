# Architecture: StockFlow

This file explains how StockFlow is built: the parts, the database design, how transactions and locks work, and how everything fits together.

**Core idea:** the database does the important work. Python only collects form input, opens a transaction, calls SQL, and shows the result as an HTML page.

---

## 1. Tech stack

| Layer | Tool | Why |
|---|---|---|
| Database | **MySQL 8.0.18+** (InnoDB engine) | Row-level locks, real transactions, enforced CHECK constraints, triggers, procedures, `EXPLAIN ANALYZE` |
| App | **Python 3.11+** with **Flask** | Flask is a small Python library that turns Python functions into web pages |
| DB driver | **mysql-connector-python** | Official MySQL driver for Python |
| Pages | **HTML + Jinja** templates | Jinja is how Flask fills HTML with data: `{{ product.name }}`, `{% for row in rows %}` |
| Styling | **Plain CSS** (one file) | No framework |
| Data | **Faker** | Makes realistic fake names, emails, cities |
| Config | **python-dotenv** | Keeps DB password in a `.env` file, not in code |
| Passwords | **werkzeug.security** (comes with Flask) | Hashes passwords |

**Not used, on purpose:** JavaScript, React, SQLAlchemy or any ORM. Every query is plain SQL you can read and explain in the viva.

---

## 2. System overview

```
 Browser (HTML forms + CSS, no JavaScript)
        |
        |  HTTP request (GET page / POST form)
        v
 +------------------------------+
 |  Flask app (Python)          |
 |  - routes: read form input   |
 |  - db.py: open connection,   |
 |    start transaction, CALL   |
 |    procedures, COMMIT or     |
 |    ROLLBACK                  |
 |  - templates: render HTML    |
 +------------------------------+
        |
        |  SQL (always with %s parameters)
        v
 +------------------------------+
 |  MySQL 8 (InnoDB)            |
 |  tables + constraints        |
 |  stored procedures           |  <- business rules live here
 |  triggers                    |  <- ledger, alerts, protection
 |  views                       |  <- all reports
 |  indexes                     |
 +------------------------------+
        |
        v
 mysqldump backups (backups/ folder)
```

---

## 3. Folder structure

```
stockflow/
  docs/                  PRD, MRD, Architecture, Rules, Phase, Design, Memory,
                         er_diagram.md, normalization.md
  sql/
    01_schema.sql        all CREATE TABLE statements
    02_procedures.sql    stored procedures
    03_triggers.sql      triggers
    04_views.sql         report views
    05_indexes.sql       extra indexes (left out of the benchmark DB for the "before")
    06_reports.sql       stand-alone queries for the report/viva (run by hand)
  app/
    __init__.py          creates the Flask app, login check for every page
    db.py                connection helpers + transaction()
    flows.py             every transaction: confirm, ship, cancel, receive, adjust ...
    helpers.py           form reading, paging, error messages, money/date format
    auth.py              login, logout, @admin_required, users page
    routes/
      dashboard.py       dashboard + alerts
      products.py        products
      masters.py         suppliers, customers, warehouses, categories
      stock.py           stock levels, adjustments, ledger, product history, rebuild
      orders.py          customer orders
      purchases.py       purchase orders
      reports.py         all reports
    templates/           .html files (see Design.md)
    static/style.css
  data/
    generate_data.py     ~2,400-row main dataset (uses flows.py)
    generate_bench.py    large dataset for the index experiment
  scripts/
    setup_db.py          drop + create a database, run sql/ files, create app user
    race_demo.py         concurrency demo (safe vs unsafe)
    index_benchmark.py   before/after index timings -> docs/index_results.md
    backup.py            mysqldump wrapper
    restore_check.py     restore + verify
  tests/
    test_rules.py        11 checks of the database rules, prints PASS/FAIL
  backups/               (created by backup.py, gitignored)
  .env.example
  requirements.txt
  run.py
  README.md
```

There is no `00_create_db.sql`: `scripts/setup_db.py` creates the database and the app user,
so the same SQL files can build `stockflow`, `stockflow_test`, `stockflow_demo` and `stockflow_bench`.
SQL files have no `USE` line for the same reason.

---

## 4. Database design

### 4.1 ER summary

```
categories 1---* products *---1 suppliers (default supplier)
products   1---* stock_levels *---1 warehouses
suppliers  1---* purchase_orders *---1 warehouses
purchase_orders 1---* purchase_order_items *---1 products
customers  1---* customer_orders *---1 warehouses
customer_orders 1---* order_items *---1 products
products + warehouses 1---* stock_movements *---1 app_users (performed_by)
products + warehouses 1---* reorder_alerts
```

Two many-to-many relationships are broken into junction tables:
- purchase orders <-> products through `purchase_order_items`
- customer orders <-> products through `order_items`

### 4.2 Tables

Types: `INT` ids with `AUTO_INCREMENT`, money as `DECIMAL(10,2)`, times as `DATETIME`.

**categories**
| Column | Type | Rules |
|---|---|---|
| category_id | INT | PK |
| name | VARCHAR(60) | NOT NULL, UNIQUE |
| description | VARCHAR(255) | |

**suppliers**
| Column | Type | Rules |
|---|---|---|
| supplier_id | INT | PK |
| name | VARCHAR(100) | NOT NULL |
| contact_person | VARCHAR(100) | |
| email | VARCHAR(120) | UNIQUE |
| phone | VARCHAR(20) | |
| city | VARCHAR(60) | |
| is_active | BOOLEAN | DEFAULT TRUE |

**warehouses**
| Column | Type | Rules |
|---|---|---|
| warehouse_id | INT | PK |
| name | VARCHAR(60) | NOT NULL, UNIQUE |
| city | VARCHAR(60) | NOT NULL |

**products**
| Column | Type | Rules |
|---|---|---|
| product_id | INT | PK |
| sku | VARCHAR(30) | NOT NULL, UNIQUE |
| name | VARCHAR(120) | NOT NULL |
| category_id | INT | FK -> categories, ON DELETE RESTRICT |
| default_supplier_id | INT | FK -> suppliers, ON DELETE SET NULL, NULL allowed |
| unit_price | DECIMAL(10,2) | NOT NULL, CHECK (unit_price >= 0) |
| cost_price | DECIMAL(10,2) | NOT NULL, CHECK (cost_price >= 0) |
| reorder_level | INT | NOT NULL DEFAULT 10, CHECK (reorder_level >= 0) |
| is_active | BOOLEAN | DEFAULT TRUE |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP |

**customers**
| Column | Type | Rules |
|---|---|---|
| customer_id | INT | PK |
| name | VARCHAR(100) | NOT NULL |
| email | VARCHAR(120) | UNIQUE |
| phone | VARCHAR(20) | |
| city | VARCHAR(60) | |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP |

**stock_levels**
| Column | Type | Rules |
|---|---|---|
| product_id | INT | PK part 1, FK -> products, ON DELETE RESTRICT |
| warehouse_id | INT | PK part 2, FK -> warehouses, ON DELETE RESTRICT |
| quantity_on_hand | INT | NOT NULL DEFAULT 0, CHECK (quantity_on_hand >= 0) |
| quantity_reserved | INT | NOT NULL DEFAULT 0, CHECK (quantity_reserved >= 0) |
| | | CHECK (quantity_reserved <= quantity_on_hand) |

Available stock = `quantity_on_hand - quantity_reserved`. It is **not stored**, it is calculated in `v_product_stock`. Storing it would break 3NF (it depends on two other columns).

**app_users**
| Column | Type | Rules |
|---|---|---|
| user_id | INT | PK |
| username | VARCHAR(40) | NOT NULL, UNIQUE |
| password_hash | VARCHAR(255) | NOT NULL |
| role | ENUM('ADMIN','STAFF') | NOT NULL |
| is_active | BOOLEAN | DEFAULT TRUE |

**purchase_orders**
| Column | Type | Rules |
|---|---|---|
| po_id | INT | PK |
| supplier_id | INT | FK -> suppliers, ON DELETE RESTRICT |
| warehouse_id | INT | FK -> warehouses, ON DELETE RESTRICT |
| status | ENUM('DRAFT','ORDERED','RECEIVED','CANCELLED') | DEFAULT 'DRAFT' |
| order_date | DATETIME | DEFAULT CURRENT_TIMESTAMP |
| received_date | DATETIME | NULL until received |
| created_by | INT | FK -> app_users |

**purchase_order_items**
| Column | Type | Rules |
|---|---|---|
| po_id | INT | PK part 1, FK -> purchase_orders, **ON DELETE CASCADE** |
| product_id | INT | PK part 2, FK -> products, ON DELETE RESTRICT |
| quantity | INT | CHECK (quantity > 0) |
| unit_cost | DECIMAL(10,2) | CHECK (unit_cost >= 0) |

**customer_orders**
| Column | Type | Rules |
|---|---|---|
| order_id | INT | PK |
| customer_id | INT | FK -> customers, ON DELETE RESTRICT |
| warehouse_id | INT | FK -> warehouses, ON DELETE RESTRICT |
| status | ENUM('PENDING','CONFIRMED','SHIPPED','CANCELLED') | DEFAULT 'PENDING' |
| order_date | DATETIME | DEFAULT CURRENT_TIMESTAMP |
| shipped_date | DATETIME | NULL |
| created_by | INT | FK -> app_users |

No `total_amount` column. Totals come from `v_order_totals` (stored totals can go out of date = update anomaly).

**order_items**
| Column | Type | Rules |
|---|---|---|
| order_id | INT | PK part 1, FK -> customer_orders, **ON DELETE CASCADE** |
| product_id | INT | PK part 2, FK -> products, ON DELETE RESTRICT |
| quantity | INT | CHECK (quantity > 0) |
| unit_price | DECIMAL(10,2) | price **at the time of sale** |

`unit_price` here is not a copy of `products.unit_price`. It is a fact about this order line (prices change later). So it does not break 3NF.

**stock_movements** (the ledger)
| Column | Type | Rules |
|---|---|---|
| movement_id | BIGINT | PK |
| product_id | INT | FK -> products, ON DELETE RESTRICT |
| warehouse_id | INT | FK -> warehouses, ON DELETE RESTRICT |
| change_qty | INT | NOT NULL, CHECK (change_qty <> 0), + means in, - means out |
| movement_type | ENUM('OPENING','PURCHASE_IN','SALE_OUT','ADJUSTMENT','RETURN_IN','TRANSFER_IN','TRANSFER_OUT') | NOT NULL |
| reference_type | ENUM('PO','ORDER','MANUAL') | |
| reference_id | INT | which PO or order (NULL for manual) |
| performed_by | INT | FK -> app_users, NOT NULL |
| note | VARCHAR(255) | required for ADJUSTMENT (checked in procedure) |
| created_at | DATETIME(6) | DEFAULT CURRENT_TIMESTAMP(6) |

`reference_id` is not a real FK because it can point to two tables. This is a known trade-off; mention it in the report.

**reorder_alerts**
| Column | Type | Rules |
|---|---|---|
| alert_id | INT | PK |
| product_id | INT | FK -> products |
| warehouse_id | INT | FK -> warehouses |
| available_at_alert | INT | |
| reorder_level_at_alert | INT | |
| status | ENUM('OPEN','RESOLVED') | DEFAULT 'OPEN' |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP |
| resolved_at | DATETIME | NULL |

### 4.3 Cascade rules (and why)

| Relationship | Rule | Reason |
|---|---|---|
| order -> order_items | CASCADE | Items mean nothing without their order |
| PO -> PO items | CASCADE | Same |
| product -> anything with history | RESTRICT | Never lose history. Deactivate the product instead. |
| category -> products | RESTRICT | Move products to another category first |
| supplier -> products.default_supplier_id | SET NULL | Product still exists without a default supplier |
| warehouse -> stock, orders | RESTRICT | Cannot remove a warehouse that holds stock |

Note: only DRAFT purchase orders and PENDING customer orders may be deleted (checked in Python). Once stock has moved, the ledger points at them.

### 4.4 Normalization (summary for the report)

- **1NF:** every column holds one value. Order items are rows, not a "items" text column.
- **2NF:** tables with composite keys (`stock_levels`, `order_items`, `purchase_order_items`) have no column that depends on only part of the key. Example: product name is in `products`, not in `order_items`.
- **3NF:** no column depends on another non-key column. Supplier city lives in `suppliers`, not in `products`. Order total and available stock are not stored.

In the report, start from one wide "spreadsheet" table (the UNF version a shop would use), then split it step by step.

---

## 5. Triggers

Each trigger has exactly one job.

| Trigger | When | Job |
|---|---|---|
| `trg_movement_apply` | AFTER INSERT ON stock_movements | Add `change_qty` to `stock_levels.quantity_on_hand` (creates the row if missing) |
| `trg_movement_no_update` | BEFORE UPDATE ON stock_movements | Raise error. Ledger cannot be edited. |
| `trg_movement_no_delete` | BEFORE DELETE ON stock_movements | Raise error. Ledger cannot be deleted. |
| `trg_stock_alert_upd` | AFTER UPDATE ON stock_levels | Open a reorder alert if available <= reorder level (and none is open). Resolve the open alert if available > reorder level. |
| `trg_stock_alert_ins` | AFTER INSERT ON stock_levels | Same check for brand-new stock rows |

Sketch of `trg_movement_apply`:

```sql
CREATE TRIGGER trg_movement_apply
AFTER INSERT ON stock_movements
FOR EACH ROW
BEGIN
  UPDATE stock_levels
  SET quantity_on_hand = quantity_on_hand + NEW.change_qty
  WHERE product_id = NEW.product_id AND warehouse_id = NEW.warehouse_id;

  IF ROW_COUNT() = 0 THEN
    INSERT INTO stock_levels (product_id, warehouse_id, quantity_on_hand, quantity_reserved)
    VALUES (NEW.product_id, NEW.warehouse_id, NEW.change_qty, 0);
  END IF;
END;
```

Why not one `INSERT ... ON DUPLICATE KEY UPDATE`? MySQL checks the CHECK constraint on the
"new row" part first. For a stock-out movement that new row has a negative quantity, so the
statement fails even though the row already exists. UPDATE first, INSERT only if no row, avoids this.
(Found by test 6 in `tests/test_rules.py`.)

If this would make stock negative, the CHECK on `stock_levels` fails, the trigger fails, and the movement INSERT fails too. So **a movement that would make stock negative can never be saved.**

Sketch of the alert check:

```sql
CREATE TRIGGER trg_stock_alert_upd
AFTER UPDATE ON stock_levels
FOR EACH ROW
BEGIN
  DECLARE v_level INT;
  DECLARE v_avail INT;
  SELECT reorder_level INTO v_level FROM products WHERE product_id = NEW.product_id;
  SET v_avail = NEW.quantity_on_hand - NEW.quantity_reserved;

  IF v_avail <= v_level THEN
    IF NOT EXISTS (SELECT 1 FROM reorder_alerts
                   WHERE product_id = NEW.product_id
                     AND warehouse_id = NEW.warehouse_id
                     AND status = 'OPEN') THEN
      INSERT INTO reorder_alerts (product_id, warehouse_id, available_at_alert, reorder_level_at_alert)
      VALUES (NEW.product_id, NEW.warehouse_id, v_avail, v_level);
    END IF;
  ELSE
    UPDATE reorder_alerts
       SET status = 'RESOLVED', resolved_at = NOW()
     WHERE product_id = NEW.product_id
       AND warehouse_id = NEW.warehouse_id
       AND status = 'OPEN';
  END IF;
END;
```

Chain of triggers: `stock_movements` -> `stock_levels` -> `reorder_alerts`. No table updates itself, so MySQL allows this.

---

## 6. Stored procedures

**Rule: procedures never START TRANSACTION or COMMIT.** Python owns the transaction. A COMMIT inside a procedure would silently commit the half-done order in Python. (See Rules.md.)

| Procedure | What it does |
|---|---|
| `sp_reserve_item(product_id, warehouse_id, qty)` | Locks the stock row (`FOR UPDATE`), checks available >= qty, adds to `quantity_reserved`. If short, raises error 45000 with the product name. |
| `sp_release_item(product_id, warehouse_id, qty)` | Locks the row, subtracts from `quantity_reserved` |
| `sp_add_movement(product_id, warehouse_id, change_qty, type, ref_type, ref_id, user_id, note, created_at)` | The **only** way to insert into `stock_movements`. Checks note is given for ADJUSTMENT. `created_at` NULL means now (a date is passed only by the data generator). |
| `sp_stock_as_of(as_of_datetime)` | Returns stock per product per warehouse rebuilt from the ledger up to that time (NULL = now) |

Sketch of `sp_reserve_item`:

```sql
CREATE PROCEDURE sp_reserve_item(IN p_product_id INT,
                                 IN p_warehouse_id INT, IN p_qty INT)
BEGIN
  DECLARE v_avail INT DEFAULT NULL;
  DECLARE v_msg VARCHAR(255);

  SELECT quantity_on_hand - quantity_reserved INTO v_avail
    FROM stock_levels
   WHERE product_id = p_product_id AND warehouse_id = p_warehouse_id
   FOR UPDATE;                      -- row lock: other orders wait here

  IF v_avail IS NULL OR v_avail < p_qty THEN
    SET v_msg = CONCAT('Not enough stock for product ', p_product_id,
                       ': available ', IFNULL(v_avail, 0), ', asked ', p_qty);
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_msg;
  END IF;

  UPDATE stock_levels
     SET quantity_reserved = quantity_reserved + p_qty
   WHERE product_id = p_product_id AND warehouse_id = p_warehouse_id;
END;
```

---

## 7. Transaction flows

All flows follow the same pattern in Python (`db.py` helper):

```python
conn.start_transaction()
try:
    # 1. lock the parent row (order or PO) with SELECT ... FOR UPDATE
    # 2. check its status is the right one
    # 3. loop items IN product_id ORDER, CALL procedures
    # 4. update the parent status
    conn.commit()
except mysql.connector.Error as e:
    conn.rollback()
    # show e.msg to the user
```

### 7.1 Confirm order (reserve)

1. Lock order row: `SELECT status FROM customer_orders WHERE order_id=%s FOR UPDATE`. Must be `PENDING`.
2. Get items: `SELECT product_id, quantity FROM order_items WHERE order_id=%s ORDER BY product_id`
3. For each item: `CALL sp_reserve_item(...)`
4. `UPDATE customer_orders SET status='CONFIRMED'`
5. COMMIT. If any item fails: ROLLBACK, nothing is reserved.

### 7.2 Ship order (deduct)

1. Lock order row. Must be `CONFIRMED`.
2. For each item in product_id order:
   - `CALL sp_release_item(...)` **first**
   - then `CALL sp_add_movement(..., -qty, 'SALE_OUT', 'ORDER', order_id, ...)`
3. `UPDATE customer_orders SET status='SHIPPED', shipped_date=NOW()`
4. COMMIT

**Order matters:** release before deducting. If on hand = 5 and reserved = 5, deducting first makes on hand 0 while reserved is still 5, and the CHECK `reserved <= on_hand` fails.

### 7.3 Cancel order

1. Lock order row. Must be `CONFIRMED` (or `PENDING`, which needs no stock change).
2. If CONFIRMED: `CALL sp_release_item(...)` for each item
3. `UPDATE customer_orders SET status='CANCELLED'`
4. COMMIT

### 7.4 Receive purchase order

1. Lock PO row. Must be `ORDERED` (this blocks receiving twice).
2. For each item: `CALL sp_add_movement(..., +qty, 'PURCHASE_IN', 'PO', po_id, ...)`
3. `UPDATE purchase_orders SET status='RECEIVED', received_date=NOW()`
4. COMMIT

### 7.5 Stock adjustment (Admin)

One `CALL sp_add_movement(..., 'ADJUSTMENT', 'MANUAL', NULL, user, note)` in its own transaction. Note is required.

---

## 8. Concurrency control

| Problem | How StockFlow stops it |
|---|---|
| Two orders reserve the last unit | `SELECT ... FOR UPDATE` in `sp_reserve_item`. Second order waits, then sees available = 0 and fails cleanly. |
| Lost update (both read 1, both write) | Updates are relative (`reserved = reserved + qty`), never "set to the number I read earlier" |
| Receiving a PO twice from two tabs | Lock the PO row and check status = ORDERED |
| Deadlock (order A locks P1 then P2, order B locks P2 then P1) | Always lock items in `product_id` order. If MySQL still reports deadlock (error 1213), retry the whole transaction once. |
| Backstop | CHECK constraints reject any row where reserved > on hand or stock < 0, even if app code is wrong |

Isolation level: InnoDB default `REPEATABLE READ`. Locking reads (`FOR UPDATE`) always read the latest committed row, which is what we need.

### 8.1 Race demo (`scripts/race_demo.py`)

Setup: one product with available = 1. Two threads each try to order 1 unit at the same moment.

- `--unsafe` mode: each thread does plain `SELECT` (no lock), sleeps 0.5 s, then writes `quantity_reserved = <value it read> + 1`. Both orders become CONFIRMED but reserved is 1. **One unit sold twice** (classic lost update).
- `--safe` mode: each thread calls `sp_reserve_item`. One succeeds, the other waits on the lock, then gets "Not enough stock". Correct.

Run the demo on a copy database (`stockflow_demo`), never the main one.

---

## 9. Views (reports)

| View | Shows |
|---|---|
| `v_product_stock` | product, warehouse, on hand, reserved, available, reorder level |
| `v_low_stock` | rows of `v_product_stock` where available <= reorder level |
| `v_order_totals` | order id, customer, date, status, item count, total amount |
| `v_sales_lines` | every line of every SHIPPED order with date, product, category, line total |
| `v_daily_sales` | date, number of shipped orders, revenue |
| `v_best_sellers` | product, total quantity sold, revenue, all time (the report page groups `v_sales_lines` by a date range instead) |
| `v_supplier_purchase_summary` | supplier, month, PO count, total quantity, total value (RECEIVED POs) |
| `v_stock_reconciliation` | product, warehouse, stored on hand, ledger sum, difference (only rows where they differ) |
| `v_movement_history` | ledger with product name, warehouse name, username |

Date-range filters (for example best sellers "last 30 days") are applied as `WHERE` on the view from Python.

Rebuild query (core of F6):

```sql
SELECT product_id, warehouse_id, SUM(change_qty) AS rebuilt_qty
FROM stock_movements
WHERE created_at <= %s
GROUP BY product_id, warehouse_id;
```

---

## 10. Indexing plan

Primary keys and UNIQUE columns already have indexes. MySQL also adds an index for each foreign key. The extra indexes are:

| Index | Helps query |
|---|---|
| `idx_mov_prod_wh_time` on stock_movements(product_id, warehouse_id, created_at) | Movement history for one product; stock as of a date |
| `idx_orders_status_date` on customer_orders(status, order_date) | Best sellers / daily sales in a date range (equality column first, range column second) |
| `idx_orders_customer_date` on customer_orders(customer_id, order_date) | A customer's order history |
| `idx_po_status_received` on purchase_orders(status, received_date) | Supplier purchase summary (received POs in a date range) |

**Experiment method** (`scripts/index_benchmark.py`):
1. `data/generate_bench.py` loads benchmark data into `stockflow_bench` **without** `05_indexes.sql`. To get a true "before", the composite indexes above must not exist (FK indexes stay).
2. Run each test query with `EXPLAIN` (access type, index, estimated rows) and time it 5 times, take the median.
3. Run `05_indexes.sql`, then `ANALYZE TABLE` on all four tables (stale statistics give bad plans).
4. Run the same queries again.
5. Save a before/after table to `docs/index_results.md`.

Note: once our composite index starts with the same column as an automatic foreign-key index,
MySQL drops its own FK index. So our index cannot simply be dropped again. To re-run the
experiment, rebuild the bench database first (`python data/generate_bench.py`).

---

## 11. Security

- Passwords stored with `generate_password_hash`, checked with `check_password_hash`
- Every query uses `%s` parameters
- Flask `SECRET_KEY` and DB password come from `.env`
- App connects as a limited MySQL user `stockflow_app`:
  - SELECT, INSERT, UPDATE on all tables
  - DELETE only on `customer_orders`, `order_items`, `purchase_orders`, `purchase_order_items`
  - EXECUTE on procedures
  - **No** DELETE on `stock_movements` (blocked by both privilege and trigger)
- Role check decorator `@admin_required` on admin pages

---

## 12. Backup and recovery

**Backup** (`scripts/backup.py`):
```
mysqldump --single-transaction --routines --triggers --events stockflow > backups/stockflow_YYYYMMDD_HHMM.sql
```
`--single-transaction` takes a consistent snapshot without locking the app.

**Restore check** (`scripts/restore_check.py`):
1. Create empty `stockflow_restore`
2. Load the backup file into it
3. Compare row counts of every table with the main database
4. Run `v_stock_reconciliation` on the restored database, must return 0 rows
5. Print PASS or FAIL

Stretch: enable binary logging and show point-in-time recovery (restore last night's dump, then replay binlog up to just before a "mistake").

---

## 13. Data generation order (`generate_data.py`)

Order matters because of foreign keys and the ledger:

1. app_users (admin, staff, system)
2. categories, suppliers, warehouses, customers
3. products
4. OPENING movements for each product x warehouse (via `sp_add_movement`, so triggers fill `stock_levels`)
5. Purchase orders: create, then receive some (via the real receive flow)
6. Customer orders: create, confirm some, ship most confirmed, cancel a few (via the real flows)
7. A few ADJUSTMENT movements with notes
8. Check: `v_stock_reconciliation` returns 0 rows

Use `random.seed(42)` and `Faker.seed(42)` so the data is the same every run.

**Dates:** if every row is created "now", date reports and "stock as of" are useless. So `sp_add_movement` takes a last parameter `p_created_at` (NULL means NOW()), and the Python flow functions take an optional `at` datetime. The generator walks forward through the last 6 months in date order and passes those dates. It must go in time order, otherwise the ledger history would show stock going negative in the past.

# PRD: StockFlow (Smart Inventory and Order Management)

**Type:** DBMS course project
**Owner:** Abhi
**Tech stack:** MySQL 8 + Python (Flask) + HTML + CSS. No JavaScript, no ORM.
**Status:** Built and tested (see README.md)

---

## 1. Problem

Small businesses keep stock, suppliers and customer orders in spreadsheets. This causes four problems:

1. **Overselling.** Two people sell the same last unit because the sheet does not lock anything.
2. **Wrong stock counts.** Someone edits a cell by mistake and nobody can tell what the real number is.
3. **No history.** There is no record of who changed what, or when.
4. **No useful reports.** Finding what is running low, or what sells best, takes manual work every time.

## 2. Goal

Build StockFlow, a database-first inventory and order system where **the database itself** stops these mistakes: through constraints, transactions, locks, triggers and an append-only movement ledger.

The web pages are only a simple window into the database. The real work happens in SQL.

## 3. What success looks like

| # | Success check | How we prove it |
|---|---|---|
| S1 | Two orders cannot sell the same last unit | `race_demo.py` runs two orders at the same time for 1 unit. Exactly one succeeds. The unsafe version (no lock) oversells. |
| S2 | Current stock can be rebuilt from history | `v_stock_reconciliation` returns 0 mismatch rows |
| S3 | A failed order changes nothing | Order with 3 items where item 3 has no stock: no rows saved, stock unchanged |
| S4 | Low stock raises an alert by itself | Ship an order that drops stock below the reorder level. An alert row appears without any Python code creating it. |
| S5 | Indexes give a measured speedup | Before/after table with `EXPLAIN ANALYZE` times and rows examined, on the benchmark dataset |
| S6 | Backup can be restored | Restore into a fresh database, row counts match, reconciliation shows 0 mismatches |
| S7 | Schema is in 3NF | Normalization section in the report, one table at a time |

## 4. Users

| Role | What they do |
|---|---|
| **Admin** | Everything Staff does, plus: manage products, suppliers, warehouses, users; make stock adjustments; see all reports |
| **Staff** | Place customer orders, ship or cancel them, create and receive purchase orders, view stock and reports |

There is no customer login. Staff place orders on behalf of customers (like a shop counter or phone order).

## 5. Features

### 5.1 Must have (core of the project)

**F1. Master data**
- Add, edit, deactivate: products, categories, suppliers, warehouses, customers
- Products are never hard-deleted once they have history. They are marked inactive.

**F2. Stock levels**
- Stock is kept per product per warehouse
- Each row shows: on hand, reserved, available (on hand minus reserved)
- Nobody can type a new stock number directly. Stock only changes through a movement (see F5).

**F3. Customer orders**
- Create an order with up to 5 items from one warehouse
- On **Confirm**: stock is reserved inside one transaction. If any item is short, the whole order is rolled back and the user sees which item failed.
- On **Ship**: reservation is released and stock is deducted (a `SALE_OUT` movement)
- On **Cancel** (before shipping): reservation is released, nothing is deducted
- Order status flow: `PENDING -> CONFIRMED -> SHIPPED`, or `CONFIRMED -> CANCELLED`

**F4. Purchase orders**
- Create a purchase order to a supplier for one warehouse
- On **Receive**: stock goes up (a `PURCHASE_IN` movement for each item). A purchase order can only be received once.

**F5. Stock movement ledger (audit log)**
- Every change to on-hand stock is one row in `stock_movements`: product, warehouse, change (+ or -), type, reference (which order or PO), who did it, when
- The ledger is **append-only**. Triggers block UPDATE and DELETE on it.
- A trigger applies each new movement to `stock_levels`, so the two can never drift apart

**F6. Stock rebuild**
- Page that shows stock rebuilt from the ledger next to the stored stock, with any mismatch highlighted
- Can rebuild stock **as of any past date** ("what did we have on 1 October?")

**F7. Automatic reorder alerts**
- A trigger creates an alert when available stock falls to or below the product's reorder level
- The alert is resolved automatically when stock goes back above the level

**F8. Reports (built on SQL views)**
- Low-stock list
- Supplier-wise purchase summary (total quantity and value per supplier per month)
- Best-selling products (by quantity and by revenue, for a chosen date range)
- Order totals and daily sales

**F9. Login and roles**
- Username + password (hashed), session login
- Admin-only pages are blocked for Staff

### 5.2 Must have (DBMS demonstrations)

**D1. Concurrency demo script** showing safe vs unsafe ordering
**D2. Index experiment** with before/after query plans and timings
**D3. Backup and recovery** script and a tested restore
**D4. Normalization write-up** (UNF to 3NF) and ER diagram

### 5.3 Nice to have (only if time is left)

- CSV export of reports
- Stock transfer between warehouses (one `TRANSFER_OUT` + one `TRANSFER_IN` in one transaction)
- Customer returns (`RETURN_IN` movement)
- Point-in-time recovery using MySQL binary logs

### 5.4 Out of scope

- Payments, invoices, GST
- Barcode scanning
- Customer-facing shop
- Mobile app
- Any JavaScript or front-end framework

## 6. Data

Self-created dataset, about 2,000 rows, made with Python + Faker.

| Table | Approx rows |
|---|---|
| categories | 10 |
| suppliers | 25 |
| warehouses | 3 |
| customers | 120 |
| products | 120 |
| stock_levels | 360 (120 products x 3 warehouses) |
| purchase_orders | 40 |
| purchase_order_items | 120 |
| customer_orders | 200 |
| order_items | about 450 |
| stock_movements | about 800 (opening + receipts + shipments + a few adjustments) |
| reorder_alerts | about 150 (made by triggers) |
| app_users | 3 |

**Important:** the data script must create stock by inserting movements (opening stock, then receipts, then shipments), not by typing random numbers into `stock_levels`. Otherwise the rebuild check fails on day one.

A second, larger **benchmark dataset** (about 200,000 movements and 50,000 orders) is generated only for the index experiment. 2,000 rows is too small for indexes to show a real difference.

## 7. Non-functional requirements

| Area | Requirement |
|---|---|
| Correctness | All money in `DECIMAL(10,2)`, never FLOAT |
| Safety | Every SQL query from Python uses parameters (`%s`), never string joining |
| Integrity | Every relationship has a foreign key; every quantity has a CHECK |
| Performance | Each page loads in under 1 second on the 2,000-row dataset |
| Simplicity | Runs on one laptop: MySQL + `python run.py` |
| Repeatable | `sql/` files rebuild the whole database from zero in order |

## 8. Assumptions

- MySQL 8.0.18 or newer (needed for enforced CHECK constraints and `EXPLAIN ANALYZE`)
- One currency (INR)
- One order ships from one warehouse

## 9. Risks

| Risk | What we do |
|---|---|
| Deadlocks when two orders lock the same products | Always lock rows in `product_id` order. Retry once on deadlock error 1213. |
| Indexes show no gain on small data | Use the benchmark dataset for the experiment |
| Trigger logic gets hard to debug | Keep each trigger short, one job per trigger, test each one with a SQL script |
| Running out of time on UI | UI is plain forms. DBMS parts come first in the phase plan. |

## 10. Deliverables

1. `sql/` folder: schema, indexes, views, procedures, triggers, report queries
2. `data/` folder: data and benchmark generators
3. Flask web app
4. `scripts/`: race demo, index benchmark, backup and restore
5. Project report: ER diagram, normalization, transaction design, index results, backup test, screenshots
6. Viva demo script (what to click and run, in order)

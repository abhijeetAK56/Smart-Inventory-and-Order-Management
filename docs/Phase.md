# Phase Plan: StockFlow

The project is built in 9 phases. **Database work comes first, UI comes later.** If time runs short, a project with a strong database and plain pages still scores well. A pretty UI with weak SQL does not.

Week numbers assume about 7 weeks. Shrink or stretch them to match the submission date.

> **Status (22 Nov 2026): the code for Phases 0 to 8 is written and tested** (11/11 rule tests pass,
> race demo, index experiment and restore check all work). What is left for you: run it on your own
> laptop (README steps), draw the ER diagram in Workbench, write the report (Phase 9) and practise the demo.
> The checkboxes below are kept as your checklist for understanding and explaining each part.

Rule: do not start a phase until the "Done when" list of the one before it is all ticked.

---

## Phase 0: Setup (Week 1, 1 to 2 days)

**Goal:** everything installed and the project skeleton in place.

- [ ] Install MySQL 8.0.18+ and MySQL Workbench (Workbench helps draw the ER diagram)
- [ ] Install Python 3.11+, create a virtual environment
- [ ] `pip install flask mysql-connector-python faker python-dotenv`, save to `requirements.txt`
- [ ] Create the folder structure from Architecture.md section 3
- [ ] Create `.env.example` and `.env` (DB host, user, password, database name, SECRET_KEY)
- [ ] `git init`, add `.gitignore` (`.env`, `backups/`, `__pycache__/`, `venv/`)
- [ ] Put all 7 md files in `docs/`

**Done when:**
- [ ] `mysql --version` shows 8.0.18 or newer
- [ ] A tiny Python script connects to MySQL and prints the version

---

## Phase 1: ER model and schema (Week 1)

**Goal:** the full database structure, normalized and with all constraints.

- [ ] Draw the ER diagram (Workbench or draw.io). Mark keys, relationships, 1-to-many signs.
- [ ] Write the normalization steps for the report: UNF spreadsheet -> 1NF -> 2NF -> 3NF
- [ ] `scripts/setup_db.py`: creates the database, runs the sql files, creates the `stockflow_app` user with limited privileges
- [ ] `01_schema.sql`: all 12 tables with PK, FK (with ON DELETE rules), UNIQUE, CHECK, DEFAULT
- [ ] Name every constraint

**Done when:**
- [ ] `python scripts/setup_db.py` runs with no errors
- [ ] Hand test: inserting `quantity_on_hand = -1` fails, inserting reserved > on hand fails
- [ ] Hand test: deleting a category that has products fails

---

## Phase 2: Procedures and triggers (Week 2)

**Goal:** the core safety logic lives in the database.

- [ ] `03_triggers.sql`: `trg_movement_apply`, `trg_movement_no_update`, `trg_movement_no_delete`
- [ ] `02_procedures.sql`: `sp_add_movement`, `sp_reserve_item`, `sp_release_item`
- [ ] Alert triggers: `trg_stock_alert_ins`, `trg_stock_alert_upd`
- [ ] `sp_stock_as_of`
- [ ] Tests 1 to 7 and 10 in `tests/test_rules.py` (see Rules.md section 5)

**Done when:**
- [ ] Adding a movement of +50 creates a stock row with on hand 50
- [ ] A movement of -60 on that row fails and the stock stays 50
- [ ] UPDATE and DELETE on `stock_movements` both fail
- [ ] Reserving more than available fails with a readable message
- [ ] Dropping stock to the reorder level creates an OPEN alert, raising it resolves the alert
- [ ] All Phase 2 tests print PASS

---

## Phase 3: Python DB layer and transaction flows (Week 2 to 3)

**Goal:** confirm, ship, cancel, receive and adjust work as safe transactions, with no web pages yet.

- [ ] `app/db.py`: `get_connection()`, `transaction()` helper with commit/rollback, deadlock retry once
- [ ] Flow functions (plain Python, no Flask yet):
  - [ ] `create_order(customer_id, warehouse_id, items, user_id, at=None)`
  - [ ] `confirm_order(order_id, user_id)`
  - [ ] `ship_order(order_id, user_id, at=None)`
  - [ ] `cancel_order(order_id, user_id)`
  - [ ] `create_po(...)`, `receive_po(po_id, user_id, at=None)`
  - [ ] `adjust_stock(product_id, warehouse_id, change, note, user_id)`
- [ ] Each flow: lock parent row, check status, loop items in product_id order, update status, commit
- [ ] Test 5 (multi-item rollback) and test 10 (receive twice)

**Done when:**
- [ ] A 3-item order where item 3 is short leaves stock and reserved exactly as before
- [ ] Ship releases then deducts, no CHECK errors
- [ ] Receiving the same PO twice fails the second time

---

## Phase 4: Data generation (Week 3)

**Goal:** about 2,000 realistic rows that pass the reconciliation check.

- [ ] `generate_data.py` using the flow functions from Phase 3 (not raw INSERTs into stock tables)
- [ ] Seeds fixed (`random.seed(42)`, `Faker.seed(42)`)
- [ ] Follow the order in Architecture.md section 13
- [ ] Walk forward in time over 6 months and pass dates in
- [ ] Indian names and cities (`Faker("en_IN")`)
- [ ] Mix of order outcomes: most shipped, some confirmed, some pending, a few cancelled
- [ ] Make sure some products end below reorder level so alerts exist
- [ ] Print a row count per table at the end

**Done when:**
- [ ] Total rows around 2,000
- [ ] `v_stock_reconciliation` (or the raw rebuild query) shows 0 mismatches
- [ ] Running the script twice on a fresh DB gives the same data

---

## Phase 5: Views and report queries (Week 3 to 4)

**Goal:** all reports work in SQL before any page shows them.

- [ ] `04_views.sql`: all 8 views from Architecture.md section 9
- [ ] `06_reports.sql`: extra queries for the report, showing each concept (run by hand in Workbench):
  - [ ] Multi-table join (4+ tables): order lines with customer, product, category, warehouse
  - [ ] GROUP BY + HAVING: categories with revenue above average
  - [ ] Nested query: products never ordered (`NOT EXISTS`)
  - [ ] Nested query: customers who spent more than the average customer
  - [ ] Correlated subquery: each product's last movement date
  - [ ] Stock as of a past date
- [ ] Save sample output of each query for the report

**Done when:**
- [ ] Every view returns sensible rows on the 2,000-row data
- [ ] Best sellers totals match a hand check for 2 products

---

## Phase 6: Web app (Week 4 to 5)

**Goal:** plain, working pages for every feature. Follow Design.md.

- [ ] `base.html`, `style.css`, nav, flash messages
- [ ] Login / logout, login check for every page, `@admin_required`, seed 1 admin + 1 staff
- [ ] Dashboard: 4 number cards + open alerts + recent movements
- [ ] Products list (search by name/SKU, filter by category) + add/edit/deactivate
- [ ] Suppliers, categories, warehouses, customers: list + add/edit
- [ ] Stock levels page (filter by warehouse, low-stock only)
- [ ] Stock adjustment form (Admin)
- [ ] Movement history per product + rebuild check
- [ ] Customer orders: list, new order (5 item rows), detail page with Confirm / Ship / Cancel buttons
- [ ] Purchase orders: list, new PO, detail page with Mark Ordered / Receive buttons
- [ ] Reports page: low stock, supplier summary, best sellers (date range), daily sales
- [ ] Alerts page

**Done when:**
- [ ] Every PRD "must have" feature can be done through the browser
- [ ] Every error from the database shows as a readable red message, never a crash page
- [ ] Staff cannot open admin pages (gets a "not allowed" message)

---

## Phase 7: Concurrency and indexing experiments (Week 5 to 6)

**Goal:** measured proof for the two hardest DBMS topics.

**Concurrency**
- [ ] `race_demo.py` with `--safe` and `--unsafe` (Architecture.md 8.1), on `stockflow_demo`
- [ ] Run each mode 5 times, record results
- [ ] Bonus: show two MySQL terminals by hand: session A locks with `FOR UPDATE`, session B waits

**Indexing**
- [ ] `generate_bench.py`: about 200,000 movements, 50,000 orders into `stockflow_bench`
- [ ] Choose 4 test queries (one per index in Architecture.md 10)
- [ ] `index_benchmark.py`: run each 5 times with `EXPLAIN ANALYZE`, take median
- [ ] Apply `05_indexes.sql`, `ANALYZE TABLE`, run again
- [ ] Write `docs/index_results.md`: query, access type before/after, rows examined before/after, time before/after

**Done when:**
- [ ] Unsafe mode oversells at least once, safe mode never does
- [ ] At least 3 of 4 queries show a clear speedup, with plans showing why

---

## Phase 8: Backup and recovery (Week 6)

- [ ] `backup.py`: runs mysqldump with `--single-transaction --routines --triggers --events`, timestamped file
- [ ] `restore_check.py`: restore to `stockflow_restore`, compare row counts, run reconciliation, print PASS/FAIL
- [ ] Test: take backup, place 3 new orders, "lose" the database (drop it), restore, show the state from the backup
- [ ] Stretch: binary log point-in-time recovery

**Done when:**
- [ ] `restore_check.py` prints PASS
- [ ] Triggers and procedures exist in the restored database

---

## Phase 9: Report, polish and viva prep (Week 7)

- [ ] Run `python tests/test_rules.py` again, all PASS
- [ ] Project report sections:
  1. Problem and objectives
  2. ER diagram
  3. Schema with constraints
  4. Normalization (UNF -> 3NF)
  5. Procedures and triggers (with code and why)
  6. Transactions and concurrency (flows, race demo results)
  7. Queries and views (with output)
  8. Indexing results table
  9. Backup and recovery test
  10. Screenshots
  11. Limits and future work
- [ ] `README.md`: how to set up and run in 5 steps
- [ ] Viva demo script (below), practise it twice end to end
- [ ] Prepare answers: why 3NF, why FOR UPDATE, what is a lost update, why release before deduct, why procedures don't commit, why not store total

**Viva demo script (about 8 minutes)**
1. Show ER diagram and say the core idea: "stock is the sum of the ledger"
2. Login as staff, place a 2-item order, confirm it. Show reserved went up.
3. Try an order bigger than stock. Show the rollback message, show nothing changed.
4. Ship an order. Show the new SALE_OUT rows in the ledger and the alert that appeared.
5. Open the rebuild page: 0 mismatches. Try `DELETE FROM stock_movements` in the terminal: blocked.
6. Run `race_demo.py --unsafe` then `--safe`
7. Show the index results table and one EXPLAIN before/after
8. Run `restore_check.py`: PASS

---

## Cut list (if time runs out, drop in this order)

1. Point-in-time recovery (stretch)
2. Customer and warehouse edit pages (add only)
3. Daily sales report
4. Search and filters on list pages
5. Stock as of date page (keep the SQL query in the report)

**Never cut:** transactions, FOR UPDATE, ledger + triggers, reconciliation, race demo, index experiment, backup test.

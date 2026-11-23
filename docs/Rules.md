# Rules: StockFlow

These rules are for anyone writing code for StockFlow: me, a teammate, or an AI coding assistant.
**If a rule here and some code disagree, the code is wrong.**

AI assistants: read `Memory.md` first, then this file, then `Architecture.md`, before writing any code.

---

## 1. Golden rules (never break these)

1. **Stock only changes through a movement.** Never write `UPDATE stock_levels SET quantity_on_hand = ...` anywhere. Call `sp_add_movement`. The trigger does the rest.
2. **Never edit or delete the ledger.** No UPDATE or DELETE on `stock_movements`, ever. Mistakes are fixed with a new ADJUSTMENT movement.
3. **Python owns the transaction.** Procedures never use `START TRANSACTION`, `COMMIT` or `ROLLBACK`.
4. **Lock before you check.** Any check like "is there enough stock?" or "is this order still PENDING?" must read the row with `FOR UPDATE` inside the same transaction that changes it.
5. **Lock items in `product_id` order.** Always `ORDER BY product_id` before looping items. This stops deadlocks.
6. **Update with relative math.** Write `quantity_reserved = quantity_reserved + %s`. Never write a number you read earlier back into the table.
7. **Release before you deduct** when shipping (see Architecture 7.2).
8. **Parameters only.** Every value from a user goes in as `%s`. No f-strings, no `+` joining in SQL. Ever.
9. **Money is DECIMAL.** Never FLOAT in SQL, and use `Decimal` in Python, not `float`.
10. **No JavaScript.** Pages are HTML forms + CSS only.

---

## 2. SQL rules

### Naming
- Tables: plural, snake_case: `customer_orders`, `order_items`
- Columns: snake_case. Primary key is `<singular>_id`: `product_id`
- Foreign key column has the same name as the key it points to
- Procedures: `sp_` + verb: `sp_reserve_item`
- Triggers: `trg_` + table short name + job: `trg_movement_apply`
- Views: `v_` + what it shows: `v_low_stock`
- Indexes: `idx_` + table short name + columns: `idx_orders_status_date`
- Constraints: name them: `chk_stock_reserved_le_onhand`, `fk_items_order`. Named constraints give readable error messages.

### Writing SQL
- SQL keywords in UPPERCASE, names in lowercase
- One clause per line for anything longer than one line (`SELECT`, `FROM`, `JOIN`, `WHERE`, `GROUP BY`)
- Always list columns in `INSERT INTO t (col1, col2) VALUES ...`
- No `SELECT *` in app code or views. Fine for quick testing in the terminal.
- Use explicit `JOIN ... ON`, not commas in `FROM`
- Every foreign key states its `ON DELETE` rule on purpose (see Architecture 4.3)
- Every quantity and price column has a CHECK
- Use `DELIMITER $$` around procedures and triggers in `.sql` files

### Procedures and triggers
- One job per trigger. If a trigger needs two jobs, make two triggers.
- Triggers never call procedures that might COMMIT (they cannot anyway, but don't try)
- Raise errors with `SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_msg;` and build `v_msg` with `CONCAT` first (MESSAGE_TEXT does not accept an expression directly). Keep it under 128 characters (`LEFT(v_msg, 128)`).
- Error messages must be readable by a shop worker: "Not enough stock for product 12: available 0, asked 2", not "constraint violated"
- Watch out: inside procedures, `SELECT ... INTO` that finds no row leaves the variable unchanged. Always `DECLARE ... DEFAULT NULL` and check for NULL.
- Avoid cursor loops in procedures. Loop over items in Python instead (simpler to debug, and avoids the NOT FOUND handler trap).

### SQL file rules
- Files in `sql/` run in number order (through `scripts/setup_db.py`) and must work on an empty database
- No `USE` line in the files: `setup_db.py` picks the database, so the same files build the main, test, demo and bench databases
- Use `DROP ... IF EXISTS` before `CREATE` for procedures and triggers, and `CREATE OR REPLACE VIEW`, so files can be re-run
- `05_indexes.sql` is kept separate so the index experiment has a real "before"
- `setup_db.py` reads the files line by line: never end a comment line with `;` or `$$`, and never put a comment after the `;` at the end of a statement

---

## 3. Python rules

### General
- Python 3.11+, follow PEP 8, 4-space indents
- Function and variable names: `snake_case`. Constants: `UPPER_CASE`
- One route file per area (`orders.py`, `stock.py` ...), registered as Flask Blueprints
- Keep functions short. If a route does more than about 30 lines, move the DB part into a helper function.
- No ORM. No SQLAlchemy. Plain SQL through `mysql-connector-python`.
- Read config from `.env` with `python-dotenv`. Never hard-code passwords.

### Database access
- All DB access goes through `app/db.py`
- Use `cursor(dictionary=True)` so rows are dicts: `row["name"]`
- Read-only pages: open connection, SELECT, close. No transaction needed.
- Any write: use the transaction helper (inside `app/flows.py` for anything that touches stock or orders):

```python
with transaction() as cur:
    cur.execute("SELECT status FROM customer_orders WHERE order_id = %s FOR UPDATE", (order_id,))
    ...
# commits at the end, rolls back on any exception
```

- Catch `mysql.connector.Error`:
  - `errno 1644` (SIGNAL from our procedures): show `e.msg` to the user as a red message
  - `errno 3819` (CHECK failed): show "This change would make stock invalid"
  - `errno 1451` (FK blocks delete): show "This record is used elsewhere and cannot be deleted"
  - `errno 1213` (deadlock): retry the whole transaction once, then show an error
  - anything else: log it, show "Something went wrong", do not show raw SQL
- Close cursors and connections. Use `with` blocks.

### Flask routes
- GET shows a page. POST changes data. Never change data on GET.
- After a successful POST, redirect (Post/Redirect/Get) so refresh does not repeat the action
- Use `flash()` for success and error messages
- Validate form input in Python before SQL (empty fields, numbers that are not numbers, quantity <= 0), but **the database checks are the real guard**. Never remove a DB check because Python already checks.
- Every page except login is protected by one login check in `app/__init__.py` (`before_request`). Admin pages also need `@admin_required`.
- Store only `user_id`, `username`, `role` in the session

---

## 4. HTML and CSS rules

- One base template `base.html`. Every page uses `{% extends "base.html" %}`
- Use real HTML elements: `<table>` for tables, `<form>` for forms, `<button>` for actions, `<label for="...">` for every input
- Forms that change data use `method="post"`
- Use HTML input rules for basic checks: `required`, `type="number" min="1"`, `type="email"`
- Jinja auto-escapes `{{ }}`. Never use `|safe` on user data.
- All styles in `static/style.css`. No inline `style="..."`.
- Use the CSS variables from `Design.md`. Don't invent new colors.
- Class names: lowercase with dashes: `.status-badge`, `.btn-danger`
- No JavaScript. If something seems to need JS (like adding item rows), find a plain-HTML way (see Design.md).

---

## 5. Testing rules

- Every rule in the database gets a test in `tests/test_rules.py` (run `python tests/test_rules.py`). It builds its own database `stockflow_test` and prints PASS or FAIL per test.
- Required tests (all 11 exist):
  1. Insert movement that makes stock negative -> must fail
  2. UPDATE on `stock_movements` -> must fail
  3. DELETE on `stock_movements` -> must fail
  4. Reserve more than available -> must fail with readable message
  5. Order with 3 items where item 3 is short -> nothing saved (check stock and reserved are unchanged)
  6. Stock drops below reorder level -> alert row appears
  7. Stock goes back up -> alert becomes RESOLVED
  8. Delete product with history -> blocked by FK
  9. Delete order -> its items are deleted too (cascade)
  10. Receive the same PO twice -> second fails
  11. `v_stock_reconciliation` returns 0 rows after data generation
- Run `race_demo.py --safe` and `--unsafe` after any change to ordering code
- Before marking a phase done, run all tests again

---

## 6. Git rules

- Commit small and often. One idea per commit.
- Message format: `area: what changed`. Example: `orders: release reservation before deducting on ship`
- Never commit `.env`, `backups/`, or `__pycache__/`
- `main` must always run. Try risky changes on a branch.

---

## 7. Rules for AI coding assistants

1. Read `Memory.md`, `Rules.md`, `Architecture.md` before starting. All business transactions live in `app/flows.py`; reuse them, don't write new stock SQL in routes.
2. Stay inside the stack: MySQL, Python, Flask, Jinja, HTML, CSS. Do not add JavaScript, an ORM, Docker, or any new library without asking.
3. Do not change the schema without updating `Architecture.md` in the same change
4. Do not "fix" a failing DB check by removing the check. Find out why the data is wrong.
5. Explain SQL in simple words in comments. The owner must be able to explain every line in the viva.
6. After finishing a task, add a line to the Progress log in `Memory.md`
7. If a request goes against a rule here, say so before doing it

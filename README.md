# StockFlow: Smart Inventory & Order Management

A DBMS course project. Small businesses track stock in spreadsheets, which leads to overselling,
wrong stock counts and no record of who changed what. StockFlow puts the safety **inside the database**:

- stock only changes through an **append-only ledger** (`stock_movements`), applied by a trigger
- orders **reserve** stock inside a **transaction** with a **row lock** (`SELECT ... FOR UPDATE`), so two orders can never sell the same last unit
- **triggers** raise and resolve reorder alerts by themselves
- **views** give the reports; **indexes** are measured before and after
- stock can be **rebuilt from history**, even "as of" any past date

Tech: **MySQL 8 + Python (Flask) + HTML + CSS**. No JavaScript, no ORM. Every query is plain SQL.

---

## 1. What you need

| Tool | Version | Check with |
|---|---|---|
| MySQL Server | 8.0.18 or newer | `mysql --version` (or look in MySQL Workbench) |
| Python | 3.11 or newer | `python --version` |
| VS Code | any | with the **Python** extension |

You need to know your MySQL **root password** (set when you installed MySQL).

## 2. Set up (first time, about 5 minutes)

Open the `stockflow` folder in VS Code, then open a terminal (**Terminal > New Terminal**).

**Step 1. Make a virtual environment and install the libraries**

Windows:
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
Mac / Linux:
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
You should now see `(venv)` at the start of the terminal line.
If VS Code asks "select interpreter", pick the one inside `venv`.

**Step 2. Create your `.env` file**

Copy `.env.example` to a new file named `.env` (Windows: `copy .env.example .env`, Mac: `cp .env.example .env`).
Open `.env` and change at least:
- `ROOT_PASSWORD` = your MySQL root password
- `DB_PASSWORD` = any password you like for the app's own MySQL user
- `SECRET_KEY` = any long random text

**Step 3. Build the database**
```
python scripts/setup_db.py
```
Type `yes` when asked. This creates the `stockflow` database (tables, procedures, triggers,
views, indexes) and a limited MySQL user `stockflow_app` for the web app.

**Step 4. Fill it with sample data** (about 2,400 rows, takes 10 to 30 seconds)
```
python data/generate_data.py
```
At the end it must say `Reconciliation mismatches: 0`.

**Step 5. Start the website**
```
python run.py
```
Open **http://127.0.0.1:5000** and log in:

| User | Password | Can do |
|---|---|---|
| `admin` | `admin123` | everything |
| `staff` | `staff123` | orders, purchases, customers, view stock and reports |

Stop the website with `Ctrl + C`. To start over with fresh data, run steps 3 and 4 again.

## 3. The DBMS demonstrations

| What | Command | What you should see |
|---|---|---|
| All database rules | `python tests/test_rules.py` | `11 of 11 tests passed` |
| Concurrency (lost update) | `python scripts/race_demo.py` | UNSAFE: last unit sold twice. SAFE: second order waits, then fails cleanly |
| Index experiment | `python data/generate_bench.py` then `python scripts/index_benchmark.py` | before/after table saved to `docs/index_results.md` |
| Backup | `python scripts/backup.py` | a `.sql` file in `backups/` |
| Restore test | `python scripts/restore_check.py` | `PASS: the backup restores completely.` |
| Concept queries | open `sql/06_reports.sql` in Workbench | joins, nested and correlated queries, window function, locking demo |

These scripts use their own databases (`stockflow_test`, `stockflow_demo`, `stockflow_bench`,
`stockflow_restore`), so your main data is never touched.

Backup and restore need the MySQL tools `mysqldump` and `mysql`. If the script says it can't
find them, put their folder in `MYSQL_BIN` in `.env`, for example
`C:\Program Files\MySQL\MySQL Server 8.0\bin`.

## 4. Viva demo (about 8 minutes)

1. Show the ER diagram (`docs/er_diagram.md`) and say the core idea: **"stock is the sum of the ledger"**.
2. Log in as `staff`. **New order** with 2 items, save, then **Confirm**. Open **Stock**: reserved went up.
3. New order asking for more than is available, **Confirm**: red message, nothing reserved (rollback).
4. **Ship** a confirmed order. Open the product's **History**: new `SALE_OUT` rows, running balance. Check **Alerts**.
5. **Rebuild check** page: 0 mismatches. In Workbench run `DELETE FROM stock_movements;` -> blocked by trigger.
6. Terminal: `python scripts/race_demo.py`.
7. Show `docs/index_results.md` and one EXPLAIN from `sql/06_reports.sql`.
8. Terminal: `python scripts/restore_check.py` -> PASS.

## 5. Where things are

```
sql/            the database: 01 schema, 02 procedures, 03 triggers, 04 views, 05 indexes, 06 report queries
app/flows.py    EVERY transaction (confirm, ship, cancel, receive, adjust). Start reading here.
app/db.py       connection + transaction() helper (commit or rollback)
app/routes/     one file per part of the website
app/templates/  the HTML pages
app/static/     style.css
data/           sample data and benchmark data generators
scripts/        setup, race demo, index benchmark, backup, restore check
tests/          test_rules.py
docs/           PRD, MRD, Architecture, Rules, Phase, Design, Memory, ER diagram, normalization
```

Read the docs in this order: `docs/Memory.md`, `docs/Architecture.md`, `docs/Rules.md`.

## 6. If something goes wrong

| Problem | Fix |
|---|---|
| `Access denied for user 'root'` | Wrong `ROOT_PASSWORD` in `.env` |
| `Access denied for user 'stockflow_app'` | Run `python scripts/setup_db.py` again after changing `DB_PASSWORD` |
| `Can't connect to MySQL server` | MySQL service is not running. Windows: open **Services**, start **MySQL80** |
| `venv\Scripts\activate` is blocked in PowerShell | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use the Command Prompt terminal |
| `ModuleNotFoundError: No module named 'flask'` | The venv is not active. Run the activate line from Step 1 |
| `The database already has data` | Run `python scripts/setup_db.py` first to empty it |
| Check constraint errors on an old MySQL | You need MySQL 8.0.18 or newer |

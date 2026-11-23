# Memory: StockFlow

The project's working memory. **Read this first** at the start of every work session (you or an AI assistant). It says where the project is, what was decided, and what not to forget.

Keep it short and current. Update it at the end of every session.

---

## 1. One-line summary

StockFlow is a MySQL-first inventory and order system for small businesses where stock is the sum of an append-only movement ledger, orders reserve stock inside locked transactions, and triggers raise reorder alerts automatically.

## 2. Current status

| Item | Value |
|---|---|
| Current phase | Code complete (Phases 0 to 8). Phase 9: report and viva prep |
| Last updated | 2026-11-22 |
| Next task | Run the project on your own laptop (README.md), then draw the ER diagram and write the report |
| Blockers | None |
| Submission date | _fill in_ |

## 3. Owner's skills (keep code inside these)

- Knows: DBMS / SQL, HTML, CSS, Python
- Does **not** use: JavaScript, React, ORMs, Docker
- Flask and Jinja are allowed because they are Python and HTML
- Every line of code must be something the owner can explain in the viva

## 4. Key decisions (do not change without a good reason)

| # | Decision | Why |
|---|---|---|
| D1 | MySQL 8.0.18+, InnoDB | Row locks, enforced CHECKs, triggers, `EXPLAIN ANALYZE` |
| D2 | Flask + Jinja + plain CSS, no JS | Matches owner's skills |
| D3 | Raw SQL with `mysql-connector-python`, no ORM | DBMS course: SQL must be visible |
| D4 | Stock changes **only** through `stock_movements` | Ledger is the truth; stock can always be rebuilt |
| D5 | Trigger `trg_movement_apply` updates `stock_levels` from each movement | Ledger and stock can never drift apart |
| D6 | Ledger is append-only (UPDATE/DELETE blocked by triggers + privileges) | Real audit trail |
| D7 | Reserve on Confirm, deduct on Ship, release on Cancel | Matches real shops; shows multi-step transactions |
| D8 | Python owns transactions; procedures never COMMIT | Avoids half-saved orders |
| D9 | Lock with `SELECT ... FOR UPDATE`, items in `product_id` order | Prevents overselling and deadlocks |
| D10 | Available stock and order totals are not stored, they come from views | 3NF, no update anomalies |
| D11 | `order_items.unit_price` stores price at time of sale | It is a fact of the order, not a copy |
| D12 | Products are deactivated, never deleted, once they have history | FK RESTRICT protects history |
| D13 | Main dataset ~2,000 rows; separate large benchmark DB for indexes | 2,000 rows too small to show index gains |
| D14 | Data generator uses the real flow functions and walks forward in time | Reconciliation passes, date reports make sense |
| D15 | Order form has 5 fixed item rows | No JS needed |
| D16 | Customers have no login; staff place orders | Keeps scope small |
| D17 | `trg_movement_apply` does UPDATE first, INSERT only if no row | `INSERT ... ON DUPLICATE KEY UPDATE` fails the CHECK on the negative "new row" |
| D18 | All stock/order transactions live in `app/flows.py`, used by both the web app and the data generator | One place to explain; same rules everywhere |
| D19 | `setup_db.py` builds any database from the same `sql/` files (no `USE` lines) | Main, test, demo and bench databases share one schema |
| D20 | Tests are one Python file `tests/test_rules.py` on its own `stockflow_test` database | Easier to read and run than SQL test files with error handlers |
| D21 | One login check for all pages (`before_request`), plus `@admin_required` | Simpler than a decorator on every route |

## 5. Things that are easy to forget

- Ship = **release reservation first, then deduct.** Other order breaks the CHECK.
- `SIGNAL ... MESSAGE_TEXT` needs a variable, not a `CONCAT(...)` directly
- `SELECT ... INTO` with no row leaves the variable unchanged: declare `DEFAULT NULL`, check for NULL
- Run `05_indexes.sql` only **after** recording the "before" benchmark. To repeat the experiment, run `generate_bench.py` again first (MySQL drops its own FK index once ours covers it, so ours can't be dropped)
- Run `ANALYZE TABLE` before reading plans; stale stats made MySQL think `order_items` had 1 row
- Never end a comment line in a `.sql` file with `;` or `$$` (setup_db.py reads statements line by line)
- `mysqldump` needs `--routines --triggers` or the restore has no procedures/triggers
- Race demo runs on `stockflow_demo`, not the main database
- MySQL error numbers: 1644 = our SIGNAL, 3819 = CHECK failed, 1451 = FK blocked delete, 1213 = deadlock
- `reference_id` in `stock_movements` is not a real FK (points to orders or POs). Mention as a trade-off.
- Fixed seeds (42) in data scripts

## 6. Database names

| Database | Use |
|---|---|
| `stockflow` | main, ~2,000 rows |
| `stockflow_demo` | race condition demo |
| `stockflow_bench` | index experiment, large data |
| `stockflow_restore` | restore test |
| `stockflow_test` | built by `tests/test_rules.py` |

## 7. Glossary

| Term | Meaning here |
|---|---|
| On hand | Units physically in the warehouse |
| Reserved | Units held for CONFIRMED orders, not yet shipped |
| Available | On hand minus reserved. What can still be sold. |
| Movement | One row in the ledger: +in or -out for one product in one warehouse |
| Ledger | The `stock_movements` table |
| Reconciliation | Checking stored stock equals the ledger sum |
| Reorder level | When available drops to this or lower, an alert opens |
| Lost update | Two people read the same value, both write, one change disappears |

## 8. Open questions

- [ ] Submission date and any required report format from the teacher?
- [ ] Does the teacher want the ER diagram in a specific notation (Chen vs crow's foot)?
- [ ] Is a live demo or a recorded video expected?
- [ ] Stock transfer between warehouses: include or skip? (not built; movement types already exist)

## 9. Progress log

Add one line per session, newest on top. Format: `date | phase | what was done | next`.

```
2026-11-22 | Phases 0-8 | Full codebase built and tested: schema, procs, triggers, views, indexes, Flask app, data generator, 11 rule tests, race demo, index benchmark, backup/restore | Run on own laptop, ER diagram, report
2026-11-22 | Planning | Wrote PRD, MRD, Architecture, Rules, Phase, Design, Memory | Start Phase 0
```

## 10. Results to keep for the report

Fill these in as you get them.

| Result | Value |
|---|---|
| Total rows in main dataset | about 2,400 (printed by generate_data.py) |
| Reconciliation mismatches | |
| Race demo unsafe: oversold runs out of 5 | |
| Race demo safe: oversold runs out of 5 | |
| Index results file | `docs/index_results.md` |
| Restore check | |

# MRD: StockFlow

Market Requirements Document. This explains **who has the problem, how they solve it today, and why that falls short.** It is the "why" behind the PRD.

Note: StockFlow is a course project, not a product for sale. This MRD keeps the project grounded in a real problem so the design choices make sense in the report and viva.

---

## 1. Target market

Small businesses that hold physical stock but are too small for a full ERP:

| Segment | Example | Size |
|---|---|---|
| Small wholesalers / distributors | Electrical goods, FMCG, hardware | 1 to 3 godowns, 100 to 2,000 SKUs |
| Retail shops with a back store | Mobile accessories, stationery, auto parts | 1 shop + 1 store room |
| Small online sellers | Sell on their own site plus a marketplace | 1 warehouse, orders from many channels |

Common traits:
- 2 to 15 staff, more than one person updating stock
- Buy from 10 to 50 suppliers
- No IT team
- Stock is a big part of their money, so mistakes hurt

## 2. How they manage today

| Method | What goes wrong |
|---|---|
| **Excel / Google Sheets** | No locking (two staff sell the last unit), easy to overwrite a cell, no reliable history, formulas break when rows are added |
| **Paper register** | Slow, no reports, hard to find anything |
| **Accounting software with an inventory module** (Tally, Vyapar and similar) | Built around billing and accounts first. Stock movement history and multi-warehouse reservations are limited or need add-ons. |
| **Cloud inventory tools** (Zoho Inventory and similar) | Work well, but cost money every month and feel heavy for a 3-person business |

## 3. Pain points (ranked)

1. **Overselling** - promising stock that is already gone. Leads to cancelled orders and angry customers.
2. **Not trusting the stock number** - nobody knows if the sheet is right, so staff count by hand.
3. **No audit trail** - when stock goes missing, there is no way to see who changed it.
4. **Running out without warning** - nobody notices a product is low until a customer asks for it.
5. **No quick answers** - "Which supplier do we buy most from?" or "What sold best last month?" needs manual work.

## 4. Market requirements

These are what any good solution must do. Each one maps to a PRD feature.

| # | Requirement | PRD feature |
|---|---|---|
| MR1 | Never sell stock that is not available, even when two people order at the same time | F3, D1 |
| MR2 | Keep a full, unchangeable history of every stock change, with who and when | F5 |
| MR3 | Be able to prove the current stock is correct | F6 |
| MR4 | Warn automatically when stock is low | F7 |
| MR5 | Handle more than one warehouse | F2 |
| MR6 | Track what was bought from which supplier | F4, F8 |
| MR7 | Give simple reports without manual work | F8 |
| MR8 | Different access for owner and staff | F9 |
| MR9 | Not lose data if the computer fails | D3 |
| MR10 | Stay fast as data grows | D2 |

## 5. What makes StockFlow different

1. **The ledger is the truth.** Stock is a running total of movements, not a number someone types. If the two ever disagree, the system shows it.
2. **Safety lives in the database, not the app.** Constraints, locks and triggers protect the data even if someone writes a bad query or uses a different app.
3. **Reserve, then deduct.** Confirming an order holds the stock. Shipping actually removes it. Cancelling gives it back. Spreadsheets cannot do this safely.
4. **Simple to run.** One database, one small Python app, plain web pages.

## 6. Why this is a good DBMS project

The business problem needs almost every topic in the DBMS syllabus, for a real reason:

| Business need | DBMS concept it needs |
|---|---|
| Products, suppliers, orders linked together | ER modelling, keys, foreign keys |
| No duplicate or contradicting data | Normalization to 3NF |
| Deleting an order removes its items, but deleting a product with history is blocked | Cascade vs restrict rules |
| Order with many items all succeeds or all fails | ACID transactions, rollback |
| Two staff ordering at once | Concurrency control, row locks |
| Automatic alerts and protected history | Triggers |
| Reusable order logic | Stored procedures |
| Reports | Joins, aggregates, nested queries, views |
| Staying fast | Indexing, query plans |
| Not losing data | Backup and recovery |

## 7. Success in market terms

If StockFlow were used by a real small business, success would mean:
- Zero oversold orders
- Stock count matches the ledger every day
- Staff can answer "what is low?" and "what sells best?" in one click
- Owner can see who changed any stock number

## 8. Limits (honest)

- No billing, GST or payments, so a real business would still need accounting software
- No barcode or mobile app
- Single-company, single-currency

# Design: StockFlow

How StockFlow looks and behaves on screen. Plain HTML + CSS, no JavaScript.

**Design goal:** a clean back-office tool. Fast to read, hard to make mistakes in. It should look like a neat admin panel, not a fancy website.

---

## 1. Principles

1. **Numbers first.** Stock and money are the main content. Right-align them, use a monospace-style digit font so columns line up.
2. **Status at a glance.** Every order, PO and alert shows a coloured status badge.
3. **Danger is obvious.** Cancel, deactivate and adjust use the red button and a separate "Are you sure?" page.
4. **Errors explain themselves.** Database error messages show in a red box at the top, in plain words.
5. **No surprises.** Every action button says exactly what it does: "Confirm order", not "Submit".

---

## 2. Colours (CSS variables)

Put these at the top of `static/style.css`. Use only these.

```css
:root {
  /* base */
  --bg:          #f6f7f9;   /* page background */
  --surface:     #ffffff;   /* cards, tables */
  --border:      #e2e5ea;
  --text:        #1f2933;
  --text-muted:  #616e7c;

  /* brand */
  --primary:       #2563eb;  /* main buttons, links */
  --primary-dark:  #1d4ed8;  /* hover */

  /* states */
  --success:     #15803d;   --success-bg: #dcfce7;
  --warning:     #b45309;   --warning-bg: #fef3c7;
  --danger:      #b91c1c;   --danger-bg:  #fee2e2;
  --info:        #1d4ed8;   --info-bg:    #dbeafe;
  --neutral:     #475569;   --neutral-bg: #e2e8f0;

  /* layout */
  --radius: 6px;
  --space-1: 4px;  --space-2: 8px;  --space-3: 12px;
  --space-4: 16px; --space-5: 24px; --space-6: 32px;
  --sidebar-width: 220px;
}
```

### Status badge colours

| Status | Colour |
|---|---|
| PENDING, DRAFT | neutral |
| CONFIRMED, ORDERED | info |
| SHIPPED, RECEIVED, RESOLVED | success |
| CANCELLED | danger |
| OPEN alert, low stock | warning |

CSS: `.badge`, plus `.badge-neutral`, `.badge-info`, `.badge-success`, `.badge-danger`, `.badge-warning`. Python passes the status, the template picks the class with a small Jinja dict.

---

## 3. Typography

```css
body {
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 14px;
  line-height: 1.5;
}
h1 { font-size: 22px; font-weight: 600; }
h2 { font-size: 17px; font-weight: 600; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.muted { color: var(--text-muted); }
```

- Money shows as `₹1,250.00` (format in Jinja with a small Python filter)
- Dates show as `22 Nov 2026, 14:05`
- Negative movement quantities show in red (`.qty-out`), positive in green (`.qty-in`)

---

## 4. Layout

```
+---------------------------------------------------------------+
| StockFlow                          Abhi (ADMIN)   [Log out]   |  <- top bar
+--------------+------------------------------------------------+
| Dashboard    |  Page title                     [Main action]  |
| Orders       |  ------------------------------------------    |
| Purchases    |  [flash messages]                              |
| Stock        |                                                |
| Ledger       |  [filters form]                                |
| Products     |                                                |
| Suppliers    |  [table or form]                               |
| Customers    |                                                |
| Reports      |                                                |
| Alerts (3)   |                                                |
| -- Admin --  |                                                |
| Warehouses   |                                                |
| Categories   |                                                |
| Users        |                                                |
+--------------+------------------------------------------------+
```

- Left sidebar, fixed width, current page highlighted
- Admin section in the sidebar only shows for Admin role
- Alerts link shows the count of OPEN alerts
- Content max width 1200px
- Use CSS Grid for the outer layout, Flexbox inside cards

---

## 5. Components

| Component | Class | Notes |
|---|---|---|
| Primary button | `.btn .btn-primary` | Blue. One per page section. |
| Secondary button | `.btn` | White with border |
| Danger button | `.btn .btn-danger` | Red. Cancel, deactivate, adjust down. |
| Card | `.card` | White, border, radius, padding `--space-5` |
| Number card | `.stat-card` | Big number + small label (dashboard) |
| Table | `.table` | Zebra rows, sticky header, numbers right-aligned |
| Badge | `.badge .badge-*` | Small rounded label |
| Flash message | `.flash .flash-success` / `.flash-error` | Full width at top of content |
| Form row | `.form-row` | Label above input, error text below in red |
| Filter bar | `.filters` | One row of inputs + "Apply" button, uses GET |
| Empty state | `.empty` | "No orders yet. [New order]" |

Tables:
- Header row uses `--neutral-bg`
- Low-stock rows get class `.row-warning` (light yellow background)
- Every table has an empty state message

---

## 6. Doing things without JavaScript

| Need | Plain HTML solution |
|---|---|
| Order with several items | New order form shows **5 fixed item rows** (product dropdown + quantity). Empty rows are ignored. Need more? Save, then "Add more items" opens 5 more rows. |
| "Are you sure?" before cancel / deactivate | Button links to a GET confirm page that explains what will happen, with a red POST button and a "Go back" link |
| Filtering | `<form method="get">` with inputs, values stay in the URL |
| Date range on reports | Two `<input type="date">` in a GET form, default last 30 days |
| Paging long lists | `?page=2` links, 25 rows per page, `LIMIT %s OFFSET %s` |
| Status buttons only when allowed | Jinja shows Confirm only if PENDING, Ship and Cancel only if CONFIRMED |
| Double-click submits twice | Database protects this (status check under lock). Second click shows "Order is already CONFIRMED". |

---

## 7. Pages

### 7.1 Login
- Centered card: username, password, "Log in" button
- Wrong details: "Wrong username or password" (never say which one)

### 7.2 Dashboard
```
[ Products: 120 ] [ Low stock: 9 ] [ Pending orders: 14 ] [ Sales this month: ₹4,82,310 ]

Open alerts                         Recent movements
Product   Warehouse  Avail  Level   Time   Product   Type       Qty   By
...                                 ...                SALE_OUT  -3   staff
[View all alerts]                   [View ledger]
```

### 7.3 Customer orders
- **List:** filters (status, warehouse, date range). Columns: Order #, Date, Customer, Warehouse, Items, Total, Status, [View].
- **New order:** customer dropdown, warehouse dropdown, 5 item rows (product + qty). Button "Save as pending". Each product option shows available stock for the chosen warehouse after first save.
- **Detail:** header (customer, warehouse, date, status badge), items table (product, qty, unit price, line total), total at bottom. Action buttons by status:
  - PENDING: "Confirm order" (primary), "Delete order" (danger)
  - CONFIRMED: "Ship order" (primary), "Cancel order" (danger)
  - SHIPPED / CANCELLED: no buttons, show date
- If confirm fails: red flash "Not enough stock for product 12: available 0, asked 2. Nothing was reserved."

### 7.4 Purchase orders
- **List:** supplier, warehouse, date, items, value, status
- **New PO:** supplier, warehouse, 5 item rows (product + qty + unit cost, cost defaults to product cost price)
- **Detail:** DRAFT -> "Mark as ordered"; ORDERED -> "Receive stock" (primary), "Cancel PO"
- After receive: green flash "Received 3 items. Stock updated."

### 7.5 Stock levels
- Filters: warehouse, category, "Low stock only" checkbox
- Columns: SKU, Product, Warehouse, On hand, Reserved, **Available** (bold), Reorder level, [History]
- Low rows highlighted yellow
- Admin sees an "Adjust" link per row

### 7.6 Stock adjustment (Admin)
- Shows current on hand / reserved / available
- Inputs: change (+ or - number), note (required, at least 5 characters)
- Text under the form: "This adds a new ADJUSTMENT entry to the ledger. It cannot be undone, only corrected with another adjustment."

### 7.7 Ledger (movement history)
- Filters: product, warehouse, type, date range
- Columns: Time, Product, Warehouse, Type, Change (+green / -red), Reference (link to order or PO), By, Note
- On a single product's page: running balance column and a box:
  - "Stored stock: 42 | Rebuilt from ledger: 42 | Match ✓" (green)
  - or "Mismatch: stored 42, ledger 40" (red)

### 7.8 Rebuild / reconciliation
- "As of" date-time input (default now)
- Table: product, warehouse, rebuilt quantity, stored quantity (only when "now"), difference
- Top summary: "0 mismatches across 360 stock rows" in green

### 7.9 Products, suppliers, customers, warehouses, categories
- List with search + "Add" button
- Add/edit form, one column, labels above inputs
- Deactivate via confirm page. Inactive rows shown greyed with "Inactive" badge.
- If delete is blocked by FK: "This product has stock history, so it can only be deactivated."

### 7.10 Reports
Tabs as links at the top: Low stock | Supplier summary | Best sellers | Daily sales
- **Low stock:** same as stock page with low-only filter, plus "Default supplier" column and "Create PO" link
- **Supplier summary:** month picker range; supplier, POs, units, value
- **Best sellers:** date range + "Top N" (10/20/50); rank, product, category, units sold, revenue
- **Daily sales:** date range; date, orders shipped, revenue. An HTML `<progress>` bar next to each row works as a chart without JS or inline styles.

### 7.11 Alerts
- Tabs: Open | Resolved
- Columns: Product, Warehouse, Available at alert, Reorder level, Raised at, Resolved at
- Note at top: "Alerts are created and resolved automatically by the database."

### 7.12 Users (Admin)
- List users, add user (username, password, role), deactivate

---

## 8. Messages (wording)

| Situation | Message |
|---|---|
| Order confirmed | Order #231 confirmed. Stock reserved for 3 items. |
| Order shipped | Order #231 shipped. Stock deducted. |
| Order cancelled | Order #231 cancelled. Reserved stock released. |
| Not enough stock | Not enough stock for "USB-C Cable 1m": available 0, asked 2. Nothing was reserved. |
| Wrong status | Order #231 is already SHIPPED, so it cannot be confirmed. |
| PO received twice | PO #48 is already RECEIVED. |
| CHECK failed | This change would make stock invalid (below zero or below reserved). Nothing was saved. |
| FK delete blocked | This record is used by other records and cannot be deleted. |
| Deadlock after retry | Too many people updated this at once. Please try again. |
| Not allowed | Only an admin can open this page. |
| Unknown error | Something went wrong. Nothing was saved. |

Tip: to show the product name instead of id in the "not enough stock" message, have `sp_reserve_item` look up the name and put it in `v_msg`.

---

## 9. Responsive and accessible

- Works at 1024px width and up (main target: laptop). Below 768px the sidebar stacks above the content.
- Tables scroll sideways on small screens (`overflow-x: auto` on a wrapper)
- Every input has a `<label>`
- Colour is never the only signal: badges also have text, red quantities also have a minus sign
- Text contrast at least 4.5:1 (the colours above pass on white)
- Focus outline visible on buttons and links (do not remove `outline`)

---

## 10. Templates list

```
templates/
  base.html
  _macros.html          badge(), money(), pagination(), filters()
  login.html
  dashboard.html
  confirm.html          generic "Are you sure?" page
  orders/list.html  orders/new.html  orders/detail.html
  purchases/list.html  purchases/new.html  purchases/detail.html
  stock/levels.html  stock/adjust.html  stock/ledger.html  stock/rebuild.html
  products/list.html  products/form.html
  suppliers/list.html  suppliers/form.html
  customers/list.html  customers/form.html
  warehouses/list.html  warehouses/form.html
  categories/list.html  categories/form.html
  reports/low_stock.html  reports/suppliers.html  reports/best_sellers.html  reports/daily_sales.html
  alerts.html
  users/list.html  users/form.html
  error.html            404 / 403 / 500
```

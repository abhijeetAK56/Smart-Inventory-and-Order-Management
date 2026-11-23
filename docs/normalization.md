# Normalization: from a spreadsheet to 3NF

This is how a small shop's spreadsheet becomes the StockFlow schema. Use it for the
normalization section of the report.

## Step 0: Unnormalized (UNF) - the spreadsheet

One row per order. Items are crammed into one cell.

| order_no | date | customer | customer_phone | customer_city | warehouse | warehouse_city | items |
|---|---|---|---|---|---|---|---|
| 101 | 01-10 | Ravi | 98xxxx | Purnia | Central | Delhi | "LED Bulb x2 @90, USB Cable x1 @150" |
| 102 | 02-10 | Ravi | 98xxxx | Purnia | West Hub | Mumbai | "LED Bulb x1 @90" |

Problems: you cannot add up quantities in the "items" cell, Ravi's phone is typed again on
every order, and the warehouse city is repeated too.

## Step 1: First Normal Form (1NF)

Rule: every cell holds one value, no repeating groups.
Split the items so each product in an order is its own row.

| order_no | date | customer | customer_phone | customer_city | warehouse | warehouse_city | product_sku | product_name | category | qty | price |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 101 | 01-10 | Ravi | 98xxxx | Purnia | Central | Delhi | ELE-01S | LED Bulb | Electrical | 2 | 90 |
| 101 | 01-10 | Ravi | 98xxxx | Purnia | Central | Delhi | MOB-01S | USB Cable | Mobile Acc. | 1 | 150 |

Key = (order_no, product_sku).

## Step 2: Second Normal Form (2NF)

Rule: 1NF, and no column depends on only PART of a composite key.

- `date, customer..., warehouse...` depend only on `order_no` -> move to **customer_orders**
- `product_name, category` depend only on `product_sku` -> move to **products**
- `qty, price` depend on the whole key (order + product) -> stay in **order_items**

## Step 3: Third Normal Form (3NF)

Rule: 2NF, and no column depends on another non-key column (no transitive dependency).

- In customer_orders: `customer_phone, customer_city` depend on `customer`, not on the order
  -> move to **customers**, keep only `customer_id`
- `warehouse_city` depends on `warehouse` -> move to **warehouses**, keep only `warehouse_id`
- In products: category name depends on the category -> move to **categories**, keep `category_id`

## Result (the StockFlow tables)

| Table | Key | Holds |
|---|---|---|
| customers | customer_id | name, email, phone, city |
| warehouses | warehouse_id | name, city |
| categories | category_id | name, description |
| products | product_id | sku, name, category_id, prices, reorder level |
| customer_orders | order_id | customer_id, warehouse_id, status, dates |
| order_items | (order_id, product_id) | quantity, unit_price |

The same steps give suppliers, purchase_orders and purchase_order_items, and stock_levels
(key = product_id + warehouse_id).

## Values we deliberately do NOT store

| Value | Why not | Where it comes from |
|---|---|---|
| Order total | Depends on the items; would go stale if an item changed (update anomaly) | view `v_order_totals` |
| Available stock | Depends on on_hand and reserved (transitive) | view `v_product_stock` |

## Two things that look like a 3NF problem but are not

1. **`order_items.unit_price`** looks like a copy of `products.unit_price`. It is not: it is the
   price on the day of the sale. Prices change later, and old orders must keep their old price.
   It depends on (order, product), the full key.
2. **`stock_levels.quantity_on_hand`** can be calculated from the ledger, so it is a stored
   derived value. We keep it on purpose for speed and so rows can be locked. The trigger
   `trg_movement_apply` keeps it in step with the ledger, and `v_stock_reconciliation`
   proves it always matches. Mention this as a controlled trade-off.

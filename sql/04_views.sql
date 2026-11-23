-- =====================================================================
-- StockFlow: 04_views.sql
-- Views used by the reports and pages. Values that can be calculated
-- (available stock, order totals) are calculated here, never stored.
-- =====================================================================

-- Stock per product per warehouse, with available stock
CREATE OR REPLACE VIEW v_product_stock AS
SELECT s.product_id,
       p.sku,
       p.name AS product_name,
       p.category_id,
       c.name AS category_name,
       s.warehouse_id,
       w.name AS warehouse_name,
       s.quantity_on_hand,
       s.quantity_reserved,
       s.quantity_on_hand - s.quantity_reserved AS available,
       p.reorder_level,
       p.is_active
FROM stock_levels s
JOIN products p   ON p.product_id = s.product_id
JOIN categories c ON c.category_id = p.category_id
JOIN warehouses w ON w.warehouse_id = s.warehouse_id;

-- Only the rows that are at or below the reorder level
CREATE OR REPLACE VIEW v_low_stock AS
SELECT ps.product_id,
       ps.sku,
       ps.product_name,
       ps.category_name,
       ps.warehouse_id,
       ps.warehouse_name,
       ps.quantity_on_hand,
       ps.quantity_reserved,
       ps.available,
       ps.reorder_level,
       p.default_supplier_id,
       sup.name AS supplier_name
FROM v_product_stock ps
JOIN products p        ON p.product_id = ps.product_id
LEFT JOIN suppliers sup ON sup.supplier_id = p.default_supplier_id
WHERE ps.available <= ps.reorder_level
  AND ps.is_active = TRUE;

-- One row per order with item count and total (total is never stored)
CREATE OR REPLACE VIEW v_order_totals AS
SELECT o.order_id,
       o.order_date,
       o.shipped_date,
       o.status,
       o.customer_id,
       cu.name AS customer_name,
       o.warehouse_id,
       w.name AS warehouse_name,
       COUNT(i.product_id) AS item_count,
       COALESCE(SUM(i.quantity * i.unit_price), 0) AS total_amount
FROM customer_orders o
JOIN customers cu      ON cu.customer_id = o.customer_id
JOIN warehouses w      ON w.warehouse_id = o.warehouse_id
LEFT JOIN order_items i ON i.order_id = o.order_id
GROUP BY o.order_id, o.order_date, o.shipped_date, o.status,
         o.customer_id, cu.name, o.warehouse_id, w.name;

-- Every line of every SHIPPED order (a sale happens when it ships)
CREATE OR REPLACE VIEW v_sales_lines AS
SELECT o.order_id,
       o.shipped_date,
       DATE(o.shipped_date) AS sale_date,
       i.product_id,
       p.sku,
       p.name AS product_name,
       c.name AS category_name,
       i.quantity,
       i.unit_price,
       i.quantity * i.unit_price AS line_total
FROM customer_orders o
JOIN order_items i ON i.order_id = o.order_id
JOIN products p    ON p.product_id = i.product_id
JOIN categories c  ON c.category_id = p.category_id
WHERE o.status = 'SHIPPED';

-- Sales per day
CREATE OR REPLACE VIEW v_daily_sales AS
SELECT sale_date,
       COUNT(DISTINCT order_id) AS orders_shipped,
       SUM(line_total) AS revenue
FROM v_sales_lines
GROUP BY sale_date;

-- Best sellers of all time (the reports page filters v_sales_lines by date instead)
CREATE OR REPLACE VIEW v_best_sellers AS
SELECT product_id,
       sku,
       product_name,
       category_name,
       SUM(quantity) AS units_sold,
       SUM(line_total) AS revenue
FROM v_sales_lines
GROUP BY product_id, sku, product_name, category_name;

-- What we bought from each supplier, per month (received POs only)
CREATE OR REPLACE VIEW v_supplier_purchase_summary AS
SELECT s.supplier_id,
       s.name AS supplier_name,
       DATE_FORMAT(po.received_date, '%Y-%m') AS month,
       COUNT(DISTINCT po.po_id) AS po_count,
       SUM(pi.quantity) AS total_quantity,
       SUM(pi.quantity * pi.unit_cost) AS total_value
FROM purchase_orders po
JOIN suppliers s             ON s.supplier_id = po.supplier_id
JOIN purchase_order_items pi ON pi.po_id = po.po_id
WHERE po.status = 'RECEIVED'
GROUP BY s.supplier_id, s.name, DATE_FORMAT(po.received_date, '%Y-%m');

-- Rows where stored stock does NOT match the ledger. Should always be empty.
CREATE OR REPLACE VIEW v_stock_reconciliation AS
SELECT s.product_id,
       s.warehouse_id,
       s.quantity_on_hand AS stored_qty,
       COALESCE(l.ledger_qty, 0) AS ledger_qty,
       s.quantity_on_hand - COALESCE(l.ledger_qty, 0) AS difference
FROM stock_levels s
LEFT JOIN (
    SELECT product_id, warehouse_id, SUM(change_qty) AS ledger_qty
    FROM stock_movements
    GROUP BY product_id, warehouse_id
) l ON l.product_id = s.product_id AND l.warehouse_id = s.warehouse_id
WHERE s.quantity_on_hand <> COALESCE(l.ledger_qty, 0);

-- The ledger with readable names
CREATE OR REPLACE VIEW v_movement_history AS
SELECT m.movement_id,
       m.created_at,
       m.product_id,
       p.sku,
       p.name AS product_name,
       m.warehouse_id,
       w.name AS warehouse_name,
       m.movement_type,
       m.change_qty,
       m.reference_type,
       m.reference_id,
       u.username,
       m.note
FROM stock_movements m
JOIN products p   ON p.product_id = m.product_id
JOIN warehouses w ON w.warehouse_id = m.warehouse_id
JOIN app_users u  ON u.user_id = m.performed_by;

-- =====================================================================
-- StockFlow: 06_reports.sql
-- Stand-alone queries for the project report and the viva.
-- Each one shows one DBMS concept. Run them one at a time in MySQL
-- Workbench (with the stockflow database selected) and copy the output.
-- This file is NOT run by setup_db.py.
-- =====================================================================


-- 1. MULTI-TABLE JOIN (5 tables)
-- Every order line with customer, product, category and warehouse.
SELECT o.order_id,
       o.order_date,
       cu.name AS customer,
       p.name  AS product,
       c.name  AS category,
       w.name  AS warehouse,
       i.quantity,
       i.quantity * i.unit_price AS line_total
FROM customer_orders o
JOIN customers cu  ON cu.customer_id = o.customer_id
JOIN order_items i ON i.order_id = o.order_id
JOIN products p    ON p.product_id = i.product_id
JOIN categories c  ON c.category_id = p.category_id
JOIN warehouses w  ON w.warehouse_id = o.warehouse_id
ORDER BY o.order_id DESC
LIMIT 20;


-- 2. GROUP BY + HAVING + nested query
-- Categories whose revenue is above the average category revenue.
SELECT category_name,
       SUM(line_total) AS revenue
FROM v_sales_lines
GROUP BY category_name
HAVING SUM(line_total) > (
    SELECT AVG(category_revenue)
    FROM (SELECT SUM(line_total) AS category_revenue
          FROM v_sales_lines
          GROUP BY category_name) AS per_category
)
ORDER BY revenue DESC;


-- 3. NESTED QUERY with NOT EXISTS
-- Products that have never been ordered.
SELECT p.sku, p.name
FROM products p
WHERE NOT EXISTS (
    SELECT 1 FROM order_items i WHERE i.product_id = p.product_id
);


-- 4. NESTED QUERY inside HAVING
-- Customers who spent more than the average customer (shipped orders only).
SELECT cu.customer_id, cu.name, SUM(t.total_amount) AS spent
FROM customers cu
JOIN v_order_totals t ON t.customer_id = cu.customer_id AND t.status = 'SHIPPED'
GROUP BY cu.customer_id, cu.name
HAVING SUM(t.total_amount) > (
    SELECT AVG(customer_total)
    FROM (SELECT SUM(total_amount) AS customer_total
          FROM v_order_totals
          WHERE status = 'SHIPPED'
          GROUP BY customer_id) AS per_customer
)
ORDER BY spent DESC;


-- 5. CORRELATED SUBQUERY
-- Each product's most recent stock movement.
SELECT p.sku,
       p.name,
       (SELECT MAX(m.created_at)
        FROM stock_movements m
        WHERE m.product_id = p.product_id) AS last_movement
FROM products p
ORDER BY last_movement DESC;


-- 6. STOCK AS OF A PAST DATE (rebuild from the ledger)
-- Change the date to any day in the last 6 months.
CALL sp_stock_as_of(DATE_SUB(NOW(), INTERVAL 30 DAY));


-- 7. RECONCILIATION: stored stock vs ledger. Should return 0 rows.
SELECT * FROM v_stock_reconciliation;


-- 8. WINDOW FUNCTION: running balance of one product per warehouse
SELECT m.created_at,
       w.name AS warehouse,
       m.movement_type,
       m.change_qty,
       SUM(m.change_qty) OVER (PARTITION BY m.warehouse_id
                               ORDER BY m.created_at, m.movement_id) AS balance
FROM stock_movements m
JOIN warehouses w ON w.warehouse_id = m.warehouse_id
WHERE m.product_id = 1
ORDER BY m.warehouse_id, m.created_at;


-- 9. TRIGGER DEMO: the ledger cannot be changed (both lines must FAIL)
-- UPDATE stock_movements SET change_qty = 100 WHERE movement_id = 1;
-- DELETE FROM stock_movements WHERE movement_id = 1;


-- 10. TRANSACTION + ROLLBACK DEMO (run line by line)
-- START TRANSACTION;
-- CALL sp_reserve_item(1, 1, 1);
-- SELECT quantity_reserved FROM stock_levels WHERE product_id = 1 AND warehouse_id = 1;
-- ROLLBACK;
-- SELECT quantity_reserved FROM stock_levels WHERE product_id = 1 AND warehouse_id = 1;


-- 11. LOCKING DEMO with two Workbench tabs (two sessions)
-- Tab A:  START TRANSACTION;
--         SELECT * FROM stock_levels WHERE product_id = 1 AND warehouse_id = 1 FOR UPDATE;
-- Tab B:  START TRANSACTION;
--         SELECT * FROM stock_levels WHERE product_id = 1 AND warehouse_id = 1 FOR UPDATE;
--         (Tab B now WAITS)
-- Tab A:  COMMIT;
--         (Tab B continues right away)
-- Tab B:  COMMIT;


-- 12. QUERY PLAN: see an index being used
EXPLAIN SELECT movement_id, change_qty, created_at
FROM stock_movements
WHERE product_id = 1 AND warehouse_id = 1
ORDER BY created_at DESC;

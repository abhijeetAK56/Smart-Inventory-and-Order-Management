-- =====================================================================
-- StockFlow: 05_indexes.sql
-- Extra indexes. Primary keys, UNIQUE columns and foreign keys already
-- have indexes. These four help the slowest queries.
-- For the index experiment, the benchmark database is built WITHOUT
-- this file first, so there is a real "before".
-- =====================================================================

-- Movement history of one product in one warehouse, newest first
CREATE INDEX idx_mov_prod_wh_time ON stock_movements (product_id, warehouse_id, created_at);

-- Sales in a date range (status = 'SHIPPED' AND order_date BETWEEN ...)
CREATE INDEX idx_orders_status_date ON customer_orders (status, order_date);

-- One customer's order history, newest first
CREATE INDEX idx_orders_customer_date ON customer_orders (customer_id, order_date);

-- Supplier summary: received POs in a date range
CREATE INDEX idx_po_status_received ON purchase_orders (status, received_date);

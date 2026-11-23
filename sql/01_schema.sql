-- =====================================================================
-- StockFlow: 01_schema.sql
-- All tables with primary keys, foreign keys, UNIQUE, CHECK and DEFAULT.
-- Run by scripts/setup_db.py (or in MySQL Workbench with the database selected).
-- =====================================================================

-- ---------- Master data ----------

CREATE TABLE categories (
    category_id  INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(60)  NOT NULL,
    description  VARCHAR(255),
    CONSTRAINT uq_categories_name UNIQUE (name)
);

CREATE TABLE suppliers (
    supplier_id     INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    contact_person  VARCHAR(100),
    email           VARCHAR(120),
    phone           VARCHAR(20),
    city            VARCHAR(60),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_suppliers_email UNIQUE (email)
);

CREATE TABLE warehouses (
    warehouse_id  INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(60) NOT NULL,
    city          VARCHAR(60) NOT NULL,
    CONSTRAINT uq_warehouses_name UNIQUE (name)
);

CREATE TABLE products (
    product_id           INT AUTO_INCREMENT PRIMARY KEY,
    sku                  VARCHAR(30)   NOT NULL,
    name                 VARCHAR(120)  NOT NULL,
    category_id          INT           NOT NULL,
    default_supplier_id  INT,
    unit_price           DECIMAL(10,2) NOT NULL,
    cost_price           DECIMAL(10,2) NOT NULL,
    reorder_level        INT           NOT NULL DEFAULT 10,
    is_active            BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at           DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_products_sku UNIQUE (sku),
    CONSTRAINT chk_products_price   CHECK (unit_price >= 0),
    CONSTRAINT chk_products_cost    CHECK (cost_price >= 0),
    CONSTRAINT chk_products_reorder CHECK (reorder_level >= 0),
    -- RESTRICT: a category that still has products cannot be deleted
    CONSTRAINT fk_products_category FOREIGN KEY (category_id)
        REFERENCES categories (category_id) ON DELETE RESTRICT,
    -- SET NULL: if the supplier is deleted, the product just has no default supplier
    CONSTRAINT fk_products_supplier FOREIGN KEY (default_supplier_id)
        REFERENCES suppliers (supplier_id) ON DELETE SET NULL
);

CREATE TABLE customers (
    customer_id  INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    email        VARCHAR(120),
    phone        VARCHAR(20),
    city         VARCHAR(60),
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_customers_email UNIQUE (email)
);

CREATE TABLE app_users (
    user_id        INT AUTO_INCREMENT PRIMARY KEY,
    username       VARCHAR(40)  NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    role           ENUM('ADMIN', 'STAFF') NOT NULL,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_users_username UNIQUE (username)
);

-- ---------- Stock ----------

-- One row per product per warehouse.
-- Available stock = quantity_on_hand - quantity_reserved (calculated in a view, not stored).
CREATE TABLE stock_levels (
    product_id         INT NOT NULL,
    warehouse_id       INT NOT NULL,
    quantity_on_hand   INT NOT NULL DEFAULT 0,
    quantity_reserved  INT NOT NULL DEFAULT 0,
    PRIMARY KEY (product_id, warehouse_id),
    CONSTRAINT chk_stock_onhand_not_negative   CHECK (quantity_on_hand >= 0),
    CONSTRAINT chk_stock_reserved_not_negative CHECK (quantity_reserved >= 0),
    CONSTRAINT chk_stock_reserved_le_onhand    CHECK (quantity_reserved <= quantity_on_hand),
    CONSTRAINT fk_stock_product FOREIGN KEY (product_id)
        REFERENCES products (product_id) ON DELETE RESTRICT,
    CONSTRAINT fk_stock_warehouse FOREIGN KEY (warehouse_id)
        REFERENCES warehouses (warehouse_id) ON DELETE RESTRICT
);

-- ---------- Purchase orders (buying from suppliers) ----------

CREATE TABLE purchase_orders (
    po_id          INT AUTO_INCREMENT PRIMARY KEY,
    supplier_id    INT NOT NULL,
    warehouse_id   INT NOT NULL,
    status         ENUM('DRAFT', 'ORDERED', 'RECEIVED', 'CANCELLED') NOT NULL DEFAULT 'DRAFT',
    order_date     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    received_date  DATETIME,
    created_by     INT NOT NULL,
    CONSTRAINT fk_po_supplier FOREIGN KEY (supplier_id)
        REFERENCES suppliers (supplier_id) ON DELETE RESTRICT,
    CONSTRAINT fk_po_warehouse FOREIGN KEY (warehouse_id)
        REFERENCES warehouses (warehouse_id) ON DELETE RESTRICT,
    CONSTRAINT fk_po_user FOREIGN KEY (created_by)
        REFERENCES app_users (user_id) ON DELETE RESTRICT
);

CREATE TABLE purchase_order_items (
    po_id       INT NOT NULL,
    product_id  INT NOT NULL,
    quantity    INT NOT NULL,
    unit_cost   DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (po_id, product_id),
    CONSTRAINT chk_po_items_qty  CHECK (quantity > 0),
    CONSTRAINT chk_po_items_cost CHECK (unit_cost >= 0),
    -- CASCADE: deleting a purchase order deletes its items
    CONSTRAINT fk_po_items_po FOREIGN KEY (po_id)
        REFERENCES purchase_orders (po_id) ON DELETE CASCADE,
    CONSTRAINT fk_po_items_product FOREIGN KEY (product_id)
        REFERENCES products (product_id) ON DELETE RESTRICT
);

-- ---------- Customer orders (selling) ----------

CREATE TABLE customer_orders (
    order_id      INT AUTO_INCREMENT PRIMARY KEY,
    customer_id   INT NOT NULL,
    warehouse_id  INT NOT NULL,
    status        ENUM('PENDING', 'CONFIRMED', 'SHIPPED', 'CANCELLED') NOT NULL DEFAULT 'PENDING',
    order_date    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    shipped_date  DATETIME,
    created_by    INT NOT NULL,
    CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id) ON DELETE RESTRICT,
    CONSTRAINT fk_orders_warehouse FOREIGN KEY (warehouse_id)
        REFERENCES warehouses (warehouse_id) ON DELETE RESTRICT,
    CONSTRAINT fk_orders_user FOREIGN KEY (created_by)
        REFERENCES app_users (user_id) ON DELETE RESTRICT
);

-- unit_price = price at the time of sale (a fact about this order line, so not a 3NF problem)
CREATE TABLE order_items (
    order_id    INT NOT NULL,
    product_id  INT NOT NULL,
    quantity    INT NOT NULL,
    unit_price  DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (order_id, product_id),
    CONSTRAINT chk_order_items_qty   CHECK (quantity > 0),
    CONSTRAINT chk_order_items_price CHECK (unit_price >= 0),
    -- CASCADE: deleting an order deletes its items
    CONSTRAINT fk_order_items_order FOREIGN KEY (order_id)
        REFERENCES customer_orders (order_id) ON DELETE CASCADE,
    CONSTRAINT fk_order_items_product FOREIGN KEY (product_id)
        REFERENCES products (product_id) ON DELETE RESTRICT
);

-- ---------- The ledger (audit log of every stock change) ----------

-- change_qty: + means stock came in, - means stock went out.
-- reference_id points to an order or a PO, so it cannot be a normal foreign key.
CREATE TABLE stock_movements (
    movement_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_id      INT NOT NULL,
    warehouse_id    INT NOT NULL,
    change_qty      INT NOT NULL,
    movement_type   ENUM('OPENING', 'PURCHASE_IN', 'SALE_OUT', 'ADJUSTMENT',
                         'RETURN_IN', 'TRANSFER_IN', 'TRANSFER_OUT') NOT NULL,
    reference_type  ENUM('PO', 'ORDER', 'MANUAL'),
    reference_id    INT,
    performed_by    INT NOT NULL,
    note            VARCHAR(255),
    created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT chk_movements_not_zero CHECK (change_qty <> 0),
    CONSTRAINT fk_movements_product FOREIGN KEY (product_id)
        REFERENCES products (product_id) ON DELETE RESTRICT,
    CONSTRAINT fk_movements_warehouse FOREIGN KEY (warehouse_id)
        REFERENCES warehouses (warehouse_id) ON DELETE RESTRICT,
    CONSTRAINT fk_movements_user FOREIGN KEY (performed_by)
        REFERENCES app_users (user_id) ON DELETE RESTRICT
);

-- ---------- Alerts (filled only by triggers) ----------

CREATE TABLE reorder_alerts (
    alert_id                INT AUTO_INCREMENT PRIMARY KEY,
    product_id              INT NOT NULL,
    warehouse_id            INT NOT NULL,
    available_at_alert      INT NOT NULL,
    reorder_level_at_alert  INT NOT NULL,
    status                  ENUM('OPEN', 'RESOLVED') NOT NULL DEFAULT 'OPEN',
    created_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at             DATETIME,
    CONSTRAINT fk_alerts_product FOREIGN KEY (product_id)
        REFERENCES products (product_id) ON DELETE RESTRICT,
    CONSTRAINT fk_alerts_warehouse FOREIGN KEY (warehouse_id)
        REFERENCES warehouses (warehouse_id) ON DELETE RESTRICT
);

-- =====================================================================
-- StockFlow: 02_procedures.sql
-- Stored procedures.
-- RULE: procedures never START TRANSACTION, COMMIT or ROLLBACK.
--       Python opens the transaction and decides to commit or roll back.
-- =====================================================================

DROP PROCEDURE IF EXISTS sp_add_movement;
DROP PROCEDURE IF EXISTS sp_reserve_item;
DROP PROCEDURE IF EXISTS sp_release_item;
DROP PROCEDURE IF EXISTS sp_stock_as_of;

DELIMITER $$

-- ---------------------------------------------------------------------
-- sp_add_movement: the ONLY way to change on-hand stock.
-- It adds one row to the ledger. The trigger trg_movement_apply then
-- updates stock_levels. p_created_at = NULL means "now".
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_add_movement(
    IN p_product_id    INT,
    IN p_warehouse_id  INT,
    IN p_change_qty    INT,
    IN p_type          VARCHAR(20),
    IN p_ref_type      VARCHAR(10),
    IN p_ref_id        INT,
    IN p_user_id       INT,
    IN p_note          VARCHAR(255),
    IN p_created_at    DATETIME(6)
)
BEGIN
    -- A manual adjustment must always say why it was made
    IF p_type = 'ADJUSTMENT' AND (p_note IS NULL OR CHAR_LENGTH(TRIM(p_note)) < 5) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'An adjustment needs a note of at least 5 characters.';
    END IF;

    INSERT INTO stock_movements
        (product_id, warehouse_id, change_qty, movement_type,
         reference_type, reference_id, performed_by, note, created_at)
    VALUES
        (p_product_id, p_warehouse_id, p_change_qty, p_type,
         p_ref_type, p_ref_id, p_user_id, p_note, IFNULL(p_created_at, NOW(6)));
END$$

-- ---------------------------------------------------------------------
-- sp_reserve_item: hold stock for a confirmed order.
-- FOR UPDATE locks the stock row, so a second order for the same
-- product waits here until the first transaction finishes.
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_reserve_item(
    IN p_product_id    INT,
    IN p_warehouse_id  INT,
    IN p_qty           INT
)
BEGIN
    DECLARE v_available INT DEFAULT NULL;
    DECLARE v_name VARCHAR(120) DEFAULT NULL;
    DECLARE v_msg VARCHAR(255);

    -- Step 1: lock the row and read what is available
    SELECT quantity_on_hand - quantity_reserved INTO v_available
    FROM stock_levels
    WHERE product_id = p_product_id
      AND warehouse_id = p_warehouse_id
    FOR UPDATE;

    -- Step 2: stop with a clear message if there is not enough
    IF v_available IS NULL OR v_available < p_qty THEN
        SELECT name INTO v_name FROM products WHERE product_id = p_product_id;
        SET v_msg = CONCAT('Not enough stock for "', IFNULL(v_name, p_product_id),
                           '": available ', IFNULL(v_available, 0), ', asked ', p_qty, '.');
        SET v_msg = LEFT(v_msg, 128);
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_msg;
    END IF;

    -- Step 3: reserve it (relative update, never "set to the number I read")
    UPDATE stock_levels
    SET quantity_reserved = quantity_reserved + p_qty
    WHERE product_id = p_product_id
      AND warehouse_id = p_warehouse_id;
END$$

-- ---------------------------------------------------------------------
-- sp_release_item: give back reserved stock (on ship or cancel).
-- The UPDATE itself locks the row.
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_release_item(
    IN p_product_id    INT,
    IN p_warehouse_id  INT,
    IN p_qty           INT
)
BEGIN
    UPDATE stock_levels
    SET quantity_reserved = quantity_reserved - p_qty
    WHERE product_id = p_product_id
      AND warehouse_id = p_warehouse_id;
END$$

-- ---------------------------------------------------------------------
-- sp_stock_as_of: rebuild stock from the ledger up to a point in time.
-- p_at = NULL means "now".
-- ---------------------------------------------------------------------
CREATE PROCEDURE sp_stock_as_of(IN p_at DATETIME(6))
BEGIN
    SELECT m.product_id,
           m.warehouse_id,
           p.sku,
           p.name AS product_name,
           w.name AS warehouse_name,
           SUM(m.change_qty) AS rebuilt_qty
    FROM stock_movements m
    JOIN products p   ON p.product_id = m.product_id
    JOIN warehouses w ON w.warehouse_id = m.warehouse_id
    WHERE m.created_at <= IFNULL(p_at, NOW(6))
    GROUP BY m.product_id, m.warehouse_id, p.sku, p.name, w.name
    ORDER BY p.sku, w.name;
END$$

DELIMITER ;

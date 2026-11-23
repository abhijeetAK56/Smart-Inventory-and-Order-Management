-- =====================================================================
-- StockFlow: 03_triggers.sql
-- Each trigger has exactly one job.
-- Chain: stock_movements -> stock_levels -> reorder_alerts
-- =====================================================================

DROP TRIGGER IF EXISTS trg_movement_apply;
DROP TRIGGER IF EXISTS trg_movement_no_update;
DROP TRIGGER IF EXISTS trg_movement_no_delete;
DROP TRIGGER IF EXISTS trg_stock_alert_ins;
DROP TRIGGER IF EXISTS trg_stock_alert_upd;

DELIMITER $$

-- ---------------------------------------------------------------------
-- Job: apply every new ledger row to stock_levels.
-- If the stock row does not exist yet, it is created.
-- If the result would be negative, the CHECK on stock_levels fails,
-- and the ledger INSERT fails too. So bad movements are never saved.
-- (We do UPDATE first and INSERT only if there was no row. A single
--  INSERT ... ON DUPLICATE KEY UPDATE does not work here, because MySQL
--  checks the CHECK rule on the negative "new row" before it sees the
--  row already exists.)
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_movement_apply
AFTER INSERT ON stock_movements
FOR EACH ROW
BEGIN
    UPDATE stock_levels
    SET quantity_on_hand = quantity_on_hand + NEW.change_qty
    WHERE product_id = NEW.product_id
      AND warehouse_id = NEW.warehouse_id;

    IF ROW_COUNT() = 0 THEN
        INSERT INTO stock_levels (product_id, warehouse_id, quantity_on_hand, quantity_reserved)
        VALUES (NEW.product_id, NEW.warehouse_id, NEW.change_qty, 0);
    END IF;
END$$

-- ---------------------------------------------------------------------
-- Job: the ledger can never be edited.
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_movement_no_update
BEFORE UPDATE ON stock_movements
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'The stock ledger cannot be changed. Add an ADJUSTMENT instead.';
END$$

-- ---------------------------------------------------------------------
-- Job: the ledger can never be deleted.
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_movement_no_delete
BEFORE DELETE ON stock_movements
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'The stock ledger cannot be deleted. Add an ADJUSTMENT instead.';
END$$

-- ---------------------------------------------------------------------
-- Job: open an alert when a NEW stock row starts at or below reorder level.
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_stock_alert_ins
AFTER INSERT ON stock_levels
FOR EACH ROW
BEGIN
    DECLARE v_level INT;
    DECLARE v_available INT;

    SELECT reorder_level INTO v_level FROM products WHERE product_id = NEW.product_id;
    SET v_available = NEW.quantity_on_hand - NEW.quantity_reserved;

    IF v_available <= v_level THEN
        INSERT INTO reorder_alerts (product_id, warehouse_id, available_at_alert, reorder_level_at_alert)
        VALUES (NEW.product_id, NEW.warehouse_id, v_available, v_level);
    END IF;
END$$

-- ---------------------------------------------------------------------
-- Job: when stock changes, open an alert if it is low,
-- or resolve the open alert if stock is fine again.
-- ---------------------------------------------------------------------
CREATE TRIGGER trg_stock_alert_upd
AFTER UPDATE ON stock_levels
FOR EACH ROW
BEGIN
    DECLARE v_level INT;
    DECLARE v_available INT;

    SELECT reorder_level INTO v_level FROM products WHERE product_id = NEW.product_id;
    SET v_available = NEW.quantity_on_hand - NEW.quantity_reserved;

    IF v_available <= v_level THEN
        -- Low: open an alert, but only if one is not already open
        IF NOT EXISTS (SELECT 1 FROM reorder_alerts
                       WHERE product_id = NEW.product_id
                         AND warehouse_id = NEW.warehouse_id
                         AND status = 'OPEN') THEN
            INSERT INTO reorder_alerts (product_id, warehouse_id, available_at_alert, reorder_level_at_alert)
            VALUES (NEW.product_id, NEW.warehouse_id, v_available, v_level);
        END IF;
    ELSE
        -- Fine again: close any open alert
        UPDATE reorder_alerts
        SET status = 'RESOLVED', resolved_at = NOW()
        WHERE product_id = NEW.product_id
          AND warehouse_id = NEW.warehouse_id
          AND status = 'OPEN';
    END IF;
END$$

DELIMITER ;

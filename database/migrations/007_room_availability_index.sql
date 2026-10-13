-- Speeds up room availability checks used by /rooms and booking confirmation.
-- Safe to run multiple times; does not change existing rows.

DELIMITER //

DROP PROCEDURE IF EXISTS fw_add_index_if_missing//
CREATE PROCEDURE fw_add_index_if_missing(
    IN table_name_value VARCHAR(64),
    IN index_name_value VARCHAR(64),
    IN index_definition_value TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = table_name_value
          AND INDEX_NAME = index_name_value
    ) THEN
        SET @fw_sql = CONCAT('ALTER TABLE `', table_name_value, '` ADD ', index_definition_value);
        PREPARE fw_stmt FROM @fw_sql;
        EXECUTE fw_stmt;
        DEALLOCATE PREPARE fw_stmt;
    END IF;
END//

DELIMITER ;

CALL fw_add_index_if_missing(
    'room_bookings',
    'idx_room_bookings_availability',
    'KEY idx_room_bookings_availability (room_id, status, check_in, check_out)'
);

DROP PROCEDURE IF EXISTS fw_add_index_if_missing;

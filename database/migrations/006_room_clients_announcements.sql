-- Adds room-booking client links and announcement delivery tables.
-- Run manually on the project database after backup:
-- mysql -u freewinds_user -p freewinds < database/migrations/006_room_clients_announcements.sql

DELIMITER //

DROP PROCEDURE IF EXISTS fw_add_column_if_missing//
CREATE PROCEDURE fw_add_column_if_missing(
    IN table_name_value VARCHAR(64),
    IN column_name_value VARCHAR(64),
    IN column_definition_value TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = table_name_value
          AND COLUMN_NAME = column_name_value
    ) THEN
        SET @fw_sql = CONCAT('ALTER TABLE `', table_name_value, '` ADD COLUMN `', column_name_value, '` ', column_definition_value);
        PREPARE fw_stmt FROM @fw_sql;
        EXECUTE fw_stmt;
        DEALLOCATE PREPARE fw_stmt;
    END IF;
END//

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

DROP PROCEDURE IF EXISTS fw_add_fk_if_missing//
CREATE PROCEDURE fw_add_fk_if_missing(
    IN table_name_value VARCHAR(64),
    IN constraint_name_value VARCHAR(64),
    IN constraint_definition_value TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = table_name_value
          AND CONSTRAINT_NAME = constraint_name_value
    ) THEN
        SET @fw_sql = CONCAT('ALTER TABLE `', table_name_value, '` ADD CONSTRAINT ', constraint_definition_value);
        PREPARE fw_stmt FROM @fw_sql;
        EXECUTE fw_stmt;
        DEALLOCATE PREPARE fw_stmt;
    END IF;
END//

DELIMITER ;

CALL fw_add_column_if_missing('room_bookings', 'client_id', 'BIGINT UNSIGNED NULL AFTER `room_id`');
CALL fw_add_index_if_missing('room_bookings', 'idx_room_bookings_client_id', 'KEY idx_room_bookings_client_id (client_id)');
CALL fw_add_fk_if_missing(
    'room_bookings',
    'fk_room_bookings_client',
    'fk_room_bookings_client FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE SET NULL ON UPDATE CASCADE'
);

UPDATE room_bookings rb
JOIN clients c ON c.telegram_user_id = rb.telegram_user_id
SET rb.client_id = c.id
WHERE rb.client_id IS NULL
  AND rb.telegram_user_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS announcements (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    media_url VARCHAR(500) NULL,
    media_type ENUM('photo', 'video') NULL,
    status ENUM('draft', 'ready', 'sent') NOT NULL DEFAULT 'draft',
    sent_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_announcements_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS announcement_recipients (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    announcement_id BIGINT UNSIGNED NOT NULL,
    client_id BIGINT UNSIGNED NOT NULL,
    status ENUM('pending', 'sent', 'failed') NOT NULL DEFAULT 'pending',
    error_message VARCHAR(500) NULL,
    sent_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_announcement_client (announcement_id, client_id),
    KEY idx_announcement_recipients_status (announcement_id, status),
    CONSTRAINT fk_announcement_recipients_announcement
        FOREIGN KEY (announcement_id) REFERENCES announcements (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_announcement_recipients_client
        FOREIGN KEY (client_id) REFERENCES clients (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP PROCEDURE IF EXISTS fw_add_column_if_missing;
DROP PROCEDURE IF EXISTS fw_add_index_if_missing;
DROP PROCEDURE IF EXISTS fw_add_fk_if_missing;

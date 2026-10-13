-- Safe database repair for an existing FreeWinds MySQL database.
-- It creates missing tables, adds missing columns/indexes, and inserts only default seed rows that do not exist.
-- Run on the selected project database, for example:
-- mysql -u freewinds_user -p freewinds < database/migrations/005_full_database_repair.sql

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
        SET @fw_sql = CONCAT(
            'ALTER TABLE `', table_name_value, '` ADD COLUMN `',
            column_name_value, '` ', column_definition_value
        );
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
        SET @fw_sql = CONCAT(
            'ALTER TABLE `', table_name_value, '` ADD ', index_definition_value
        );
        PREPARE fw_stmt FROM @fw_sql;
        EXECUTE fw_stmt;
        DEALLOCATE PREPARE fw_stmt;
    END IF;
END//

DELIMITER ;

CREATE TABLE IF NOT EXISTS clients (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    telegram_user_id BIGINT UNSIGNED NOT NULL,
    username VARCHAR(255) NULL,
    first_name VARCHAR(255) NULL,
    last_name VARCHAR(255) NULL,
    language_code VARCHAR(16) NULL,
    is_premium BOOLEAN NULL,
    phone VARCHAR(64) NULL,
    email VARCHAR(255) NULL,
    status ENUM('active', 'blocked') NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_seen DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_clients_telegram_user_id (telegram_user_id),
    KEY idx_clients_telegram_user_id (telegram_user_id),
    KEY idx_clients_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS services (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    price DECIMAL(10, 2) NOT NULL,
    price_unit VARCHAR(80) NOT NULL DEFAULT 'год',
    duration_minutes INT UNSIGNED NOT NULL DEFAULT 60,
    conditions TEXT NULL,
    image_url VARCHAR(500) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_services_name (name),
    KEY idx_services_active_sort (is_active, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CALL fw_add_column_if_missing('services', 'description', 'TEXT NULL AFTER `name`');
CALL fw_add_column_if_missing('services', 'price', 'DECIMAL(10, 2) NOT NULL DEFAULT 0 AFTER `description`');
CALL fw_add_column_if_missing('services', 'price_unit', 'VARCHAR(80) NOT NULL DEFAULT ''год'' AFTER `price`');
CALL fw_add_column_if_missing('services', 'duration_minutes', 'INT UNSIGNED NOT NULL DEFAULT 60 AFTER `price_unit`');
CALL fw_add_column_if_missing('services', 'conditions', 'TEXT NULL AFTER `duration_minutes`');
CALL fw_add_column_if_missing('services', 'image_url', 'VARCHAR(500) NULL AFTER `conditions`');
CALL fw_add_column_if_missing('services', 'is_active', 'BOOLEAN NOT NULL DEFAULT TRUE AFTER `image_url`');
CALL fw_add_column_if_missing('services', 'sort_order', 'INT NOT NULL DEFAULT 0 AFTER `is_active`');
CALL fw_add_column_if_missing('services', 'created_at', 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER `sort_order`');
CALL fw_add_column_if_missing('services', 'updated_at', 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER `created_at`');
CALL fw_add_index_if_missing('services', 'idx_services_active_sort', 'KEY idx_services_active_sort (is_active, sort_order)');

CREATE TABLE IF NOT EXISTS bookings (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    client_id BIGINT UNSIGNED NOT NULL,
    service_id BIGINT UNSIGNED NOT NULL,
    booking_date DATE NOT NULL,
    booking_time TIME NOT NULL,
    status ENUM('pending', 'confirmed', 'cancelled', 'completed') NOT NULL DEFAULT 'pending',
    active_slot_key TINYINT
        GENERATED ALWAYS AS (
            CASE WHEN status IN ('pending', 'confirmed') THEN 1 ELSE NULL END
        ) STORED,
    comment TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_bookings_client
        FOREIGN KEY (client_id) REFERENCES clients (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_bookings_service
        FOREIGN KEY (service_id) REFERENCES services (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    UNIQUE KEY uq_bookings_active_slot (service_id, booking_date, booking_time, active_slot_key),
    KEY idx_bookings_booking_date (booking_date),
    KEY idx_bookings_client_id (client_id),
    KEY idx_bookings_service_date_time (service_id, booking_date, booking_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CALL fw_add_column_if_missing('bookings', 'active_slot_key', 'TINYINT GENERATED ALWAYS AS (CASE WHEN status IN (''pending'', ''confirmed'') THEN 1 ELSE NULL END) STORED AFTER `status`');
CALL fw_add_column_if_missing('bookings', 'comment', 'TEXT NULL AFTER `active_slot_key`');
CALL fw_add_column_if_missing('bookings', 'created_at', 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER `comment`');
CALL fw_add_column_if_missing('bookings', 'updated_at', 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER `created_at`');
CALL fw_add_index_if_missing('bookings', 'idx_bookings_booking_date', 'KEY idx_bookings_booking_date (booking_date)');
CALL fw_add_index_if_missing('bookings', 'idx_bookings_client_id', 'KEY idx_bookings_client_id (client_id)');
CALL fw_add_index_if_missing('bookings', 'idx_bookings_service_date_time', 'KEY idx_bookings_service_date_time (service_id, booking_date, booking_time)');

CREATE TABLE IF NOT EXISTS admins (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(120) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(64) NOT NULL DEFAULT 'admin',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_admins_username (username),
    KEY idx_admins_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS menu_categories (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_menu_categories_name (name),
    KEY idx_menu_categories_active_sort (is_active, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CALL fw_add_column_if_missing('menu_categories', 'sort_order', 'INT NOT NULL DEFAULT 0 AFTER `name`');
CALL fw_add_column_if_missing('menu_categories', 'is_active', 'BOOLEAN NOT NULL DEFAULT TRUE AFTER `sort_order`');
CALL fw_add_column_if_missing('menu_categories', 'created_at', 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER `is_active`');
CALL fw_add_column_if_missing('menu_categories', 'updated_at', 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER `created_at`');
CALL fw_add_index_if_missing('menu_categories', 'idx_menu_categories_active_sort', 'KEY idx_menu_categories_active_sort (is_active, sort_order)');

CREATE TABLE IF NOT EXISTS menu_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    category_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    price DECIMAL(10, 2) NOT NULL,
    image_url VARCHAR(500) NULL,
    is_available BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_menu_items_category
        FOREIGN KEY (category_id) REFERENCES menu_categories (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    KEY idx_menu_items_category_sort (category_id, is_active, is_available, sort_order),
    KEY idx_menu_items_search (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CALL fw_add_column_if_missing('menu_items', 'description', 'TEXT NULL AFTER `name`');
CALL fw_add_column_if_missing('menu_items', 'price', 'DECIMAL(10, 2) NOT NULL DEFAULT 0 AFTER `description`');
CALL fw_add_column_if_missing('menu_items', 'image_url', 'VARCHAR(500) NULL AFTER `price`');
CALL fw_add_column_if_missing('menu_items', 'is_available', 'BOOLEAN NOT NULL DEFAULT TRUE AFTER `image_url`');
CALL fw_add_column_if_missing('menu_items', 'is_active', 'BOOLEAN NOT NULL DEFAULT TRUE AFTER `is_available`');
CALL fw_add_column_if_missing('menu_items', 'sort_order', 'INT NOT NULL DEFAULT 0 AFTER `is_active`');
CALL fw_add_column_if_missing('menu_items', 'created_at', 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER `sort_order`');
CALL fw_add_column_if_missing('menu_items', 'updated_at', 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER `created_at`');
CALL fw_add_index_if_missing('menu_items', 'idx_menu_items_category_sort', 'KEY idx_menu_items_category_sort (category_id, is_active, is_available, sort_order)');
CALL fw_add_index_if_missing('menu_items', 'idx_menu_items_search', 'KEY idx_menu_items_search (name)');

CREATE TABLE IF NOT EXISTS rooms (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(120) NULL,
    description TEXT NULL,
    price DECIMAL(10, 2) NOT NULL,
    guests_count INT UNSIGNED NOT NULL DEFAULT 1,
    area VARCHAR(80) NULL,
    sleeping_places VARCHAR(160) NULL,
    tags TEXT NULL,
    amenities TEXT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_rooms_active_sort (is_active, sort_order),
    KEY idx_rooms_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS room_photos (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    room_id BIGINT UNSIGNED NOT NULL,
    image_url VARCHAR(500) NOT NULL,
    alt_text VARCHAR(255) NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_room_photos_room
        FOREIGN KEY (room_id) REFERENCES rooms (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    KEY idx_room_photos_room_sort (room_id, is_primary, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS room_bookings (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    room_id BIGINT UNSIGNED NOT NULL,
    guest_name VARCHAR(255) NULL,
    guest_phone VARCHAR(80) NULL,
    guest_email VARCHAR(255) NULL,
    check_in DATE NOT NULL,
    check_out DATE NOT NULL,
    check_in_time TIME NULL,
    check_out_time TIME NULL,
    status ENUM('pending', 'confirmed', 'cancelled', 'completed') NOT NULL DEFAULT 'confirmed',
    comment TEXT NULL,
    telegram_user_id BIGINT UNSIGNED NULL,
    telegram_link_token VARCHAR(96) NULL,
    telegram_link_expires_at DATETIME NULL,
    admin_notified_at DATETIME NULL,
    client_notified_status ENUM('pending', 'confirmed', 'cancelled', 'completed') NULL,
    client_notified_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_room_bookings_room
        FOREIGN KEY (room_id) REFERENCES rooms (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    KEY idx_room_bookings_room_dates (room_id, check_in, check_out),
    KEY idx_room_bookings_status (status),
    KEY idx_room_bookings_telegram_token (telegram_link_token),
    KEY idx_room_bookings_telegram_user (telegram_user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CALL fw_add_column_if_missing('room_bookings', 'check_in_time', 'TIME NULL AFTER `check_out`');
CALL fw_add_column_if_missing('room_bookings', 'check_out_time', 'TIME NULL AFTER `check_in_time`');
CALL fw_add_column_if_missing('room_bookings', 'telegram_user_id', 'BIGINT UNSIGNED NULL AFTER `comment`');
CALL fw_add_column_if_missing('room_bookings', 'telegram_link_token', 'VARCHAR(96) NULL AFTER `telegram_user_id`');
CALL fw_add_column_if_missing('room_bookings', 'telegram_link_expires_at', 'DATETIME NULL AFTER `telegram_link_token`');
CALL fw_add_column_if_missing('room_bookings', 'admin_notified_at', 'DATETIME NULL AFTER `telegram_link_expires_at`');
CALL fw_add_column_if_missing('room_bookings', 'client_notified_status', 'ENUM(''pending'', ''confirmed'', ''cancelled'', ''completed'') NULL AFTER `admin_notified_at`');
CALL fw_add_column_if_missing('room_bookings', 'client_notified_at', 'DATETIME NULL AFTER `client_notified_status`');
CALL fw_add_index_if_missing('room_bookings', 'idx_room_bookings_telegram_token', 'KEY idx_room_bookings_telegram_token (telegram_link_token)');
CALL fw_add_index_if_missing('room_bookings', 'idx_room_bookings_telegram_user', 'KEY idx_room_bookings_telegram_user (telegram_user_id)');

CREATE TABLE IF NOT EXISTS site_settings (
    setting_key VARCHAR(120) NOT NULL,
    setting_value TEXT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (setting_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS home_banners (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    image_url VARCHAR(500) NOT NULL,
    title VARCHAR(255) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_home_banners_active_sort (is_active, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS service_photos (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    service_id BIGINT UNSIGNED NOT NULL,
    image_url VARCHAR(500) NOT NULL,
    alt_text VARCHAR(255) NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_service_photos_service
        FOREIGN KEY (service_id) REFERENCES services (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    KEY idx_service_photos_service_sort (service_id, is_primary, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO menu_categories (name, sort_order, is_active)
SELECT seed.name, seed.sort_order, TRUE
FROM (
    SELECT 'Сніданки' AS name, 10 AS sort_order
    UNION ALL SELECT 'Гарніри', 20
    UNION ALL SELECT 'Салати', 30
    UNION ALL SELECT 'Супи', 40
    UNION ALL SELECT 'Напої', 50
) AS seed
WHERE NOT EXISTS (
    SELECT 1 FROM menu_categories c WHERE c.name = seed.name
);

INSERT INTO menu_items (category_id, name, description, price, image_url, is_available, is_active, sort_order)
SELECT c.id, seed.name, seed.description, seed.price, seed.image_url, TRUE, TRUE, seed.sort_order
FROM (
    SELECT 'Сніданки' AS category_name, 'Карпатський сніданок' AS name, 'Яйця, сир, зелень та теплий хліб.' AS description, 150.00 AS price, '/static/img/vodogray.png' AS image_url, 10 AS sort_order
    UNION ALL SELECT 'Сніданки', 'Сирники зі сметаною', 'Ніжні сирники з ягідним соусом.', 180.00, '/static/img/vodogray.png', 20
    UNION ALL SELECT 'Гарніри', 'Печена картопля', 'Картопля з травами та часниковою олією.', 90.00, '/static/img/vodogray.png', 10
    UNION ALL SELECT 'Салати', 'Салат із бринзою', 'Свіжі овочі, бринза та насіння.', 140.00, '/static/img/vodogray.png', 10
    UNION ALL SELECT 'Супи', 'Грибна юшка', 'Лісові гриби, вершки та грінки.', 160.00, '/static/img/vodogray.png', 10
    UNION ALL SELECT 'Напої', 'Карпатський чай', 'Травʼяний чай із медом.', 70.00, '/static/img/vodogray.png', 10
) AS seed
JOIN menu_categories c ON c.name = seed.category_name
WHERE NOT EXISTS (
    SELECT 1 FROM menu_items mi WHERE mi.name = seed.name AND mi.category_id = c.id
);

INSERT INTO services (name, description, price, price_unit, duration_minutes, image_url, is_active, sort_order)
SELECT seed.name, seed.description, seed.price, seed.price_unit, seed.duration_minutes, seed.image_url, TRUE, seed.sort_order
FROM (
    SELECT 'Басейн' AS name, 'Відпочинок у басейні серед гір.' AS description, 150.00 AS price, 'год' AS price_unit, 60 AS duration_minutes, '/static/img/vodogray.png' AS image_url, 10 AS sort_order
    UNION ALL SELECT 'Чани', 'Теплі чани для релаксу після прогулянки.', 180.00, 'год', 60, '/static/img/vodogray.png', 20
    UNION ALL SELECT 'Баня', 'Класична баня для відновлення сил.', 50.00, 'год', 60, '/static/img/vodogray.png', 30
    UNION ALL SELECT 'Більярд', 'Більярд для вечірнього відпочинку.', 360.00, 'год', 60, '/static/img/vodogray.png', 40
) AS seed
WHERE NOT EXISTS (
    SELECT 1 FROM services s WHERE s.name = seed.name
);

INSERT INTO service_photos (service_id, image_url, alt_text, is_primary, sort_order, created_at)
SELECT s.id, s.image_url, s.name, TRUE, 0, NOW()
FROM services s
WHERE s.image_url IS NOT NULL
  AND s.image_url <> ''
  AND NOT EXISTS (
      SELECT 1
      FROM service_photos sp
      WHERE sp.service_id = s.id
  );

INSERT INTO site_settings (setting_key, setting_value, updated_at)
SELECT 'home_hero_image', '/static/img/vodogray.png', NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM site_settings WHERE setting_key = 'home_hero_image'
);

INSERT INTO rooms (
    name, category, description, price, guests_count, area, sleeping_places,
    tags, amenities, is_active, sort_order, created_at, updated_at
)
SELECT seed.name, seed.category, seed.description, seed.price, seed.guests_count, seed.area, seed.sleeping_places,
       seed.tags, seed.amenities, seed.is_active, seed.sort_order, NOW(), NOW()
FROM (
    SELECT
        'Лісова хатина' AS name,
        'Котедж' AS category,
        'Деревʼяна хатина на узліссі з каміном.' AS description,
        2400.00 AS price,
        2 AS guests_count,
        '25 м²' AS area,
        '1 спальня' AS sleeping_places,
        'Тераса\nКамін\nВид на ліс' AS tags,
        'Двоспальне ліжко\nКамін\nДуш і ванна\nWi-Fi\nКавова зона\nТераса\nВид на ліс\nОпалення' AS amenities,
        TRUE AS is_active,
        10 AS sort_order
    UNION ALL
    SELECT
        'Гірський люкс',
        'Люкс',
        'Панорамні вікна на хребти Карпат.',
        3800.00,
        4,
        '40 м²',
        '2 спальні',
        'Панорама\nСімейний номер\nБалкон',
        'Двоспальне ліжко\nДодаткове спальне місце\nДуш і ванна\nWi-Fi\nКавова зона\nБалкон\nВид на гори\nОпалення',
        TRUE,
        20
) AS seed
WHERE NOT EXISTS (
    SELECT 1 FROM rooms r WHERE r.name = seed.name
);

INSERT INTO room_photos (room_id, image_url, alt_text, is_primary, sort_order, created_at)
SELECT r.id, '/static/img/vodogray.png', r.name, TRUE, 10, NOW()
FROM rooms r
WHERE NOT EXISTS (
    SELECT 1 FROM room_photos rp WHERE rp.room_id = r.id
);

DROP PROCEDURE IF EXISTS fw_add_column_if_missing;
DROP PROCEDURE IF EXISTS fw_add_index_if_missing;

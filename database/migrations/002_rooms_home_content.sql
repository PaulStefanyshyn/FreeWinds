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
    status ENUM('pending', 'confirmed', 'cancelled', 'completed') NOT NULL DEFAULT 'confirmed',
    comment TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_room_bookings_room
        FOREIGN KEY (room_id) REFERENCES rooms (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    KEY idx_room_bookings_room_dates (room_id, check_in, check_out),
    KEY idx_room_bookings_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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

INSERT INTO rooms (
    name, category, description, price, guests_count, area, sleeping_places,
    tags, amenities, is_active, sort_order, created_at, updated_at
)
SELECT *
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
        10 AS sort_order,
        NOW() AS created_at,
        NOW() AS updated_at
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
        20,
        NOW(),
        NOW()
) AS seed
WHERE NOT EXISTS (
    SELECT 1 FROM rooms r WHERE r.name = seed.name
);

INSERT INTO site_settings (setting_key, setting_value, updated_at)
VALUES ('home_hero_image', '/static/img/vodogray.png', NOW())
ON DUPLICATE KEY UPDATE setting_key = setting_key;

INSERT INTO room_photos (room_id, image_url, alt_text, is_primary, sort_order, created_at)
SELECT r.id, '/static/img/vodogray.png', r.name, TRUE, 10, NOW()
FROM rooms r
WHERE NOT EXISTS (
    SELECT 1 FROM room_photos rp WHERE rp.room_id = r.id
);

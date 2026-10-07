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

INSERT INTO menu_categories (name, sort_order, is_active)
VALUES
    ('Сніданки', 10, TRUE),
    ('Гарніри', 20, TRUE),
    ('Салати', 30, TRUE),
    ('Супи', 40, TRUE),
    ('Напої', 50, TRUE)
ON DUPLICATE KEY UPDATE
    sort_order = VALUES(sort_order),
    is_active = VALUES(is_active);

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

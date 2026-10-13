ALTER TABLE services
    ADD COLUMN price_unit VARCHAR(80) NOT NULL DEFAULT 'год' AFTER price,
    ADD COLUMN conditions TEXT NULL AFTER duration_minutes;

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

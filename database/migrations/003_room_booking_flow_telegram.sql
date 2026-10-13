ALTER TABLE room_bookings
    ADD COLUMN check_in_time TIME NULL AFTER check_out,
    ADD COLUMN check_out_time TIME NULL AFTER check_in_time,
    ADD COLUMN telegram_user_id BIGINT UNSIGNED NULL AFTER comment,
    ADD COLUMN telegram_link_token VARCHAR(96) NULL AFTER telegram_user_id,
    ADD COLUMN telegram_link_expires_at DATETIME NULL AFTER telegram_link_token,
    ADD COLUMN admin_notified_at DATETIME NULL AFTER telegram_link_expires_at,
    ADD COLUMN client_notified_status ENUM('pending', 'confirmed', 'cancelled', 'completed') NULL AFTER admin_notified_at,
    ADD COLUMN client_notified_at DATETIME NULL AFTER client_notified_status,
    ADD KEY idx_room_bookings_telegram_token (telegram_link_token),
    ADD KEY idx_room_bookings_telegram_user (telegram_user_id);

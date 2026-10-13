from contextlib import contextmanager
from datetime import date, datetime, time, timedelta

from config import MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER

try:
    import mysql.connector
    from mysql.connector import Error, IntegrityError
except ImportError:
    mysql = None
    Error = Exception
    IntegrityError = Exception


BOOKING_STATUSES = ('pending', 'confirmed', 'cancelled', 'completed')
STATUS_LABELS = {
    'pending': 'Очікує',
    'confirmed': 'Підтверджено',
    'cancelled': 'Скасовано',
    'completed': 'Завершено',
}
DEFAULT_SLOTS = ('10:00', '12:00', '14:00', '16:00', '18:00', '20:00')
ROOM_BLOCKING_STATUSES = ('pending', 'confirmed')
ANNOUNCEMENT_STATUSES = ('draft', 'ready', 'sent')


class DatabaseUnavailable(RuntimeError):
    pass


@contextmanager
def get_connection():
    if mysql is None:
        raise DatabaseUnavailable('mysql-connector-python is not installed')

    connection = mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        database=MYSQL_DATABASE,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        autocommit=False,
    )
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def fetch_one(query, params=None):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params or ())
        return cursor.fetchone()


def fetch_all(query, params=None):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params or ())
        return cursor.fetchall()


def normalize_time(value):
    if isinstance(value, time):
        return value.strftime('%H:%M')
    return str(value)[:5]


def serialize_client(client):
    if not client:
        return None

    return {
        'id': client['id'],
        'telegram_user_id': client['telegram_user_id'],
        'username': client.get('username'),
        'first_name': client.get('first_name'),
        'last_name': client.get('last_name'),
        'language_code': client.get('language_code'),
        'phone': client.get('phone'),
        'email': client.get('email'),
        'status': client.get('status'),
        'last_seen': client.get('last_seen').isoformat() if client.get('last_seen') else None,
    }


def serialize_service(service):
    photos = service.get('photos') if isinstance(service, dict) else None
    return {
        'id': service['id'],
        'name': service['name'],
        'description': service.get('description'),
        'price': float(service['price']) if service.get('price') is not None else None,
        'price_unit': service.get('price_unit') or 'год',
        'duration_minutes': service.get('duration_minutes'),
        'conditions': service.get('conditions'),
        'image_url': service.get('image_url'),
        'is_active': bool(service.get('is_active')),
        'sort_order': service.get('sort_order') or 0,
        'photos': photos or [],
    }


def serialize_booking(booking):
    return {
        'id': booking['id'],
        'client_id': booking['client_id'],
        'service_id': booking['service_id'],
        'service_name': booking.get('service_name'),
        'booking_date': booking['booking_date'].isoformat(),
        'booking_time': normalize_time(booking['booking_time']),
        'status': booking['status'],
        'comment': booking.get('comment'),
        'created_at': serialize_datetime(booking.get('created_at')),
    }


def parse_booking_date(value, field_label='Дата'):
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        raise ValueError(f'{field_label} має некоректний формат')


def serialize_datetime(value):
    return value.isoformat(sep=' ', timespec='minutes') if value else None


def client_display_name(client):
    parts = [client.get('first_name'), client.get('last_name')]
    name = ' '.join(part for part in parts if part)
    return name or client.get('username') or f"Telegram {client.get('telegram_user_id')}"


def serialize_admin_booking(booking):
    return {
        'id': booking['id'],
        'client_id': booking['client_id'],
        'service_id': booking['service_id'],
        'service_name': booking.get('service_name'),
        'booking_date': booking['booking_date'].isoformat(),
        'booking_time': normalize_time(booking['booking_time']),
        'status': booking['status'],
        'comment': booking.get('comment'),
        'created_at': serialize_datetime(booking.get('created_at')),
        'updated_at': serialize_datetime(booking.get('updated_at')),
        'client_name': client_display_name(booking),
        'telegram_user_id': booking.get('telegram_user_id'),
        'username': booking.get('username'),
        'phone': booking.get('phone'),
        'email': booking.get('email'),
    }


def serialize_menu_category(category):
    return {
        'id': category['id'],
        'name': category['name'],
        'sort_order': category.get('sort_order') or 0,
        'is_active': bool(category.get('is_active')),
        'items_count': category.get('items_count', 0),
        'created_at': serialize_datetime(category.get('created_at')),
        'updated_at': serialize_datetime(category.get('updated_at')),
    }


def serialize_menu_item(item):
    return {
        'id': item['id'],
        'category_id': item['category_id'],
        'category_name': item.get('category_name'),
        'name': item['name'],
        'description': item.get('description'),
        'price': float(item['price']) if item.get('price') is not None else None,
        'image_url': item.get('image_url'),
        'is_available': bool(item.get('is_available')),
        'is_active': bool(item.get('is_active')),
        'sort_order': item.get('sort_order') or 0,
        'created_at': serialize_datetime(item.get('created_at')),
        'updated_at': serialize_datetime(item.get('updated_at')),
    }


def upsert_client_from_telegram(user):
    telegram_user_id = user.get('id')
    if not telegram_user_id:
        raise ValueError('Telegram user id is required')

    params = {
        'telegram_user_id': telegram_user_id,
        'username': user.get('username'),
        'first_name': user.get('first_name'),
        'last_name': user.get('last_name'),
        'language_code': user.get('language_code'),
        'is_premium': user.get('is_premium'),
    }

    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            INSERT INTO clients (
                telegram_user_id, username, first_name, last_name,
                language_code, is_premium, status, created_at, updated_at, last_seen
            )
            VALUES (
                %(telegram_user_id)s, %(username)s, %(first_name)s, %(last_name)s,
                %(language_code)s, %(is_premium)s, 'active', NOW(), NOW(), NOW()
            )
            ON DUPLICATE KEY UPDATE
                username = VALUES(username),
                first_name = VALUES(first_name),
                last_name = VALUES(last_name),
                language_code = VALUES(language_code),
                is_premium = VALUES(is_premium),
                updated_at = NOW(),
                last_seen = NOW()
            """,
            params,
        )
        cursor.execute(
            "SELECT * FROM clients WHERE telegram_user_id = %s",
            (telegram_user_id,),
        )
        client = cursor.fetchone()
        connection.commit()
        return client


def serialize_service_photo(photo):
    return {
        'id': photo['id'],
        'service_id': photo['service_id'],
        'image_url': photo['image_url'],
        'alt_text': photo.get('alt_text'),
        'is_primary': bool(photo.get('is_primary')),
        'sort_order': photo.get('sort_order') or 0,
        'created_at': serialize_datetime(photo.get('created_at')),
    }


def get_service_photos(service_id):
    rows = fetch_all(
        """
        SELECT *
        FROM service_photos
        WHERE service_id = %s
        ORDER BY is_primary DESC, sort_order, id
        """,
        (service_id,),
    )
    return [serialize_service_photo(row) for row in rows]


def get_services(include_inactive=False, include_photos=False, search=None):
    clauses = []
    params = []
    if not include_inactive:
        clauses.append('is_active = 1')
    if search:
        like = f"%{search}%"
        clauses.append('(name LIKE %s OR description LIKE %s OR conditions LIKE %s)')
        params.extend([like, like, like])
    where_clause = ' AND '.join(clauses) if clauses else '1=1'
    services = fetch_all(
        f"""
        SELECT id, name, description, price, price_unit, duration_minutes, conditions,
               image_url, is_active, sort_order, created_at, updated_at
        FROM services
        WHERE {where_clause}
        ORDER BY sort_order, id
        """,
        tuple(params),
    )
    result = [serialize_service(service) for service in services]
    if include_photos:
        for service in result:
            service['photos'] = get_service_photos(service['id'])
            if not service.get('image_url') and service['photos']:
                service['image_url'] = service['photos'][0]['image_url']
    return result


def get_service(service_id, include_photos=False):
    row = fetch_one(
        """
        SELECT id, name, description, price, price_unit, duration_minutes, conditions,
               image_url, is_active, sort_order, created_at, updated_at
        FROM services
        WHERE id = %s
        """,
        (service_id,),
    )
    if not row:
        return None
    service = serialize_service(row)
    if include_photos:
        service['photos'] = get_service_photos(service_id)
        if not service.get('image_url') and service['photos']:
            service['image_url'] = service['photos'][0]['image_url']
    return service


def save_service(data, service_id=None):
    name = (data.get('name') or '').strip()
    if not name:
        raise ValueError('Вкажіть назву послуги')

    price = data.get('price')
    if price in (None, ''):
        raise ValueError('Вкажіть ціну послуги')

    duration_minutes = int(data.get('duration_minutes') or 60)
    if duration_minutes <= 0:
        raise ValueError('Тривалість повинна бути більшою за 0')

    payload = {
        'name': name,
        'description': (data.get('description') or '').strip() or None,
        'price': price,
        'price_unit': (data.get('price_unit') or '').strip() or 'год',
        'duration_minutes': duration_minutes,
        'conditions': (data.get('conditions') or '').strip() or None,
        'image_url': (data.get('image_url') or '').strip() or None,
        'is_active': bool(data.get('is_active')),
        'sort_order': int(data.get('sort_order') or 0),
    }

    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        if service_id:
            cursor.execute(
                """
                UPDATE services
                SET name = %(name)s,
                    description = %(description)s,
                    price = %(price)s,
                    price_unit = %(price_unit)s,
                    duration_minutes = %(duration_minutes)s,
                    conditions = %(conditions)s,
                    image_url = %(image_url)s,
                    is_active = %(is_active)s,
                    sort_order = %(sort_order)s,
                    updated_at = NOW()
                WHERE id = %(service_id)s
                """,
                {**payload, 'service_id': service_id},
            )
        else:
            cursor.execute(
                """
                INSERT INTO services (
                    name, description, price, price_unit, duration_minutes, conditions,
                    image_url, is_active, sort_order, created_at, updated_at
                )
                VALUES (
                    %(name)s, %(description)s, %(price)s, %(price_unit)s,
                    %(duration_minutes)s, %(conditions)s, %(image_url)s,
                    %(is_active)s, %(sort_order)s, NOW(), NOW()
                )
                """,
                payload,
            )
            service_id = cursor.lastrowid
        connection.commit()
    return get_service(service_id, include_photos=True)


def set_service_active(service_id, is_active):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE services SET is_active = %s, updated_at = NOW() WHERE id = %s",
            (is_active, service_id),
        )
        connection.commit()
        return cursor.rowcount > 0


def delete_service(service_id):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT id FROM bookings WHERE service_id = %s LIMIT 1', (service_id,))
        if cursor.fetchone():
            cursor.execute('UPDATE services SET is_active = FALSE, updated_at = NOW() WHERE id = %s', (service_id,))
            connection.commit()
            return 'deactivated'
        cursor.execute('DELETE FROM service_photos WHERE service_id = %s', (service_id,))
        cursor.execute('DELETE FROM services WHERE id = %s', (service_id,))
        connection.commit()
        return 'deleted' if cursor.rowcount else None


def add_service_photo(service_id, image_url, alt_text=None, sort_order=0):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT COUNT(*) AS count FROM service_photos WHERE service_id = %s', (service_id,))
        count = cursor.fetchone()['count']
        is_primary = count == 0
        cursor.execute(
            """
            INSERT INTO service_photos (service_id, image_url, alt_text, is_primary, sort_order, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (service_id, image_url, alt_text or None, is_primary, sort_order),
        )
        if is_primary:
            cursor.execute(
                'UPDATE services SET image_url = %s, updated_at = NOW() WHERE id = %s',
                (image_url, service_id),
            )
        connection.commit()


def set_service_primary_photo(service_id, photo_id):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            'SELECT image_url FROM service_photos WHERE id = %s AND service_id = %s',
            (photo_id, service_id),
        )
        photo = cursor.fetchone()
        if not photo:
            connection.rollback()
            return False
        cursor.execute('UPDATE service_photos SET is_primary = FALSE WHERE service_id = %s', (service_id,))
        cursor.execute(
            'UPDATE service_photos SET is_primary = TRUE WHERE id = %s AND service_id = %s',
            (photo_id, service_id),
        )
        cursor.execute(
            'UPDATE services SET image_url = %s, updated_at = NOW() WHERE id = %s',
            (photo['image_url'], service_id),
        )
        connection.commit()
        return True


def delete_service_photo(service_id, photo_id):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT * FROM service_photos WHERE id = %s AND service_id = %s', (photo_id, service_id))
        photo = cursor.fetchone()
        if not photo:
            return None
        cursor.execute('DELETE FROM service_photos WHERE id = %s AND service_id = %s', (photo_id, service_id))
        if photo.get('is_primary'):
            cursor.execute(
                """
                SELECT id, image_url
                FROM service_photos
                WHERE service_id = %s
                ORDER BY sort_order, id
                LIMIT 1
                """,
                (service_id,),
            )
            next_photo = cursor.fetchone()
            if next_photo:
                cursor.execute('UPDATE service_photos SET is_primary = TRUE WHERE id = %s', (next_photo['id'],))
                cursor.execute(
                    'UPDATE services SET image_url = %s, updated_at = NOW() WHERE id = %s',
                    (next_photo['image_url'], service_id),
                )
            else:
                cursor.execute('UPDATE services SET image_url = NULL, updated_at = NOW() WHERE id = %s', (service_id,))
        connection.commit()
        return serialize_service_photo(photo)


def update_service_photo_order(service_id, photo_orders):
    with get_connection() as connection:
        cursor = connection.cursor()
        for photo_id, sort_order in photo_orders:
            cursor.execute(
                'UPDATE service_photos SET sort_order = %s WHERE id = %s AND service_id = %s',
                (sort_order, photo_id, service_id),
            )
        connection.commit()


def get_client_room_bookings_by_telegram(telegram_user_id):
    if not telegram_user_id:
        return []
    rows = fetch_all(
        """
        SELECT rb.*, r.name AS room_name, r.price
        FROM room_bookings rb
        JOIN rooms r ON r.id = rb.room_id
        WHERE rb.telegram_user_id = %s
        ORDER BY rb.check_in DESC, rb.created_at DESC
        """,
        (telegram_user_id,),
    )
    return [serialize_room_booking(row) for row in rows]


def get_client_room_bookings(client_id):
    if not client_id:
        return []
    rows = fetch_all(
        """
        SELECT rb.*, r.name AS room_name, r.price
        FROM clients c
        JOIN room_bookings rb
          ON (rb.client_id = c.id OR (rb.client_id IS NULL AND rb.telegram_user_id = c.telegram_user_id))
        JOIN rooms r ON r.id = rb.room_id
        WHERE c.id = %s
        GROUP BY rb.id
        ORDER BY rb.check_in DESC, rb.created_at DESC
        """,
        (client_id,),
    )
    return [serialize_room_booking(row) for row in rows]


def get_client_bookings(client_id):
    bookings = fetch_all(
        """
        SELECT b.*, s.name AS service_name
        FROM bookings b
        JOIN services s ON s.id = b.service_id
        WHERE b.client_id = %s
        ORDER BY b.booking_date DESC, b.booking_time DESC
        """,
        (client_id,),
    )
    return [serialize_booking(booking) for booking in bookings]


def get_availability(service_id, start_date=None, days=7):
    service = fetch_one(
        "SELECT id FROM services WHERE id = %s AND is_active = 1",
        (service_id,),
    )
    if not service:
        return None

    today = date.today()
    if start_date:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        if start < today:
            start = today
    else:
        start = today

    end = start + timedelta(days=max(1, min(days, 14)) - 1)
    booked = fetch_all(
        """
        SELECT booking_date, booking_time
        FROM bookings
        WHERE service_id = %s
          AND booking_date BETWEEN %s AND %s
          AND status IN ('pending', 'confirmed')
        """,
        (service_id, start, end),
    )
    blocked = {
        (item['booking_date'].isoformat(), normalize_time(item['booking_time']))
        for item in booked
    }

    availability = []
    for offset in range((end - start).days + 1):
        current = start + timedelta(days=offset)
        slots = [
            slot for slot in DEFAULT_SLOTS
            if (current.isoformat(), slot) not in blocked
        ]
        availability.append({'date': current.isoformat(), 'slots': slots})

    return availability


def create_booking(client_id, service_id, booking_date, booking_time, comment=None):
    if not client_id:
        raise ValueError('Client is required')
    if not service_id:
        raise ValueError('Service is required')
    if booking_time not in DEFAULT_SLOTS:
        raise ValueError('Selected time is not available')

    parsed_date = datetime.strptime(booking_date, '%Y-%m-%d').date()
    if parsed_date < date.today():
        raise ValueError('Booking date cannot be in the past')

    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id FROM clients WHERE id = %s", (client_id,))
        if not cursor.fetchone():
            raise LookupError('Client not found')

        cursor.execute(
            "SELECT id FROM services WHERE id = %s AND is_active = 1",
            (service_id,),
        )
        if not cursor.fetchone():
            raise LookupError('Service not found')

        cursor.execute(
            """
            SELECT id
            FROM bookings
            WHERE service_id = %s
              AND booking_date = %s
              AND booking_time = %s
              AND status IN ('pending', 'confirmed')
            FOR UPDATE
            """,
            (service_id, parsed_date, booking_time),
        )
        if cursor.fetchone():
            raise IntegrityError('Selected slot is already booked')

        cursor.execute(
            """
            INSERT INTO bookings (
                client_id, service_id, booking_date, booking_time,
                status, comment, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, 'pending', %s, NOW(), NOW())
            """,
            (client_id, service_id, parsed_date, booking_time, comment),
        )
        booking_id = cursor.lastrowid
        cursor.execute(
            """
            SELECT b.*, s.name AS service_name
            FROM bookings b
            JOIN services s ON s.id = b.service_id
            WHERE b.id = %s
            """,
            (booking_id,),
        )
        booking = cursor.fetchone()
        connection.commit()
        return serialize_booking(booking)


def cancel_booking(client_id, booking_id):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            UPDATE bookings
            SET status = 'cancelled', updated_at = NOW()
            WHERE id = %s AND client_id = %s AND status IN ('pending', 'confirmed')
            """,
            (booking_id, client_id),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            return None
        cursor.execute(
            """
            SELECT b.*, s.name AS service_name
            FROM bookings b
            JOIN services s ON s.id = b.service_id
            WHERE b.id = %s AND b.client_id = %s
            """,
            (booking_id, client_id),
        )
        booking = cursor.fetchone()
        connection.commit()
        return serialize_booking(booking)


def get_admin_by_username(username):
    return fetch_one(
        """
        SELECT *
        FROM admins
        WHERE username = %s AND is_active = 1
        """,
        (username,),
    )


def get_admin_by_id(admin_id):
    return fetch_one(
        """
        SELECT id, username, name, role, is_active, created_at, updated_at, last_login_at
        FROM admins
        WHERE id = %s AND is_active = 1
        """,
        (admin_id,),
    )


def create_admin_user(username, password_hash, name='Administrator', role='admin'):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            INSERT INTO admins (username, password_hash, name, role, is_active, created_at, updated_at)
            VALUES (%s, %s, %s, %s, TRUE, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                password_hash = VALUES(password_hash),
                name = VALUES(name),
                role = VALUES(role),
                is_active = TRUE,
                updated_at = NOW()
            """,
            (username, password_hash, name, role),
        )
        connection.commit()


def mark_admin_login(admin_id):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE admins SET last_login_at = NOW(), updated_at = NOW() WHERE id = %s",
            (admin_id,),
        )
        connection.commit()


def get_dashboard_summary():
    row = fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM bookings WHERE booking_date = CURDATE()) AS today_bookings,
            (SELECT COUNT(*) FROM bookings WHERE booking_date >= CURDATE() AND status IN ('pending', 'confirmed')) AS upcoming_bookings,
            (SELECT COUNT(*) FROM clients) AS clients_count,
            (SELECT COUNT(*) FROM menu_items WHERE is_active = 1) AS menu_items_count,
            (SELECT COUNT(*) FROM bookings WHERE status = 'pending') AS pending_bookings
        """
    )
    return {
        'today_bookings': row['today_bookings'],
        'upcoming_bookings': row['upcoming_bookings'],
        'clients_count': row['clients_count'],
        'menu_items_count': row['menu_items_count'],
        'pending_bookings': row['pending_bookings'],
    }


def booking_base_query(where_clause='1=1'):
    return f"""
        SELECT b.*, s.name AS service_name,
               c.telegram_user_id, c.username, c.first_name, c.last_name, c.phone, c.email
        FROM bookings b
        JOIN services s ON s.id = b.service_id
        JOIN clients c ON c.id = b.client_id
        WHERE {where_clause}
    """


def get_admin_bookings(period='upcoming', status=None, date_value=None, search=None, limit=200):
    clauses = []
    params = []

    if period == 'today':
        clauses.append('b.booking_date = CURDATE()')
    elif period == 'upcoming':
        clauses.append('b.booking_date >= CURDATE()')
    elif period == 'past':
        clauses.append('b.booking_date < CURDATE()')

    if status:
        clauses.append('b.status = %s')
        params.append(status)

    if date_value:
        parsed_date = datetime.strptime(date_value, '%Y-%m-%d').date()
        clauses.append('b.booking_date = %s')
        params.append(parsed_date)

    if search:
        like = f"%{search}%"
        clauses.append(
            """
            (
                c.first_name LIKE %s OR c.last_name LIKE %s OR c.username LIKE %s OR
                c.phone LIKE %s OR c.email LIKE %s OR s.name LIKE %s OR b.comment LIKE %s
            )
            """
        )
        params.extend([like, like, like, like, like, like, like])

    where_clause = ' AND '.join(clauses) if clauses else '1=1'
    query = booking_base_query(where_clause) + """
        ORDER BY b.booking_date ASC, b.booking_time ASC, b.created_at DESC
        LIMIT %s
    """
    params.append(limit)
    rows = fetch_all(query, tuple(params))
    return [serialize_admin_booking(row) for row in rows]


def get_recent_bookings(limit=8):
    rows = fetch_all(
        booking_base_query('1=1') + """
        ORDER BY b.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [serialize_admin_booking(row) for row in rows]


def get_admin_booking(booking_id):
    row = fetch_one(
        booking_base_query('b.id = %s'),
        (booking_id,),
    )
    return serialize_admin_booking(row) if row else None


def update_booking_status(booking_id, status):
    if status not in BOOKING_STATUSES:
        raise ValueError('Invalid booking status')

    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "UPDATE bookings SET status = %s, updated_at = NOW() WHERE id = %s",
            (status, booking_id),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            return None
        cursor.execute(booking_base_query('b.id = %s'), (booking_id,))
        booking = cursor.fetchone()
        connection.commit()
        return serialize_admin_booking(booking)


def get_booking_notification_payload(booking_id):
    return get_admin_booking(booking_id)


def get_menu_categories(include_inactive=False):
    where = '1=1' if include_inactive else 'c.is_active = 1'
    rows = fetch_all(
        f"""
        SELECT c.*, COUNT(mi.id) AS items_count
        FROM menu_categories c
        LEFT JOIN menu_items mi ON mi.category_id = c.id AND mi.is_active = 1
        WHERE {where}
        GROUP BY c.id
        ORDER BY c.sort_order, c.name
        """
    )
    return [serialize_menu_category(row) for row in rows]


def get_menu_category(category_id):
    row = fetch_one(
        """
        SELECT c.*, COUNT(mi.id) AS items_count
        FROM menu_categories c
        LEFT JOIN menu_items mi ON mi.category_id = c.id AND mi.is_active = 1
        WHERE c.id = %s
        GROUP BY c.id
        """,
        (category_id,),
    )
    return serialize_menu_category(row) if row else None


def save_menu_category(name, sort_order=0, is_active=True, category_id=None):
    if not name:
        raise ValueError('Category name is required')

    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        if category_id:
            cursor.execute(
                """
                UPDATE menu_categories
                SET name = %s, sort_order = %s, is_active = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (name, sort_order, is_active, category_id),
            )
        else:
            cursor.execute(
                """
                INSERT INTO menu_categories (name, sort_order, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                """,
                (name, sort_order, is_active),
            )
            category_id = cursor.lastrowid
        connection.commit()
        return get_menu_category(category_id)


def set_menu_category_active(category_id, is_active):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE menu_categories SET is_active = %s, updated_at = NOW() WHERE id = %s",
            (is_active, category_id),
        )
        connection.commit()
        return cursor.rowcount > 0


def get_menu_items(category_id=None, search=None, availability=None, include_inactive=False):
    clauses = []
    params = []

    if not include_inactive:
        clauses.append('mi.is_active = 1')

    if category_id:
        clauses.append('mi.category_id = %s')
        params.append(category_id)

    if availability == 'available':
        clauses.append('mi.is_available = 1')
    elif availability == 'unavailable':
        clauses.append('mi.is_available = 0')

    if search:
        like = f"%{search}%"
        clauses.append('(mi.name LIKE %s OR mi.description LIKE %s OR c.name LIKE %s)')
        params.extend([like, like, like])

    where_clause = ' AND '.join(clauses) if clauses else '1=1'
    rows = fetch_all(
        f"""
        SELECT mi.*, c.name AS category_name
        FROM menu_items mi
        JOIN menu_categories c ON c.id = mi.category_id
        WHERE {where_clause}
        ORDER BY c.sort_order, mi.sort_order, mi.name
        """,
        tuple(params),
    )
    return [serialize_menu_item(row) for row in rows]


def get_public_menu():
    categories = get_menu_categories(include_inactive=False)
    items = get_menu_items(include_inactive=False, availability='available')
    grouped = []
    for category in categories:
        category_items = [
            item for item in items
            if item['category_id'] == category['id'] and item['is_active'] and item['is_available']
        ]
        if category_items:
            grouped.append({**category, 'items': category_items})
    return grouped


def get_menu_item(item_id):
    row = fetch_one(
        """
        SELECT mi.*, c.name AS category_name
        FROM menu_items mi
        JOIN menu_categories c ON c.id = mi.category_id
        WHERE mi.id = %s
        """,
        (item_id,),
    )
    return serialize_menu_item(row) if row else None


def save_menu_item(data, item_id=None):
    name = (data.get('name') or '').strip()
    if not name:
        raise ValueError('Dish name is required')

    category_id = data.get('category_id')
    if not category_id:
        raise ValueError('Category is required')

    price = data.get('price')
    if price in (None, ''):
        raise ValueError('Price is required')

    payload = {
        'category_id': int(category_id),
        'name': name,
        'description': (data.get('description') or '').strip() or None,
        'price': price,
        'image_url': (data.get('image_url') or '').strip() or None,
        'is_available': bool(data.get('is_available')),
        'is_active': bool(data.get('is_active')),
        'sort_order': int(data.get('sort_order') or 0),
    }

    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT id FROM menu_categories WHERE id = %s",
            (payload['category_id'],),
        )
        if not cursor.fetchone():
            raise LookupError('Category not found')

        if item_id:
            cursor.execute(
                """
                UPDATE menu_items
                SET category_id = %(category_id)s,
                    name = %(name)s,
                    description = %(description)s,
                    price = %(price)s,
                    image_url = %(image_url)s,
                    is_available = %(is_available)s,
                    is_active = %(is_active)s,
                    sort_order = %(sort_order)s,
                    updated_at = NOW()
                WHERE id = %(item_id)s
                """,
                {**payload, 'item_id': item_id},
            )
        else:
            cursor.execute(
                """
                INSERT INTO menu_items (
                    category_id, name, description, price, image_url,
                    is_available, is_active, sort_order, created_at, updated_at
                )
                VALUES (
                    %(category_id)s, %(name)s, %(description)s, %(price)s, %(image_url)s,
                    %(is_available)s, %(is_active)s, %(sort_order)s, NOW(), NOW()
                )
                """,
                payload,
            )
            item_id = cursor.lastrowid

        connection.commit()
        return get_menu_item(item_id)


def set_menu_item_active(item_id, is_active):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE menu_items SET is_active = %s, updated_at = NOW() WHERE id = %s",
            (is_active, item_id),
        )
        connection.commit()
        return cursor.rowcount > 0


def split_text_list(value):
    if not value:
        return []
    return [item.strip() for item in value.replace('\r', '').split('\n') if item.strip()]


def serialize_room_photo(photo):
    return {
        'id': photo['id'],
        'room_id': photo['room_id'],
        'image_url': photo['image_url'],
        'alt_text': photo.get('alt_text'),
        'is_primary': bool(photo.get('is_primary')),
        'sort_order': photo.get('sort_order') or 0,
        'created_at': serialize_datetime(photo.get('created_at')),
    }


def get_room_photos(room_id):
    rows = fetch_all(
        """
        SELECT *
        FROM room_photos
        WHERE room_id = %s
        ORDER BY is_primary DESC, sort_order, id
        """,
        (room_id,),
    )
    return [serialize_room_photo(row) for row in rows]


def serialize_room(room, include_photos=False):
    if not room:
        return None
    photo_url = room.get('primary_photo_url') or room.get('image_url') or '/static/img/vodogray.png'
    data = {
        'id': room['id'],
        'name': room['name'],
        'category': room.get('category'),
        'description': room.get('description'),
        'price': float(room['price']) if room.get('price') is not None else None,
        'guests_count': room.get('guests_count'),
        'area': room.get('area'),
        'sleeping_places': room.get('sleeping_places'),
        'tags': room.get('tags') or '',
        'amenities': room.get('amenities') or '',
        'tags_list': split_text_list(room.get('tags')),
        'amenities_list': split_text_list(room.get('amenities')),
        'is_active': bool(room.get('is_active')),
        'sort_order': room.get('sort_order') or 0,
        'primary_photo_url': photo_url,
        'created_at': serialize_datetime(room.get('created_at')),
        'updated_at': serialize_datetime(room.get('updated_at')),
    }
    if include_photos:
        data['photos'] = get_room_photos(room['id'])
    return data


def room_base_query(where_clause='1=1'):
    return f"""
        SELECT r.*,
               (
                   SELECT rp.image_url
                   FROM room_photos rp
                   WHERE rp.room_id = r.id
                   ORDER BY rp.is_primary DESC, rp.sort_order, rp.id
                   LIMIT 1
               ) AS primary_photo_url
        FROM rooms r
        WHERE {where_clause}
    """


def room_has_overlap(room_id, check_in, check_out, exclude_booking_id=None):
    check_in = parse_booking_date(check_in, 'Дата заїзду')
    check_out = parse_booking_date(check_out, 'Дата виїзду')
    if check_out <= check_in:
        raise ValueError('Дата виїзду повинна бути пізніше дати заїзду')
    params = [room_id, check_in, check_out]
    clause = ''
    if exclude_booking_id:
        clause = 'AND id <> %s'
        params.append(exclude_booking_id)
    row = fetch_one(
        f"""
        SELECT id
        FROM room_bookings
        WHERE room_id = %s
          AND status IN ('pending', 'confirmed')
          AND check_in < %s
          AND check_out > %s
          {clause}
        LIMIT 1
        """,
        tuple(params),
    )
    return bool(row)


def get_admin_rooms(search=None, include_inactive=True):
    clauses = []
    params = []
    if not include_inactive:
        clauses.append('r.is_active = 1')
    if search:
        like = f"%{search}%"
        clauses.append('(r.name LIKE %s OR r.category LIKE %s OR r.description LIKE %s)')
        params.extend([like, like, like])
    where_clause = ' AND '.join(clauses) if clauses else '1=1'
    rows = fetch_all(
        room_base_query(where_clause) + """
        ORDER BY r.sort_order, r.name
        """,
        tuple(params),
    )
    return [serialize_room(row) for row in rows]


def get_public_rooms(check_in=None, check_out=None):
    if check_in or check_out:
        if not check_in or not check_out:
            raise ValueError('Оберіть дату заїзду та виїзду')
        check_in = parse_booking_date(check_in, 'Дата заїзду')
        check_out = parse_booking_date(check_out, 'Дата виїзду')
        if check_out <= check_in:
            raise ValueError('Дата виїзду повинна бути пізніше дати заїзду')
        rows = fetch_all(
            room_base_query(
                """
                r.is_active = 1
                AND NOT EXISTS (
                    SELECT 1
                    FROM room_bookings rb
                    WHERE rb.room_id = r.id
                      AND rb.status IN ('pending', 'confirmed')
                      AND rb.check_in < %s
                      AND rb.check_out > %s
                )
                """
            ) + """
            ORDER BY r.sort_order, r.name
            """,
            (check_out, check_in),
        )
        return [serialize_room(row) for row in rows]
    return get_admin_rooms(include_inactive=False)


def get_room(room_id, include_photos=False):
    row = fetch_one(room_base_query('r.id = %s'), (room_id,))
    return serialize_room(row, include_photos=include_photos) if row else None


def save_room(data, room_id=None):
    name = (data.get('name') or '').strip()
    if not name:
        raise ValueError('Назва номера обовʼязкова')
    price = data.get('price')
    if price in (None, ''):
        raise ValueError('Вкажіть ціну номера')

    payload = {
        'name': name,
        'category': (data.get('category') or '').strip() or None,
        'description': (data.get('description') or '').strip() or None,
        'price': price,
        'guests_count': int(data.get('guests_count') or 1),
        'area': (data.get('area') or '').strip() or None,
        'sleeping_places': (data.get('sleeping_places') or '').strip() or None,
        'tags': (data.get('tags') or '').strip() or None,
        'amenities': (data.get('amenities') or '').strip() or None,
        'is_active': bool(data.get('is_active')),
        'sort_order': int(data.get('sort_order') or 0),
    }

    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        if room_id:
            payload['id'] = room_id
            cursor.execute(
                """
                UPDATE rooms
                SET name = %(name)s,
                    category = %(category)s,
                    description = %(description)s,
                    price = %(price)s,
                    guests_count = %(guests_count)s,
                    area = %(area)s,
                    sleeping_places = %(sleeping_places)s,
                    tags = %(tags)s,
                    amenities = %(amenities)s,
                    is_active = %(is_active)s,
                    sort_order = %(sort_order)s,
                    updated_at = NOW()
                WHERE id = %(id)s
                """,
                payload,
            )
        else:
            cursor.execute(
                """
                INSERT INTO rooms (
                    name, category, description, price, guests_count, area,
                    sleeping_places, tags, amenities, is_active, sort_order,
                    created_at, updated_at
                )
                VALUES (
                    %(name)s, %(category)s, %(description)s, %(price)s, %(guests_count)s,
                    %(area)s, %(sleeping_places)s, %(tags)s, %(amenities)s,
                    %(is_active)s, %(sort_order)s, NOW(), NOW()
                )
                """,
                payload,
            )
            room_id = cursor.lastrowid
        connection.commit()
    return get_room(room_id, include_photos=True)


def add_room_photo(room_id, image_url, alt_text='', sort_order=0):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT COUNT(*) AS count FROM room_photos WHERE room_id = %s', (room_id,))
        count = cursor.fetchone()['count']
        cursor.execute(
            """
            INSERT INTO room_photos (room_id, image_url, alt_text, is_primary, sort_order, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (room_id, image_url, alt_text or None, count == 0, sort_order),
        )
        connection.commit()


def set_room_primary_photo(room_id, photo_id):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute('UPDATE room_photos SET is_primary = FALSE WHERE room_id = %s', (room_id,))
        cursor.execute(
            'UPDATE room_photos SET is_primary = TRUE WHERE id = %s AND room_id = %s',
            (photo_id, room_id),
        )
        connection.commit()
        return cursor.rowcount > 0


def delete_room_photo(room_id, photo_id):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT * FROM room_photos WHERE id = %s AND room_id = %s', (photo_id, room_id))
        photo = cursor.fetchone()
        if not photo:
            return None
        cursor.execute('DELETE FROM room_photos WHERE id = %s AND room_id = %s', (photo_id, room_id))
        if photo.get('is_primary'):
            cursor.execute(
                """
                UPDATE room_photos
                SET is_primary = TRUE
                WHERE room_id = %s
                ORDER BY sort_order, id
                LIMIT 1
                """,
                (room_id,),
            )
        connection.commit()
        return serialize_room_photo(photo)


def update_room_photo_order(room_id, photo_orders):
    with get_connection() as connection:
        cursor = connection.cursor()
        for photo_id, sort_order in photo_orders:
            cursor.execute(
                'UPDATE room_photos SET sort_order = %s WHERE id = %s AND room_id = %s',
                (sort_order, photo_id, room_id),
            )
        connection.commit()


def delete_room(room_id):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT id FROM room_bookings WHERE room_id = %s LIMIT 1', (room_id,))
        if cursor.fetchone():
            cursor.execute('UPDATE rooms SET is_active = FALSE, updated_at = NOW() WHERE id = %s', (room_id,))
            connection.commit()
            return 'deactivated'
        cursor.execute('DELETE FROM room_photos WHERE room_id = %s', (room_id,))
        cursor.execute('DELETE FROM rooms WHERE id = %s', (room_id,))
        connection.commit()
        return 'deleted' if cursor.rowcount else None


def serialize_room_booking(booking):
    check_in_time = booking.get('check_in_time')
    check_out_time = booking.get('check_out_time')
    telegram_user_id = booking.get('telegram_user_id')
    room = {
        'id': booking['id'],
        'room_id': booking['room_id'],
        'client_id': booking.get('client_id'),
        'room_name': booking.get('room_name'),
        'guest_name': booking.get('guest_name'),
        'guest_phone': booking.get('guest_phone'),
        'guest_email': booking.get('guest_email'),
        'check_in': booking['check_in'].isoformat(),
        'check_out': booking['check_out'].isoformat(),
        'check_in_time': normalize_time(check_in_time) if check_in_time else None,
        'check_out_time': normalize_time(check_out_time) if check_out_time else None,
        'status': booking['status'],
        'status_label': STATUS_LABELS.get(booking['status'], booking['status']),
        'comment': booking.get('comment'),
        'telegram_user_id': telegram_user_id,
        'telegram_link_token': booking.get('telegram_link_token'),
        'telegram_linked': bool(telegram_user_id),
        'client_notified_status': booking.get('client_notified_status'),
        'admin_notified_at': serialize_datetime(booking.get('admin_notified_at')),
        'created_at': serialize_datetime(booking.get('created_at')),
        'updated_at': serialize_datetime(booking.get('updated_at')),
    }
    if booking.get('price') is not None:
        room['room_price'] = float(booking['price'])
    return room


def get_room_bookings(status=None, room_id=None):
    clauses = []
    params = []
    if status:
        clauses.append('rb.status = %s')
        params.append(status)
    if room_id:
        clauses.append('rb.room_id = %s')
        params.append(room_id)
    where_clause = ' AND '.join(clauses) if clauses else '1=1'
    rows = fetch_all(
        f"""
        SELECT rb.*, r.name AS room_name, r.price
        FROM room_bookings rb
        JOIN rooms r ON r.id = rb.room_id
        WHERE {where_clause}
        ORDER BY rb.check_in DESC, rb.created_at DESC
        """,
        tuple(params),
    )
    return [serialize_room_booking(row) for row in rows]


def get_room_booking(booking_id):
    row = fetch_one(
        """
        SELECT rb.*, r.name AS room_name, r.price
        FROM room_bookings rb
        JOIN rooms r ON r.id = rb.room_id
        WHERE rb.id = %s
        """,
        (booking_id,),
    )
    return serialize_room_booking(row) if row else None


def save_room_booking(data, booking_id=None):
    room_id = data.get('room_id')
    if not room_id:
        raise ValueError('Оберіть номер')
    check_in = parse_booking_date(data.get('check_in'), 'Дата заїзду')
    check_out = parse_booking_date(data.get('check_out'), 'Дата виїзду')
    if check_out <= check_in:
        raise ValueError('Дата виїзду повинна бути пізніше дати заїзду')
    status = data.get('status') or 'confirmed'
    if status not in BOOKING_STATUSES:
        raise ValueError('Некоректний статус бронювання')

    payload = {
        'room_id': int(room_id),
        'guest_name': (data.get('guest_name') or '').strip() or None,
        'guest_phone': (data.get('guest_phone') or '').strip() or None,
        'guest_email': (data.get('guest_email') or '').strip() or None,
        'check_in': check_in,
        'check_out': check_out,
        'check_in_time': data.get('check_in_time') or None,
        'check_out_time': data.get('check_out_time') or None,
        'status': status,
        'comment': (data.get('comment') or '').strip() or None,
    }
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT id FROM rooms WHERE id = %s FOR UPDATE', (payload['room_id'],))
        if not cursor.fetchone():
            raise LookupError('Номер не знайдено')
        if status in ROOM_BLOCKING_STATUSES:
            overlap_params = {
                **payload,
                'id': booking_id or 0,
            }
            cursor.execute(
                """
                SELECT id
                FROM room_bookings
                WHERE room_id = %(room_id)s
                  AND id <> %(id)s
                  AND status IN ('pending', 'confirmed')
                  AND check_in < %(check_out)s
                  AND check_out > %(check_in)s
                LIMIT 1
                FOR UPDATE
                """,
                overlap_params,
            )
            if cursor.fetchone():
                raise IntegrityError('Номер вже зайнятий на вибрані дати')
        if booking_id:
            payload['id'] = booking_id
            cursor.execute(
                """
                UPDATE room_bookings
                SET room_id = %(room_id)s,
                    guest_name = %(guest_name)s,
                    guest_phone = %(guest_phone)s,
                    guest_email = %(guest_email)s,
                    check_in = %(check_in)s,
                    check_out = %(check_out)s,
                    check_in_time = %(check_in_time)s,
                    check_out_time = %(check_out_time)s,
                    status = %(status)s,
                    comment = %(comment)s,
                    updated_at = NOW()
                WHERE id = %(id)s
                """,
                payload,
            )
        else:
            cursor.execute(
                """
                INSERT INTO room_bookings (
                    room_id, guest_name, guest_phone, guest_email,
                    check_in, check_out, check_in_time, check_out_time,
                    status, comment, created_at, updated_at
                )
                VALUES (
                    %(room_id)s, %(guest_name)s, %(guest_phone)s, %(guest_email)s,
                    %(check_in)s, %(check_out)s, %(check_in_time)s, %(check_out_time)s,
                    %(status)s, %(comment)s, NOW(), NOW()
                )
                """,
                payload,
            )
            booking_id = cursor.lastrowid
        connection.commit()
    return get_room_booking(booking_id)


def create_public_room_booking(data, link_token):
    room_id = data.get('room_id')
    if not room_id:
        raise ValueError('Оберіть номер')
    check_in = parse_booking_date(data.get('check_in'), 'Дата заїзду')
    check_out = parse_booking_date(data.get('check_out'), 'Дата виїзду')
    if check_out <= check_in:
        raise ValueError('Дата виїзду повинна бути пізніше дати заїзду')

    payload = {
        'room_id': int(room_id),
        'guest_name': (data.get('guest_name') or '').strip(),
        'guest_phone': (data.get('guest_phone') or '').strip(),
        'guest_email': (data.get('guest_email') or '').strip() or None,
        'check_in': check_in,
        'check_out': check_out,
        'check_in_time': data.get('check_in_time') or None,
        'check_out_time': data.get('check_out_time') or None,
        'comment': (data.get('comment') or '').strip() or None,
        'telegram_link_token': link_token,
        'telegram_user_id': data.get('telegram_user_id'),
        'client_id': None,
    }
    if not payload['guest_name']:
        raise ValueError('Вкажіть імʼя та прізвище')
    if not payload['guest_phone']:
        raise ValueError('Вкажіть номер телефону')

    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        if payload['telegram_user_id']:
            cursor.execute(
                """
                SELECT id
                FROM clients
                WHERE telegram_user_id = %s
                LIMIT 1
                """,
                (payload['telegram_user_id'],),
            )
            client = cursor.fetchone()
            if client:
                payload['client_id'] = client['id']
        cursor.execute('SELECT id FROM rooms WHERE id = %s AND is_active = TRUE FOR UPDATE', (payload['room_id'],))
        if not cursor.fetchone():
            raise LookupError('Номер не знайдено або він недоступний')
        cursor.execute(
            """
            SELECT id
            FROM room_bookings
            WHERE room_id = %(room_id)s
              AND status IN ('pending', 'confirmed')
              AND check_in < %(check_out)s
              AND check_out > %(check_in)s
            LIMIT 1
            """,
            payload,
        )
        if cursor.fetchone():
            raise IntegrityError('Номер вже зайнятий на вибрані дати')
        cursor.execute(
            """
            INSERT INTO room_bookings (
                room_id, guest_name, guest_phone, guest_email,
                check_in, check_out, check_in_time, check_out_time,
                status, comment, client_id, telegram_user_id, telegram_link_token, telegram_link_expires_at,
                created_at, updated_at
            )
            VALUES (
                %(room_id)s, %(guest_name)s, %(guest_phone)s, %(guest_email)s,
                %(check_in)s, %(check_out)s, %(check_in_time)s, %(check_out_time)s,
                'pending', %(comment)s, %(client_id)s, %(telegram_user_id)s, %(telegram_link_token)s, DATE_ADD(NOW(), INTERVAL 14 DAY),
                NOW(), NOW()
            )
            """,
            payload,
        )
        booking_id = cursor.lastrowid
        connection.commit()
    return get_room_booking(booking_id)


def update_room_booking_status(booking_id, status):
    if status not in BOOKING_STATUSES:
        raise ValueError('Некоректний статус бронювання')
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT *
            FROM room_bookings
            WHERE id = %s
            FOR UPDATE
            """,
            (booking_id,),
        )
        booking = cursor.fetchone()
        if not booking:
            connection.rollback()
            return None, 'not_found'
        if booking['status'] == status:
            connection.rollback()
            return get_room_booking(booking_id), 'unchanged'
        if status == 'confirmed':
            cursor.execute(
                """
                SELECT id
                FROM room_bookings
                WHERE id <> %s
                  AND room_id = %s
                  AND status IN ('pending', 'confirmed')
                  AND check_in < %s
                  AND check_out > %s
                LIMIT 1
                """,
                (booking_id, booking['room_id'], booking['check_out'], booking['check_in']),
            )
            if cursor.fetchone():
                connection.rollback()
                raise IntegrityError('Номер вже зайнятий на вибрані дати')
        cursor.execute(
            """
            UPDATE room_bookings
            SET status = %s,
                client_notified_status = CASE WHEN client_notified_status = %s THEN NULL ELSE client_notified_status END,
                updated_at = NOW()
            WHERE id = %s
            """,
            (status, status, booking_id),
        )
        connection.commit()
    return get_room_booking(booking_id), 'changed'


def mark_room_booking_client_notified(booking_id, status):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE room_bookings
            SET client_notified_status = %s, client_notified_at = NOW()
            WHERE id = %s
            """,
            (status, booking_id),
        )
        connection.commit()


def mark_room_booking_admin_notified(booking_id):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute('UPDATE room_bookings SET admin_notified_at = NOW() WHERE id = %s', (booking_id,))
        connection.commit()


def link_room_booking_to_telegram(link_token, telegram_user_id):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id
            FROM clients
            WHERE telegram_user_id = %s
            LIMIT 1
            """,
            (telegram_user_id,),
        )
        client = cursor.fetchone()
        cursor.execute(
            """
            SELECT id
            FROM room_bookings
            WHERE telegram_link_token = %s
              AND telegram_link_expires_at >= NOW()
            LIMIT 1
            FOR UPDATE
            """,
            (link_token,),
        )
        row = cursor.fetchone()
        if not row:
            connection.rollback()
            return None
        cursor.execute(
            """
            UPDATE room_bookings
            SET telegram_user_id = %s,
                client_id = %s,
                telegram_link_token = NULL,
                telegram_link_expires_at = NULL,
                updated_at = NOW()
            WHERE id = %s
            """,
            (telegram_user_id, client['id'] if client else None, row['id']),
        )
        connection.commit()
        return get_room_booking(row['id'])


def get_site_setting(key, default=None):
    row = fetch_one('SELECT setting_value FROM site_settings WHERE setting_key = %s', (key,))
    return row['setting_value'] if row else default


def set_site_setting(key, value):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO site_settings (setting_key, setting_value, updated_at)
            VALUES (%s, %s, NOW())
            ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value), updated_at = NOW()
            """,
            (key, value),
        )
        connection.commit()


def serialize_banner(row):
    return {
        'id': row['id'],
        'image_url': row['image_url'],
        'title': row.get('title'),
        'is_active': bool(row.get('is_active')),
        'sort_order': row.get('sort_order') or 0,
        'created_at': serialize_datetime(row.get('created_at')),
    }


def get_banners(include_inactive=False):
    where = '1=1' if include_inactive else 'is_active = TRUE'
    rows = fetch_all(
        f"""
        SELECT *
        FROM home_banners
        WHERE {where}
        ORDER BY sort_order, id
        """
    )
    return [serialize_banner(row) for row in rows]


def add_banner(image_url, title='', is_active=True, sort_order=0):
    sort_order = int(sort_order or 0)
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO home_banners (image_url, title, is_active, sort_order, created_at, updated_at)
            VALUES (%s, %s, %s, %s, NOW(), NOW())
            """,
            (image_url, title or None, is_active, sort_order),
        )
        connection.commit()


def update_banner(banner_id, title='', is_active=True, sort_order=0):
    sort_order = int(sort_order or 0)
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE home_banners
            SET title = %s, is_active = %s, sort_order = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (title or None, is_active, sort_order, banner_id),
        )
        connection.commit()
        return cursor.rowcount > 0


def delete_banner(banner_id):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT * FROM home_banners WHERE id = %s', (banner_id,))
        banner = cursor.fetchone()
        if not banner:
            return None
        cursor.execute('DELETE FROM home_banners WHERE id = %s', (banner_id,))
        connection.commit()
        return serialize_banner(banner)


def get_admin_clients(search=None, limit=200):
    params = []
    clauses = []
    if search:
        like = f"%{search}%"
        clauses.append(
            """
            (
                c.first_name LIKE %s OR c.last_name LIKE %s OR c.username LIKE %s OR
                c.phone LIKE %s OR c.email LIKE %s OR CAST(c.telegram_user_id AS CHAR) LIKE %s
            )
            """
        )
        params.extend([like, like, like, like, like, like])

    where_clause = ' AND '.join(clauses) if clauses else '1=1'
    params.append(limit)
    rows = fetch_all(
        f"""
        SELECT c.*,
               COUNT(DISTINCT b.id) AS service_bookings_count,
               COUNT(DISTINCT rb.id) AS room_bookings_count,
               (
                   COUNT(DISTINCT b.id) + COUNT(DISTINCT rb.id)
               ) AS bookings_count,
               COUNT(DISTINCT CASE WHEN b.booking_date >= CURDATE() AND b.status IN ('pending', 'confirmed') THEN b.id END)
               + COUNT(DISTINCT CASE WHEN rb.check_out >= CURDATE() AND rb.status IN ('pending', 'confirmed') THEN rb.id END) AS upcoming_count
        FROM clients c
        LEFT JOIN bookings b ON b.client_id = c.id
        LEFT JOIN room_bookings rb
          ON (rb.client_id = c.id OR (rb.client_id IS NULL AND rb.telegram_user_id = c.telegram_user_id))
        WHERE {where_clause}
        GROUP BY c.id
        ORDER BY c.last_seen DESC, c.created_at DESC
        LIMIT %s
        """,
        tuple(params),
    )
    return [
        {
            **serialize_client(row),
            'display_name': client_display_name(row),
            'created_at': serialize_datetime(row.get('created_at')),
            'updated_at': serialize_datetime(row.get('updated_at')),
            'bookings_count': row.get('bookings_count') or 0,
            'service_bookings_count': row.get('service_bookings_count') or 0,
            'room_bookings_count': row.get('room_bookings_count') or 0,
            'upcoming_count': row.get('upcoming_count') or 0,
        }
        for row in rows
    ]


def get_admin_client(client_id):
    row = fetch_one(
        "SELECT * FROM clients WHERE id = %s",
        (client_id,),
    )
    if not row:
        return None

    bookings = fetch_all(
        booking_base_query('b.client_id = %s') + """
        ORDER BY b.booking_date DESC, b.booking_time DESC
        """,
        (client_id,),
    )
    client = {
        **serialize_client(row),
        'display_name': client_display_name(row),
        'created_at': serialize_datetime(row.get('created_at')),
        'updated_at': serialize_datetime(row.get('updated_at')),
        'bookings': [serialize_admin_booking(booking) for booking in bookings],
        'room_bookings': get_client_room_bookings(client_id),
    }
    client['upcoming_bookings'] = [
        booking for booking in client['bookings']
        if booking['status'] in ('pending', 'confirmed')
        and booking['booking_date'] >= date.today().isoformat()
    ]
    client['upcoming_room_bookings'] = [
        booking for booking in client['room_bookings']
        if booking['status'] in ROOM_BLOCKING_STATUSES
        and booking['check_out'] >= date.today().isoformat()
    ]
    return client


def serialize_announcement(row):
    return {
        'id': row['id'],
        'title': row['title'],
        'body': row.get('body'),
        'media_url': row.get('media_url'),
        'media_type': row.get('media_type'),
        'status': row['status'],
        'sent_at': serialize_datetime(row.get('sent_at')),
        'created_at': serialize_datetime(row.get('created_at')),
        'updated_at': serialize_datetime(row.get('updated_at')),
        'recipients_count': row.get('recipients_count') or 0,
        'sent_count': row.get('sent_count') or 0,
        'failed_count': row.get('failed_count') or 0,
    }


def get_announcements():
    rows = fetch_all(
        """
        SELECT a.*,
               COUNT(ar.id) AS recipients_count,
               COUNT(CASE WHEN ar.status = 'sent' THEN 1 END) AS sent_count,
               COUNT(CASE WHEN ar.status = 'failed' THEN 1 END) AS failed_count
        FROM announcements a
        LEFT JOIN announcement_recipients ar ON ar.announcement_id = a.id
        GROUP BY a.id
        ORDER BY a.created_at DESC
        """
    )
    return [serialize_announcement(row) for row in rows]


def get_announcement(announcement_id, include_recipients=False):
    row = fetch_one(
        """
        SELECT a.*,
               COUNT(ar.id) AS recipients_count,
               COUNT(CASE WHEN ar.status = 'sent' THEN 1 END) AS sent_count,
               COUNT(CASE WHEN ar.status = 'failed' THEN 1 END) AS failed_count
        FROM announcements a
        LEFT JOIN announcement_recipients ar ON ar.announcement_id = a.id
        WHERE a.id = %s
        GROUP BY a.id
        """,
        (announcement_id,),
    )
    if not row:
        return None
    announcement = serialize_announcement(row)
    if include_recipients:
        announcement['recipients'] = fetch_all(
            """
            SELECT ar.*, c.telegram_user_id, c.username, c.first_name, c.last_name
            FROM announcement_recipients ar
            JOIN clients c ON c.id = ar.client_id
            WHERE ar.announcement_id = %s
            ORDER BY ar.id DESC
            """,
            (announcement_id,),
        )
    return announcement


def save_announcement(data, announcement_id=None, media_url=None, media_type=None):
    title = (data.get('title') or '').strip()
    body = (data.get('body') or '').strip()
    status = data.get('status') or 'draft'
    if not title:
        raise ValueError('Вкажіть заголовок оголошення')
    if not body:
        raise ValueError('Вкажіть текст оголошення')
    if status not in ANNOUNCEMENT_STATUSES:
        raise ValueError('Некоректний статус оголошення')
    current_status = None
    if announcement_id:
        current = fetch_one('SELECT status FROM announcements WHERE id = %s', (announcement_id,))
        current_status = current['status'] if current else None
    if status == 'sent' and current_status != 'sent':
        raise ValueError('Статус "надіслано" встановлюється тільки після фактичної розсилки')
    with get_connection() as connection:
        cursor = connection.cursor()
        payload = {
            'title': title,
            'body': body,
            'status': status,
            'media_url': media_url,
            'media_type': media_type,
            'id': announcement_id,
        }
        if announcement_id:
            media_sql = ''
            if media_url:
                media_sql = ', media_url = %(media_url)s, media_type = %(media_type)s'
            cursor.execute(
                f"""
                UPDATE announcements
                SET title = %(title)s,
                    body = %(body)s,
                    status = CASE WHEN status = 'sent' THEN status ELSE %(status)s END
                    {media_sql},
                    updated_at = NOW()
                WHERE id = %(id)s
                """,
                payload,
            )
        else:
            cursor.execute(
                """
                INSERT INTO announcements (title, body, media_url, media_type, status, created_at, updated_at)
                VALUES (%(title)s, %(body)s, %(media_url)s, %(media_type)s, %(status)s, NOW(), NOW())
                """,
                payload,
            )
            announcement_id = cursor.lastrowid
        connection.commit()
    return get_announcement(announcement_id, include_recipients=True)


def delete_announcement(announcement_id):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT status FROM announcements WHERE id = %s", (announcement_id,))
        row = cursor.fetchone()
        if not row:
            return False
        if row['status'] == 'sent':
            raise ValueError('Надіслане оголошення не можна видалити')
        cursor.execute('DELETE FROM announcement_recipients WHERE announcement_id = %s', (announcement_id,))
        cursor.execute('DELETE FROM announcements WHERE id = %s', (announcement_id,))
        connection.commit()
        return True


def count_announcement_recipients():
    row = fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM clients
        WHERE status = 'active' AND telegram_user_id IS NOT NULL
        """
    )
    return row['count'] if row else 0


def prepare_announcement_recipients(announcement_id, retry_failed=False):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute('SELECT * FROM announcements WHERE id = %s FOR UPDATE', (announcement_id,))
        announcement = cursor.fetchone()
        if not announcement:
            raise LookupError('Оголошення не знайдено')
        if announcement['status'] == 'draft':
            raise ValueError('Чернетки не можна надсилати')
        if announcement['status'] == 'sent' and not retry_failed:
            raise ValueError('Оголошення вже надіслано')
        if retry_failed:
            cursor.execute(
                """
                SELECT ar.id, ar.client_id, c.telegram_user_id
                FROM announcement_recipients ar
                JOIN clients c ON c.id = ar.client_id
                WHERE ar.announcement_id = %s AND ar.status = 'failed'
                """,
                (announcement_id,),
            )
            recipients = cursor.fetchall()
            cursor.execute(
                """
                UPDATE announcement_recipients
                SET status = 'pending', error_message = NULL, updated_at = NOW()
                WHERE announcement_id = %s AND status = 'failed'
                """,
                (announcement_id,),
            )
        else:
            cursor.execute(
                """
                INSERT IGNORE INTO announcement_recipients (announcement_id, client_id, status, created_at, updated_at)
                SELECT %s, id, 'pending', NOW(), NOW()
                FROM clients
                WHERE status = 'active' AND telegram_user_id IS NOT NULL
                """,
                (announcement_id,),
            )
            cursor.execute(
                """
                SELECT ar.id, ar.client_id, c.telegram_user_id
                FROM announcement_recipients ar
                JOIN clients c ON c.id = ar.client_id
                WHERE ar.announcement_id = %s AND ar.status = 'pending'
                """,
                (announcement_id,),
            )
            recipients = cursor.fetchall()
        connection.commit()
        return serialize_announcement(announcement), recipients


def mark_announcement_recipient_result(recipient_id, ok, error_message=None):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE announcement_recipients
            SET status = %s,
                error_message = %s,
                sent_at = CASE WHEN %s THEN NOW() ELSE sent_at END,
                updated_at = NOW()
            WHERE id = %s
            """,
            ('sent' if ok else 'failed', None if ok else (error_message or 'Telegram API error')[:500], ok, recipient_id),
        )
        connection.commit()


def finish_announcement_if_sent(announcement_id):
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) AS pending_count,
                COUNT(CASE WHEN status = 'sent' THEN 1 END) AS sent_count
            FROM announcement_recipients
            WHERE announcement_id = %s
            """,
            (announcement_id,),
        )
        stats = cursor.fetchone()
        if stats and stats['total_count'] and not stats['pending_count'] and stats['sent_count'] == stats['total_count']:
            cursor.execute(
                "UPDATE announcements SET status = 'sent', sent_at = NOW(), updated_at = NOW() WHERE id = %s",
                (announcement_id,),
            )
            connection.commit()

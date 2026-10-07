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
DEFAULT_SLOTS = ('10:00', '12:00', '14:00', '16:00', '18:00', '20:00')


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
    return {
        'id': service['id'],
        'name': service['name'],
        'description': service.get('description'),
        'price': float(service['price']) if service.get('price') is not None else None,
        'duration_minutes': service.get('duration_minutes'),
        'image_url': service.get('image_url'),
        'is_active': bool(service.get('is_active')),
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
    }


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


def get_services():
    services = fetch_all(
        """
        SELECT id, name, description, price, duration_minutes, image_url, is_active
        FROM services
        WHERE is_active = 1
        ORDER BY sort_order, id
        """
    )
    return [serialize_service(service) for service in services]


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
               COUNT(b.id) AS bookings_count,
               SUM(CASE WHEN b.booking_date >= CURDATE() AND b.status IN ('pending', 'confirmed') THEN 1 ELSE 0 END) AS upcoming_count
        FROM clients c
        LEFT JOIN bookings b ON b.client_id = c.id
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
    }
    client['upcoming_bookings'] = [
        booking for booking in client['bookings']
        if booking['status'] in ('pending', 'confirmed')
        and booking['booking_date'] >= date.today().isoformat()
    ]
    return client

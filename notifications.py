import json
import logging
from urllib.error import URLError
from urllib.request import Request, urlopen

from config import TELEGRAM_BOOKINGS_CHAT_ID, TELEGRAM_BOT_TOKEN


logger = logging.getLogger(__name__)


STATUS_LABELS = {
    'pending': 'Очікує підтвердження',
    'confirmed': 'Підтверджено',
    'cancelled': 'Скасовано',
    'completed': 'Завершено',
}


def _line(label, value):
    if value in (None, ''):
        return None
    return f"{label}: {value}"


def format_booking_message(booking):
    client = booking.get('client_name') or 'Клієнт'
    username = booking.get('username')
    telegram = f"@{username}" if username else None

    lines = [
        'Нове бронювання',
        '',
        _line('Дата', booking.get('booking_date')),
        _line('Час', booking.get('booking_time')),
        _line('Послуга', booking.get('service_name')),
        '',
        _line('Клієнт', client),
        _line('Телефон', booking.get('phone')),
        _line('Telegram', telegram),
        _line('Email', booking.get('email')),
    ]

    comment = booking.get('comment')
    if comment:
        lines.extend(['', 'Коментар:', comment])

    lines.extend([
        '',
        _line('Booking', f"#{booking.get('id')}"),
        _line('Статус', STATUS_LABELS.get(booking.get('status'), booking.get('status'))),
    ])

    return '\n'.join(line for line in lines if line is not None)


def send_booking_notification(booking):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_BOOKINGS_CHAT_ID:
        logger.info('Telegram booking notification skipped: token or chat id is missing')
        return False

    payload = {
        'chat_id': TELEGRAM_BOOKINGS_CHAT_ID,
        'text': format_booking_message(booking),
        'disable_web_page_preview': True,
    }
    data = json.dumps(payload).encode('utf-8')
    request = Request(
        f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urlopen(request, timeout=8) as response:
            result = json.loads(response.read().decode('utf-8'))
            if not result.get('ok'):
                logger.warning('Telegram booking notification failed: %s', result)
                return False
            return True
    except (OSError, URLError, json.JSONDecodeError) as exc:
        logger.warning('Telegram booking notification failed: %s', exc)
        return False

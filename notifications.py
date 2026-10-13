import json
import logging
from html import escape
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


def send_telegram_message(chat_id, text):
    ok, _error = send_telegram_payload('sendMessage', {
        'chat_id': chat_id,
        'text': text,
        'disable_web_page_preview': True,
    })
    return ok


def send_telegram_payload(method, payload):
    chat_id = payload.get('chat_id')
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return False, 'token or chat id is missing'

    data = json.dumps(payload).encode('utf-8')
    request = Request(
        f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urlopen(request, timeout=8) as response:
            result = json.loads(response.read().decode('utf-8'))
            if not result.get('ok'):
                return False, result.get('description') or 'Telegram API error'
            return True, None
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return False, str(exc)


def send_announcement_message(chat_id, title, body, media_url=None, media_type=None):
    text = f"<b>{escape(title)}</b>\n\n{escape(body)}"
    if media_url and media_type == 'photo':
        return send_telegram_payload('sendPhoto', {
            'chat_id': chat_id,
            'photo': media_url,
            'caption': text,
            'parse_mode': 'HTML',
        })
    if media_url and media_type == 'video':
        return send_telegram_payload('sendVideo', {
            'chat_id': chat_id,
            'video': media_url,
            'caption': text,
            'parse_mode': 'HTML',
        })
    return send_telegram_payload('sendMessage', {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    })


def format_room_booking_admin_message(booking, admin_url=None):
    lines = [
        'Нова заявка на бронювання номера',
        '',
        _line('Клієнт', booking.get('guest_name')),
        _line('Телефон', booking.get('guest_phone')),
        _line('Номер', booking.get('room_name')),
        _line('Заїзд', f"{booking.get('check_in')} {booking.get('check_in_time') or ''}".strip()),
        _line('Виїзд', f"{booking.get('check_out')} {booking.get('check_out_time') or ''}".strip()),
        _line('Статус', STATUS_LABELS.get(booking.get('status'), booking.get('status'))),
    ]
    if booking.get('comment'):
        lines.extend(['', 'Коментар:', booking['comment']])
    if admin_url:
        lines.extend(['', admin_url])
    return '\n'.join(line for line in lines if line is not None)


def send_room_booking_admin_notification(booking, admin_url=None):
    if not TELEGRAM_BOOKINGS_CHAT_ID:
        logger.info('Room booking admin notification skipped: chat id is missing')
        return False
    return send_telegram_message(
        TELEGRAM_BOOKINGS_CHAT_ID,
        format_room_booking_admin_message(booking, admin_url=admin_url),
    )


def format_room_booking_client_message(booking, status):
    name = booking.get('guest_name') or 'гостю'
    check_in = f"{booking.get('check_in')} {booking.get('check_in_time') or ''}".strip()
    check_out = f"{booking.get('check_out')} {booking.get('check_out_time') or ''}".strip()

    if status == 'confirmed':
        return (
            f"Вітаємо, {name}!\n\n"
            "Ваше бронювання підтверджено.\n\n"
            f"Номер: {booking.get('room_name')}\n"
            f"Заїзд: {check_in}\n"
            f"Виїзд: {check_out}\n\n"
            "Дякуємо, що обрали нас! Чекаємо на вас."
        )
    if status == 'cancelled':
        return (
            f"Добрий день, {name}.\n\n"
            f"На жаль, ваше бронювання номера «{booking.get('room_name')}» "
            f"на період {check_in} - {check_out} скасовано.\n\n"
            "Перепрошуємо за незручності. Наш адміністратор зв'яжеться з вами найближчим часом, "
            "щоб пояснити ситуацію та обговорити можливі варіанти.\n\n"
            "Дякуємо за розуміння."
        )
    return ''


def send_room_booking_client_notification(booking, status):
    if booking.get('client_notified_status') == status:
        return False
    if not booking.get('telegram_user_id'):
        logger.info('Room booking client notification skipped: booking is not linked to Telegram')
        return False
    text = format_room_booking_client_message(booking, status)
    if not text:
        return False
    return send_telegram_message(booking['telegram_user_id'], text)

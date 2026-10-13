import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from functools import wraps
from urllib.parse import parse_qsl

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import (
    ADMIN_NAME,
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    ROOM_CHECK_IN_TIME,
    ROOM_CHECK_OUT_TIME,
    SECRET_KEY,
    SITE_BASE_URL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_BOT_USERNAME,
)
from db import (
    BOOKING_STATUSES,
    STATUS_LABELS,
    DatabaseUnavailable,
    Error,
    IntegrityError,
    add_banner,
    add_room_photo,
    add_service_photo,
    cancel_booking,
    create_admin_user,
    create_booking,
    count_announcement_recipients,
    create_public_room_booking,
    delete_banner,
    delete_announcement,
    delete_room,
    delete_room_photo,
    delete_service,
    delete_service_photo,
    get_admin_booking,
    get_admin_bookings,
    get_admin_by_id,
    get_admin_by_username,
    get_admin_client,
    get_admin_clients,
    get_admin_rooms,
    get_announcement,
    get_announcements,
    get_availability,
    get_booking_notification_payload,
    get_client_bookings,
    get_client_room_bookings,
    get_dashboard_summary,
    get_banners,
    get_menu_categories,
    get_menu_category,
    get_menu_item,
    get_menu_items,
    get_public_menu,
    get_public_rooms,
    get_recent_bookings,
    get_room,
    get_room_booking,
    get_room_bookings,
    get_service,
    get_site_setting,
    get_services,
    mark_admin_login,
    save_room,
    save_room_booking,
    save_announcement,
    save_service,
    link_room_booking_to_telegram,
    mark_room_booking_admin_notified,
    mark_room_booking_client_notified,
    set_room_primary_photo,
    set_service_active,
    set_service_primary_photo,
    set_site_setting,
    save_menu_category,
    save_menu_item,
    serialize_client,
    finish_announcement_if_sent,
    mark_announcement_recipient_result,
    prepare_announcement_recipients,
    set_menu_category_active,
    set_menu_item_active,
    update_booking_status,
    update_banner,
    update_room_booking_status,
    update_room_photo_order,
    update_service_photo_order,
    upsert_client_from_telegram,
)
from notifications import (
    send_announcement_message,
    send_booking_notification,
    send_room_booking_admin_notification,
    send_room_booking_client_notification,
)


app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'menu')
ROOM_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'rooms')
BANNER_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'banners')
SITE_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'site')
SERVICE_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'services')
ANNOUNCEMENT_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'announcements')
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
ALLOWED_IMAGE_MIMES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'mov'}
ALLOWED_VIDEO_MIMES = {'video/mp4', 'video/webm', 'video/quicktime'}

DEFAULT_HOUSE_DATA = {
    'start_date': '2026-10-12T00:00:00.000Z',
    'end_date': '2026-10-14T00:00:00.000Z',
    'name': 'Лісова хатина',
    'description': "Дерев'яна хатина на узліссі з каміном.",
    'img': ['/static/img/vodogray.png', '/static/img/retro_comand.png'],
    'room_parap': ['2 гості', '25 м²', '1 спальня'],
    'comfort': ['Двоспальне ліжко', 'Камін', 'Душ і ванна', 'Wi-Fi', 'Кавова зона', 'Тераса', 'Вид на ліс', 'Опалення'],
}


def error_response(message, status=400):
    return jsonify({'error': message}), status


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        admin_id = session.get('admin_id')
        if not admin_id:
            return redirect(url_for('admin_login', next=request.path))

        try:
            admin = get_admin_by_id(admin_id)
        except (DatabaseUnavailable, Error):
            session.pop('admin_id', None)
            flash('Не вдалося перевірити admin session. Перевірте підключення до БД.', 'error')
            return redirect(url_for('admin_login'))

        if not admin:
            session.pop('admin_id', None)
            flash('Сесія адміністратора завершена. Увійдіть ще раз.', 'error')
            return redirect(url_for('admin_login'))

        g.admin = admin
        return view(*args, **kwargs)

    return wrapped


def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def allowed_announcement_media(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in (ALLOWED_IMAGE_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS)


def save_uploaded_menu_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_image(file_storage.filename):
        raise ValueError('Підтримуються тільки jpg, jpeg, png, webp або gif.')

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename = secure_filename(file_storage.filename)
    stem, ext = os.path.splitext(filename)
    stored_name = f"{stem[:42]}-{int(time.time())}{ext.lower()}"
    file_storage.save(os.path.join(UPLOAD_FOLDER, stored_name))
    return f"/static/uploads/menu/{stored_name}"


def save_uploaded_service_image(file_storage):
    return save_uploaded_image(file_storage, SERVICE_UPLOAD_FOLDER, '/static/uploads/services')


def save_uploaded_image(file_storage, upload_folder, url_prefix):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_image(file_storage.filename):
        raise ValueError('Підтримуються тільки jpg, jpeg, png, webp або gif.')
    if file_storage.mimetype not in ALLOWED_IMAGE_MIMES:
        raise ValueError('Файл має бути зображенням jpg, png, webp або gif.')

    os.makedirs(upload_folder, exist_ok=True)
    filename = secure_filename(file_storage.filename)
    _, ext = os.path.splitext(filename)
    stored_name = f"{uuid.uuid4().hex}{ext.lower()}"
    file_storage.save(os.path.join(upload_folder, stored_name))
    return f"{url_prefix}/{stored_name}"


def save_uploaded_announcement_media(file_storage):
    if not file_storage or not file_storage.filename:
        return None, None
    if not allowed_announcement_media(file_storage.filename):
        raise ValueError('Підтримуються jpg, jpeg, png, webp, gif, mp4, webm або mov.')
    if file_storage.mimetype in ALLOWED_IMAGE_MIMES:
        media_type = 'photo'
    elif file_storage.mimetype in ALLOWED_VIDEO_MIMES:
        media_type = 'video'
    else:
        raise ValueError('Файл має бути фото або відео.')
    os.makedirs(ANNOUNCEMENT_UPLOAD_FOLDER, exist_ok=True)
    filename = secure_filename(file_storage.filename)
    _, ext = os.path.splitext(filename)
    stored_name = f"{uuid.uuid4().hex}{ext.lower()}"
    file_storage.save(os.path.join(ANNOUNCEMENT_UPLOAD_FOLDER, stored_name))
    return f"/static/uploads/announcements/{stored_name}", media_type


def bool_from_form(name, default=False):
    if name not in request.form:
        return default
    return request.form.get(name) in ('1', 'true', 'on', 'yes')


def normalize_phone(value):
    phone = (value or '').strip()
    compact = re.sub(r'[\s().-]+', '', phone)
    if not re.fullmatch(r'\+?\d{9,15}', compact):
        raise ValueError('Вкажіть коректний номер телефону')
    return phone


def validate_room_booking_payload(data, room_id):
    user = data.get('telegram_user') or {}
    guest_name = ' '.join(
        part for part in [user.get('first_name'), user.get('last_name')]
        if part
    ).strip() or user.get('username') or (data.get('guest_name') or '').strip() or 'Клієнт'
    payload = {
        'room_id': room_id,
        'guest_name': guest_name,
        'guest_phone': normalize_phone(data.get('guest_phone')),
        'guest_email': '',
        'check_in': data.get('check_in'),
        'check_out': data.get('check_out'),
        'check_in_time': ROOM_CHECK_IN_TIME,
        'check_out_time': ROOM_CHECK_OUT_TIME,
        'comment': (data.get('comment') or '').strip(),
        'telegram_user_id': user.get('id'),
    }
    if not payload['check_in'] or not payload['check_out']:
        raise ValueError('Оберіть дату заїзду та виїзду на сторінці номерів')
    return payload


def calculate_booking_preview(room, payload):
    from datetime import datetime

    check_in = datetime.strptime(payload['check_in'], '%Y-%m-%d').date()
    check_out = datetime.strptime(payload['check_out'], '%Y-%m-%d').date()
    nights = (check_out - check_in).days
    if nights <= 0:
        raise ValueError('Дата виїзду повинна бути пізніше дати заїзду')
    total = float(room['price']) * nights if room.get('price') is not None else None
    return {**payload, 'room': room, 'nights': nights, 'total': total}


def ensure_room_available_for_payload(room, payload):
    if not room or not room.get('is_active'):
        raise LookupError('Номер не знайдено або він тимчасово недоступний')
    available_rooms = get_public_rooms(check_in=payload.get('check_in'), check_out=payload.get('check_out'))
    if not any(candidate['id'] == payload.get('room_id') for candidate in available_rooms):
        raise IntegrityError('Номер вже зайнятий на вибрані дати')


def site_base_url():
    return (SITE_BASE_URL or request.url_root.rstrip('/')).rstrip('/')


def room_booking_admin_url(booking_id):
    return f"{site_base_url()}{url_for('admin_room_booking_detail', booking_id=booking_id)}"


def telegram_link_url(token):
    if TELEGRAM_BOT_USERNAME:
        return f"https://t.me/{TELEGRAM_BOT_USERNAME}?start={token}"
    return None


def verify_telegram_init_data(init_data):
    if not TELEGRAM_BOT_TOKEN:
        return None
    if not init_data:
        return None

    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop('hash', None)
    if not received_hash:
        return None

    data_check_string = '\n'.join(
        f'{key}={value}' for key, value in sorted(values.items())
    )
    secret_key = hmac.new(
        b'WebAppData',
        TELEGRAM_BOT_TOKEN.encode(),
        hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        return None

    auth_date = values.get('auth_date')
    if not auth_date:
        return None
    try:
        if time.time() - int(auth_date) > 86400:
            return None
    except ValueError:
        return None

    user_data = values.get('user')
    if not user_data:
        return None

    try:
        return json.loads(user_data)
    except json.JSONDecodeError:
        return None


def get_init_data():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('tma '):
        return auth_header[4:]

    init_data = request.headers.get('X-Telegram-Init-Data')
    if init_data:
        return init_data

    if request.is_json:
        body = request.get_json(silent=True) or {}
        return body.get('initData')

    return request.args.get('tg_init_data')


def get_current_client():
    user = verify_telegram_init_data(get_init_data())
    if not user:
        return None
    return upsert_client_from_telegram(user)


@app.cli.command('create-admin')
def create_admin_command():
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise RuntimeError('Set ADMIN_USERNAME and ADMIN_PASSWORD before running create-admin')

    password_hash = generate_password_hash(ADMIN_PASSWORD)
    create_admin_user(ADMIN_USERNAME, password_hash, ADMIN_NAME)
    print(f"Admin user '{ADMIN_USERNAME}' is ready.")


@app.route('/')
def index():
    try:
        hero_image_url = get_site_setting('home_hero_image', '/static/img/vodogray.png')
        banners = get_banners(include_inactive=False)
    except (DatabaseUnavailable, Error):
        hero_image_url = '/static/img/vodogray.png'
        banners = []
    return render_template('index.html', hero_image_url=hero_image_url, banners=banners)

@app.route('/menu')
def info():
    return render_template('menu.html')

@app.route('/contact')
def contact():
    return render_template('contacts.html')

@app.route('/service')
def service():
    return render_template('services.html')

@app.route('/rooms')
def rooms():
    check_in = request.args.get('check_in') or None
    check_out = request.args.get('check_out') or None
    availability_error = None
    try:
        public_rooms = get_public_rooms(check_in=check_in, check_out=check_out)
    except ValueError as exc:
        availability_error = str(exc)
        public_rooms = []
    except (DatabaseUnavailable, Error):
        availability_error = 'Не вдалося перевірити доступність. Спробуйте пізніше.'
        public_rooms = []
    return render_template(
        'rooms.html',
        rooms=public_rooms,
        check_in=check_in,
        check_out=check_out,
        availability_error=availability_error,
        availability_checked=bool(check_in or check_out),
    )


@app.get('/my-bookings')
def my_bookings():
    return render_template('my_bookings.html')

@app.route('/house', methods=['GET', 'POST'])
@app.route('/house/<int:room_id>', methods=['GET'])
def house(room_id=None):
    if request.method == 'POST':
        data = request.get_json()
        session['house_data'] = data
        return '', 204

    if room_id:
        try:
            room = get_room(room_id, include_photos=True)
        except (DatabaseUnavailable, Error):
            room = None
        if not room or not room['is_active']:
            flash('Номер не знайдено або він тимчасово недоступний.', 'error')
            return redirect(url_for('rooms'))
        data = {
            'id': room['id'],
            'check_in': request.args.get('check_in') or '',
            'check_out': request.args.get('check_out') or '',
            'start_date': request.args.get('check_in') or DEFAULT_HOUSE_DATA['start_date'],
            'end_date': request.args.get('check_out') or DEFAULT_HOUSE_DATA['end_date'],
            'name': room['name'],
            'description': room['description'],
            'img': [photo['image_url'] for photo in room.get('photos', [])] or [room['primary_photo_url']],
            'room_parap': [
                f"{room['guests_count']} гостей",
                room['area'] or '',
                room['sleeping_places'] or '',
            ],
            'comfort': room['amenities_list'] or room['tags_list'],
        }
    else:
        data = session.get('house_data') or DEFAULT_HOUSE_DATA
    
    return render_template(
        'house.html',
        data=data
    )


@app.route('/rooms/<int:room_id>/book', methods=['GET', 'POST'])
def room_booking_start(room_id):
    try:
        room = get_room(room_id, include_photos=True)
    except (DatabaseUnavailable, Error):
        flash('Не вдалося завантажити номер. Спробуйте пізніше.', 'error')
        return redirect(url_for('rooms'))
    if not room or not room['is_active']:
        flash('Номер не знайдено або він тимчасово недоступний.', 'error')
        return redirect(url_for('rooms'))

    errors = []
    form = {
        'guest_phone': '',
        'check_in': request.args.get('check_in') or '',
        'check_out': request.args.get('check_out') or '',
        'comment': '',
    }
    if not form['check_in'] or not form['check_out']:
        flash('Спочатку оберіть дати заїзду та виїзду.', 'error')
        return redirect(url_for('rooms'))
    if request.method == 'POST':
        form.update({key: request.form.get(key, '') for key in form})
        try:
            telegram_user = verify_telegram_init_data(request.form.get('initData'))
            if not telegram_user:
                telegram_user = {
                    'id': request.form.get('telegram_user_id') or None,
                    'first_name': request.form.get('telegram_first_name') or None,
                    'last_name': request.form.get('telegram_last_name') or None,
                    'username': request.form.get('telegram_username') or None,
                }
            form['telegram_user'] = telegram_user
            form['guest_name'] = request.form.get('guest_name')
            payload = validate_room_booking_payload(form, room_id)
            preview = calculate_booking_preview(room, payload)
            ensure_room_available_for_payload(room, payload)
            session['pending_room_booking'] = payload
            session['pending_room_booking_preview'] = {
                'room_id': room_id,
                'nights': preview['nights'],
                'total': preview['total'],
            }
            session['room_booking_submit_token'] = secrets.token_urlsafe(24)
            return redirect(url_for('room_booking_preview'))
        except ValueError as exc:
            errors.append(str(exc))
        except IntegrityError:
            flash('На вибрані дати цей номер вже зайнятий. Оберіть інший номер або змініть дати.', 'error')
            return redirect(url_for('rooms', check_in=form.get('check_in'), check_out=form.get('check_out')))

    return render_template(
        'room_booking_form.html',
        room=room,
        form=form,
        errors=errors,
        check_in_time=ROOM_CHECK_IN_TIME,
        check_out_time=ROOM_CHECK_OUT_TIME,
    )


@app.get('/rooms/booking/preview')
def room_booking_preview():
    payload = session.get('pending_room_booking')
    if not payload:
        return redirect(url_for('rooms'))
    try:
        room = get_room(payload['room_id'], include_photos=True)
        preview = calculate_booking_preview(room, payload)
        ensure_room_available_for_payload(room, payload)
    except IntegrityError:
        flash('На вибрані дати цей номер вже зайнятий. Оберіть інший номер або змініть дати.', 'error')
        return redirect(url_for('rooms', check_in=payload.get('check_in'), check_out=payload.get('check_out')))
    except (TypeError, ValueError, LookupError, DatabaseUnavailable, Error):
        flash('Дані бронювання застаріли. Заповніть форму ще раз.', 'error')
        return redirect(url_for('rooms'))
    return render_template(
        'room_booking_preview.html',
        preview=preview,
        submit_token=session.get('room_booking_submit_token'),
    )


@app.post('/rooms/booking/confirm')
def room_booking_confirm():
    payload = session.get('pending_room_booking')
    submit_token = session.get('room_booking_submit_token')
    if not payload or not submit_token or request.form.get('submit_token') != submit_token:
        flash('Заявка вже оброблена або сесія застаріла. Заповніть форму ще раз.', 'error')
        return redirect(url_for('rooms'))

    try:
        room = get_room(payload['room_id'], include_photos=False)
        calculate_booking_preview(room, payload)
        link_token = secrets.token_urlsafe(32)
        booking = create_public_room_booking(payload, link_token=link_token)
        session.pop('pending_room_booking', None)
        session.pop('pending_room_booking_preview', None)
        session.pop('room_booking_submit_token', None)
        if send_room_booking_admin_notification(booking, admin_url=room_booking_admin_url(booking['id'])):
            mark_room_booking_admin_notified(booking['id'])
        session['last_room_booking_id'] = booking['id']
        return redirect(url_for('room_booking_success', booking_id=booking['id']))
    except IntegrityError:
        flash('На жаль, номер вже зайнятий на вибрані дати. Оберіть інший період.', 'error')
        return redirect(url_for('room_booking_start', room_id=payload.get('room_id'), check_in=payload.get('check_in'), check_out=payload.get('check_out')))
    except (ValueError, LookupError) as exc:
        flash(str(exc), 'error')
        return redirect(url_for('room_booking_start', room_id=payload.get('room_id'), check_in=payload.get('check_in'), check_out=payload.get('check_out')))
    except (DatabaseUnavailable, Error):
        flash('Не вдалося створити бронювання. Спробуйте ще раз пізніше.', 'error')
        return redirect(url_for('room_booking_start', room_id=payload.get('room_id'), check_in=payload.get('check_in'), check_out=payload.get('check_out')))


@app.get('/rooms/booking/success/<int:booking_id>')
def room_booking_success(booking_id):
    if session.get('last_room_booking_id') != booking_id:
        return redirect(url_for('rooms'))
    booking = get_room_booking(booking_id)
    if not booking:
        return redirect(url_for('rooms'))
    return render_template(
        'room_booking_success.html',
        booking=booking,
        telegram_link=None if booking.get('telegram_linked') else telegram_link_url(booking.get('telegram_link_token')),
    )


@app.get('/api/client/me')
def api_client_me():
    try:
        client = get_current_client()
    except DatabaseUnavailable as exc:
        return error_response(str(exc), 503)
    except Error:
        return error_response('Database error', 500)

    if not client:
        return error_response('Telegram authorization is required', 401)

    return jsonify({'client': serialize_client(client)})


@app.get('/api/services')
def api_services():
    try:
        return jsonify({'services': get_services()})
    except DatabaseUnavailable as exc:
        return error_response(str(exc), 503)
    except Error:
        return error_response('Database error', 500)


@app.get('/api/menu')
def api_menu():
    try:
        return jsonify({'categories': get_public_menu()})
    except DatabaseUnavailable as exc:
        return error_response(str(exc), 503)
    except Error:
        return error_response('Database error', 500)


@app.get('/api/bookings')
def api_bookings():
    try:
        client = get_current_client()
        if not client:
            return error_response('Telegram authorization is required', 401)
        return jsonify({'bookings': get_client_bookings(client['id'])})
    except DatabaseUnavailable as exc:
        return error_response(str(exc), 503)
    except Error:
        return error_response('Database error', 500)


@app.get('/api/room-bookings')
def api_room_bookings():
    try:
        client = get_current_client()
        if not client:
            return error_response('Telegram authorization is required', 401)
        return jsonify({'bookings': get_client_room_bookings(client['id'])})
    except DatabaseUnavailable as exc:
        return error_response(str(exc), 503)
    except Error:
        return error_response('Database error', 500)


@app.get('/api/booking/availability')
def api_booking_availability():
    service_id = request.args.get('service_id', type=int)
    start_date = request.args.get('start_date')

    if not service_id:
        return error_response('service_id is required')

    try:
        availability = get_availability(service_id, start_date=start_date)
    except ValueError:
        return error_response('Invalid date format. Use YYYY-MM-DD')
    except DatabaseUnavailable as exc:
        return error_response(str(exc), 503)
    except Error:
        return error_response('Database error', 500)

    if availability is None:
        return error_response('Service not found', 404)

    return jsonify({'availability': availability})


@app.post('/api/bookings')
def api_create_booking():
    data = request.get_json(silent=True) or {}

    try:
        client = get_current_client()
        if not client:
            return error_response('Telegram authorization is required', 401)

        booking = create_booking(
            client_id=client['id'],
            service_id=data.get('service_id'),
            booking_date=data.get('booking_date'),
            booking_time=data.get('booking_time'),
            comment=data.get('comment'),
        )
        notification_booking = get_booking_notification_payload(booking['id'])
        if notification_booking:
            send_booking_notification(notification_booking)
        return jsonify({'booking': booking}), 201
    except ValueError as exc:
        return error_response(str(exc))
    except LookupError as exc:
        return error_response(str(exc), 404)
    except IntegrityError:
        return error_response('Selected slot is already booked', 409)
    except DatabaseUnavailable as exc:
        return error_response(str(exc), 503)
    except Error:
        return error_response('Database error', 500)


@app.route('/admin')
def admin_index():
    if session.get('admin_id'):
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('admin_login'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        try:
            admin = get_admin_by_username(username)
            if admin and check_password_hash(admin['password_hash'], password):
                session.clear()
                session['admin_id'] = admin['id']
                mark_admin_login(admin['id'])
                return redirect(request.args.get('next') or url_for('admin_dashboard'))
        except DatabaseUnavailable as exc:
            flash(str(exc), 'error')
            return render_template('admin/login.html')
        except Error:
            flash('Помилка бази даних під час входу.', 'error')
            return render_template('admin/login.html')

        flash('Невірний логін або пароль.', 'error')

    return render_template('admin/login.html')


@app.post('/admin/logout')
@admin_required
def admin_logout():
    session.clear()
    flash('Ви вийшли з admin panel.', 'success')
    return redirect(url_for('admin_login'))


@app.get('/admin/dashboard')
@admin_required
def admin_dashboard():
    summary = get_dashboard_summary()
    today_bookings = get_admin_bookings(period='today', limit=8)
    upcoming_bookings = get_admin_bookings(period='upcoming', status=None, limit=8)
    recent_bookings = get_recent_bookings(limit=8)
    return render_template(
        'admin/dashboard.html',
        summary=summary,
        today_bookings=today_bookings,
        upcoming_bookings=upcoming_bookings,
        recent_bookings=recent_bookings,
    )


@app.get('/admin/bookings')
@admin_required
def admin_bookings():
    filters = {
        'period': request.args.get('period', 'upcoming'),
        'status': request.args.get('status') or None,
        'date': request.args.get('date') or None,
        'q': request.args.get('q', '').strip() or None,
    }
    bookings = get_admin_bookings(
        period=filters['period'],
        status=filters['status'],
        date_value=filters['date'],
        search=filters['q'],
    )
    return render_template(
        'admin/bookings.html',
        bookings=bookings,
        filters=filters,
        statuses=BOOKING_STATUSES,
        status_labels=STATUS_LABELS,
    )


@app.get('/admin/bookings/<int:booking_id>')
@admin_required
def admin_booking_detail(booking_id):
    booking = get_admin_booking(booking_id)
    if not booking:
        flash('Бронювання не знайдено.', 'error')
        return redirect(url_for('admin_bookings'))
    return render_template('admin/booking_detail.html', booking=booking, statuses=BOOKING_STATUSES, status_labels=STATUS_LABELS)


@app.post('/admin/bookings/<int:booking_id>/status')
@admin_required
def admin_booking_update_status(booking_id):
    status = request.form.get('status')
    try:
        booking = update_booking_status(booking_id, status)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('admin_booking_detail', booking_id=booking_id))

    if not booking:
        flash('Бронювання не знайдено.', 'error')
        return redirect(url_for('admin_bookings'))

    flash('Статус бронювання оновлено.', 'success')
    return redirect(url_for('admin_booking_detail', booking_id=booking_id))


@app.get('/admin/services')
@admin_required
def admin_services():
    search = request.args.get('q', '').strip()
    services = get_services(include_inactive=True, include_photos=True, search=search or None)
    return render_template('admin/services.html', services=services, search=search)


@app.route('/admin/services/new', methods=['GET', 'POST'])
@admin_required
def admin_service_new():
    return handle_service_form()


@app.route('/admin/services/<int:service_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_service_edit(service_id):
    return handle_service_form(service_id)


def handle_service_form(service_id=None):
    service = get_service(service_id, include_photos=True) if service_id else None
    if service_id and not service:
        flash('Послугу не знайдено.', 'error')
        return redirect(url_for('admin_services'))

    if request.method == 'POST':
        try:
            image_url = service['image_url'] if service else ''
            cover_upload = save_uploaded_service_image(request.files.get('cover_image'))
            if cover_upload:
                image_url = cover_upload
            elif request.form.get('remove_cover'):
                image_url = ''

            payload = {
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'price': request.form.get('price'),
                'price_unit': request.form.get('price_unit'),
                'duration_minutes': request.form.get('duration_minutes'),
                'conditions': request.form.get('conditions'),
                'image_url': image_url,
                'is_active': bool_from_form('is_active', default=False),
                'sort_order': request.form.get('sort_order'),
            }
            saved_service = save_service(payload, service_id=service_id)
            files = request.files.getlist('photos')
            for index, image in enumerate(files):
                photo_url = save_uploaded_service_image(image)
                if photo_url:
                    add_service_photo(saved_service['id'], photo_url, alt_text=saved_service['name'], sort_order=index)
            flash('Послугу збережено.', 'success')
            return redirect(url_for('admin_service_edit', service_id=saved_service['id']))
        except (ValueError, IntegrityError) as exc:
            flash(str(exc), 'error')
        except (DatabaseUnavailable, Error):
            flash('Помилка бази даних під час збереження послуги.', 'error')

    return render_template('admin/service_form.html', service=service)


@app.post('/admin/services/<int:service_id>/deactivate')
@admin_required
def admin_service_deactivate(service_id):
    if set_service_active(service_id, False):
        flash('Послугу вимкнено.', 'success')
    else:
        flash('Послугу не знайдено.', 'error')
    return redirect(url_for('admin_services'))


@app.post('/admin/services/<int:service_id>/delete')
@admin_required
def admin_service_delete(service_id):
    result = delete_service(service_id)
    if result == 'deactivated':
        flash('Послуга має бронювання, тому її вимкнено замість видалення.', 'success')
    elif result == 'deleted':
        flash('Послугу видалено.', 'success')
    else:
        flash('Послугу не знайдено.', 'error')
    return redirect(url_for('admin_services'))


@app.post('/admin/services/<int:service_id>/photos/<int:photo_id>/primary')
@admin_required
def admin_service_photo_primary(service_id, photo_id):
    if set_service_primary_photo(service_id, photo_id):
        flash('Головне фото послуги оновлено.', 'success')
    else:
        flash('Фото не знайдено.', 'error')
    return redirect(url_for('admin_service_edit', service_id=service_id))


@app.post('/admin/services/<int:service_id>/photos/order')
@admin_required
def admin_service_photo_order(service_id):
    orders = []
    for key, value in request.form.items():
        if key.startswith('sort_order_'):
            try:
                orders.append((int(key.replace('sort_order_', '')), int(value or 0)))
            except ValueError:
                continue
    update_service_photo_order(service_id, orders)
    flash('Порядок фотографій послуги оновлено.', 'success')
    return redirect(url_for('admin_service_edit', service_id=service_id))


@app.post('/admin/services/<int:service_id>/photos/<int:photo_id>/delete')
@admin_required
def admin_service_photo_delete(service_id, photo_id):
    if delete_service_photo(service_id, photo_id):
        flash('Фото видалено з послуги.', 'success')
    else:
        flash('Фото не знайдено.', 'error')
    return redirect(url_for('admin_service_edit', service_id=service_id))


@app.get('/admin/menu')
@admin_required
def admin_menu():
    filters = {
        'category_id': request.args.get('category_id', type=int),
        'availability': request.args.get('availability') or None,
        'q': request.args.get('q', '').strip() or None,
    }
    categories = get_menu_categories(include_inactive=True)
    items = get_menu_items(
        category_id=filters['category_id'],
        search=filters['q'],
        availability=filters['availability'],
        include_inactive=True,
    )
    return render_template('admin/menu.html', items=items, categories=categories, filters=filters)


@app.route('/admin/menu/new', methods=['GET', 'POST'])
@admin_required
def admin_menu_new():
    return handle_menu_form()


@app.route('/admin/menu/<int:item_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_menu_edit(item_id):
    return handle_menu_form(item_id)


def handle_menu_form(item_id=None):
    item = get_menu_item(item_id) if item_id else None
    if item_id and not item:
        flash('Страву не знайдено.', 'error')
        return redirect(url_for('admin_menu'))

    categories = get_menu_categories(include_inactive=True)
    if request.method == 'POST':
        try:
            image_url = item['image_url'] if item else ''
            uploaded_image = save_uploaded_menu_image(request.files.get('image_file'))
            if uploaded_image:
                image_url = uploaded_image
            elif request.form.get('remove_image'):
                image_url = ''
            elif request.form.get('image_url') is not None:
                image_url = request.form.get('image_url', '').strip()

            payload = {
                'category_id': request.form.get('category_id'),
                'name': request.form.get('name'),
                'description': request.form.get('description'),
                'price': request.form.get('price'),
                'image_url': image_url,
                'is_available': bool_from_form('is_available', default=False),
                'is_active': bool_from_form('is_active', default=False),
                'sort_order': request.form.get('sort_order'),
            }
            saved_item = save_menu_item(payload, item_id=item_id)
            flash('Страву збережено.', 'success')
            return redirect(url_for('admin_menu_edit', item_id=saved_item['id']))
        except (ValueError, LookupError, IntegrityError) as exc:
            flash(str(exc), 'error')

    return render_template('admin/menu_form.html', item=item, categories=categories)


@app.post('/admin/menu/<int:item_id>/deactivate')
@admin_required
def admin_menu_deactivate(item_id):
    if set_menu_item_active(item_id, False):
        flash('Страву деактивовано.', 'success')
    else:
        flash('Страву не знайдено.', 'error')
    return redirect(url_for('admin_menu'))


@app.get('/admin/categories')
@admin_required
def admin_categories():
    categories = get_menu_categories(include_inactive=True)
    return render_template('admin/categories.html', categories=categories)


@app.post('/admin/categories')
@admin_required
def admin_category_create():
    try:
        save_menu_category(
            name=request.form.get('name', '').strip(),
            sort_order=int(request.form.get('sort_order') or 0),
            is_active=bool_from_form('is_active', default=False),
        )
        flash('Категорію створено.', 'success')
    except (ValueError, IntegrityError) as exc:
        flash(str(exc), 'error')
    return redirect(url_for('admin_categories'))


@app.post('/admin/categories/<int:category_id>/edit')
@admin_required
def admin_category_edit(category_id):
    try:
        save_menu_category(
            name=request.form.get('name', '').strip(),
            sort_order=int(request.form.get('sort_order') or 0),
            is_active=bool_from_form('is_active', default=False),
            category_id=category_id,
        )
        flash('Категорію оновлено.', 'success')
    except (ValueError, IntegrityError) as exc:
        flash(str(exc), 'error')
    return redirect(url_for('admin_categories'))


@app.post('/admin/categories/<int:category_id>/deactivate')
@admin_required
def admin_category_deactivate(category_id):
    category = get_menu_category(category_id)
    if category and category['items_count']:
        flash('Категорію з активними стравами можна лише вимкнути після перенесення або деактивації страв.', 'error')
    elif set_menu_category_active(category_id, False):
        flash('Категорію деактивовано.', 'success')
    else:
        flash('Категорію не знайдено.', 'error')
    return redirect(url_for('admin_categories'))


@app.get('/admin/rooms')
@admin_required
def admin_rooms():
    search = request.args.get('q', '').strip()
    try:
        rooms = get_admin_rooms(search=search or None)
    except (DatabaseUnavailable, Error) as exc:
        rooms = []
        flash(str(exc) if isinstance(exc, DatabaseUnavailable) else 'Не вдалося завантажити номери.', 'error')
    return render_template('admin/rooms.html', rooms=rooms, search=search)


@app.route('/admin/rooms/new', methods=['GET', 'POST'])
@admin_required
def admin_room_new():
    return handle_room_form()


@app.route('/admin/rooms/<int:room_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_room_edit(room_id):
    return handle_room_form(room_id)


def handle_room_form(room_id=None):
    room = get_room(room_id, include_photos=True) if room_id else None
    if room_id and not room:
        flash('Номер не знайдено.', 'error')
        return redirect(url_for('admin_rooms'))

    if request.method == 'POST':
        try:
            payload = {
                'name': request.form.get('name'),
                'category': request.form.get('category'),
                'description': request.form.get('description'),
                'price': request.form.get('price'),
                'guests_count': request.form.get('guests_count'),
                'area': request.form.get('area'),
                'sleeping_places': request.form.get('sleeping_places'),
                'tags': request.form.get('tags'),
                'amenities': request.form.get('amenities'),
                'sort_order': request.form.get('sort_order'),
                'is_active': bool_from_form('is_active', default=False),
            }
            saved_room = save_room(payload, room_id=room_id)
            files = request.files.getlist('photos')
            for index, image in enumerate(files):
                image_url = save_uploaded_image(image, ROOM_UPLOAD_FOLDER, '/static/uploads/rooms')
                if image_url:
                    add_room_photo(saved_room['id'], image_url, alt_text=saved_room['name'], sort_order=index)
            flash('Номер збережено.', 'success')
            return redirect(url_for('admin_room_edit', room_id=saved_room['id']))
        except (ValueError, IntegrityError) as exc:
            flash(str(exc), 'error')
        except (DatabaseUnavailable, Error):
            flash('Помилка бази даних під час збереження номера.', 'error')

    return render_template('admin/room_form.html', room=room)


@app.post('/admin/rooms/<int:room_id>/photos/<int:photo_id>/primary')
@admin_required
def admin_room_photo_primary(room_id, photo_id):
    if set_room_primary_photo(room_id, photo_id):
        flash('Головне фото оновлено.', 'success')
    else:
        flash('Фото не знайдено.', 'error')
    return redirect(url_for('admin_room_edit', room_id=room_id))


@app.post('/admin/rooms/<int:room_id>/photos/order')
@admin_required
def admin_room_photo_order(room_id):
    orders = []
    for key, value in request.form.items():
        if key.startswith('sort_order_'):
            try:
                orders.append((int(key.replace('sort_order_', '')), int(value or 0)))
            except ValueError:
                continue
    update_room_photo_order(room_id, orders)
    flash('Порядок фотографій оновлено.', 'success')
    return redirect(url_for('admin_room_edit', room_id=room_id))


@app.post('/admin/rooms/<int:room_id>/photos/<int:photo_id>/delete')
@admin_required
def admin_room_photo_delete(room_id, photo_id):
    if delete_room_photo(room_id, photo_id):
        flash('Фото видалено з номера.', 'success')
    else:
        flash('Фото не знайдено.', 'error')
    return redirect(url_for('admin_room_edit', room_id=room_id))


@app.post('/admin/rooms/<int:room_id>/delete')
@admin_required
def admin_room_delete(room_id):
    result = delete_room(room_id)
    if result == 'deactivated':
        flash('Номер має повʼязані бронювання, тому його вимкнено замість видалення.', 'success')
    elif result == 'deleted':
        flash('Номер видалено.', 'success')
    else:
        flash('Номер не знайдено.', 'error')
    return redirect(url_for('admin_rooms'))


@app.get('/admin/room-bookings')
@admin_required
def admin_room_bookings():
    status = request.args.get('status') or None
    bookings = get_room_bookings(status=status)
    return render_template(
        'admin/room_bookings.html',
        bookings=bookings,
        statuses=BOOKING_STATUSES,
        status_labels=STATUS_LABELS,
        selected_status=status,
    )


@app.get('/admin/room-bookings/<int:booking_id>')
@admin_required
def admin_room_booking_detail(booking_id):
    booking = get_room_booking(booking_id)
    if not booking:
        flash('Бронювання номера не знайдено.', 'error')
        return redirect(url_for('admin_room_bookings'))
    return render_template(
        'admin/room_booking_detail.html',
        booking=booking,
        status_labels=STATUS_LABELS,
    )


@app.route('/admin/room-bookings/new', methods=['GET', 'POST'])
@admin_required
def admin_room_booking_new():
    return handle_room_booking_form()


@app.route('/admin/room-bookings/<int:booking_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_room_booking_edit(booking_id):
    return handle_room_booking_form(booking_id)


@app.post('/admin/room-bookings/<int:booking_id>/status')
@admin_required
def admin_room_booking_update_status(booking_id):
    status = request.form.get('status')
    try:
        booking, result = update_room_booking_status(booking_id, status)
    except IntegrityError:
        flash('Неможливо підтвердити: номер вже зайнятий на цей період.', 'error')
        return redirect(url_for('admin_room_booking_detail', booking_id=booking_id))
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('admin_room_booking_detail', booking_id=booking_id))

    if result == 'not_found':
        flash('Бронювання номера не знайдено.', 'error')
        return redirect(url_for('admin_room_bookings'))
    if result == 'unchanged':
        flash('Статус уже має це значення. Повторне сповіщення не надсилалось.', 'success')
        return redirect(url_for('admin_room_booking_detail', booking_id=booking_id))

    sent = False
    if status in ('confirmed', 'cancelled') and booking.get('telegram_user_id'):
        sent = send_room_booking_client_notification(booking, status)
        if sent:
            mark_room_booking_client_notified(booking['id'], status)
    if status in ('confirmed', 'cancelled'):
        if sent:
            flash('Статус оновлено, Telegram-сповіщення клієнту надіслано.', 'success')
        elif booking.get('telegram_user_id'):
            flash('Статус оновлено, але Telegram-сповіщення не вдалося надіслати.', 'error')
        else:
            flash('Статус оновлено. Telegram не привʼязаний до цієї заявки.', 'success')
    else:
        flash('Статус бронювання оновлено.', 'success')
    return redirect(url_for('admin_room_booking_detail', booking_id=booking_id))


@app.post('/admin/room-bookings/<int:booking_id>/notify')
@admin_required
def admin_room_booking_notify_client(booking_id):
    booking = get_room_booking(booking_id)
    if not booking:
        flash('Бронювання номера не знайдено.', 'error')
        return redirect(url_for('admin_room_bookings'))
    if booking['status'] not in ('confirmed', 'cancelled'):
        flash('Сповіщення доступне тільки для підтверджених або скасованих бронювань.', 'error')
        return redirect(url_for('admin_room_booking_detail', booking_id=booking_id))
    if not booking.get('telegram_user_id'):
        flash('Telegram не привʼязаний до цієї заявки.', 'error')
        return redirect(url_for('admin_room_booking_detail', booking_id=booking_id))
    if send_room_booking_client_notification({**booking, 'client_notified_status': None}, booking['status']):
        mark_room_booking_client_notified(booking['id'], booking['status'])
        flash('Telegram-сповіщення повторно надіслано.', 'success')
    else:
        flash('Не вдалося надіслати Telegram-сповіщення.', 'error')
    return redirect(url_for('admin_room_booking_detail', booking_id=booking_id))


def handle_room_booking_form(booking_id=None):
    booking = get_room_booking(booking_id) if booking_id else None
    if booking_id and not booking:
        flash('Бронювання номера не знайдено.', 'error')
        return redirect(url_for('admin_room_bookings'))
    rooms = get_admin_rooms(include_inactive=True)

    if request.method == 'POST':
        try:
            saved = save_room_booking(request.form, booking_id=booking_id)
            flash('Бронювання номера збережено.', 'success')
            return redirect(url_for('admin_room_booking_detail', booking_id=saved['id']))
        except ValueError as exc:
            flash(str(exc), 'error')
        except IntegrityError:
            flash('Номер вже зайнятий на вибрані дати.', 'error')
        except (DatabaseUnavailable, Error):
            flash('Помилка бази даних під час збереження бронювання.', 'error')

    return render_template(
        'admin/room_booking_form.html',
        booking=booking,
        rooms=rooms,
        statuses=BOOKING_STATUSES,
        status_labels=STATUS_LABELS,
    )


@app.get('/admin/home-content')
@admin_required
def admin_home_content():
    hero_image_url = get_site_setting('home_hero_image', '/static/img/vodogray.png')
    banners = get_banners(include_inactive=True)
    return render_template('admin/home_content.html', hero_image_url=hero_image_url, banners=banners)


@app.post('/admin/home-content/hero')
@admin_required
def admin_home_hero_update():
    try:
        image_url = save_uploaded_image(request.files.get('hero_image'), SITE_UPLOAD_FOLDER, '/static/uploads/site')
        if image_url:
            set_site_setting('home_hero_image', image_url)
            flash('Головне фото сайту оновлено.', 'success')
        else:
            flash('Оберіть файл зображення.', 'error')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('admin_home_content'))


@app.post('/admin/home-content/banners')
@admin_required
def admin_banner_create():
    try:
        image_url = save_uploaded_image(request.files.get('banner_image'), BANNER_UPLOAD_FOLDER, '/static/uploads/banners')
        if not image_url:
            flash('Оберіть файл банера.', 'error')
        else:
            add_banner(
                image_url=image_url,
                title=request.form.get('title'),
                is_active=bool_from_form('is_active', default=False),
                sort_order=request.form.get('sort_order') or 0,
            )
            flash('Банер додано.', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('admin_home_content'))


@app.post('/admin/home-content/banners/<int:banner_id>/edit')
@admin_required
def admin_banner_update(banner_id):
    if update_banner(
        banner_id,
        title=request.form.get('title'),
        is_active=bool_from_form('is_active', default=False),
        sort_order=request.form.get('sort_order') or 0,
    ):
        flash('Банер оновлено.', 'success')
    else:
        flash('Банер не знайдено.', 'error')
    return redirect(url_for('admin_home_content'))


@app.post('/admin/home-content/banners/<int:banner_id>/delete')
@admin_required
def admin_banner_delete(banner_id):
    if delete_banner(banner_id):
        flash('Банер видалено.', 'success')
    else:
        flash('Банер не знайдено.', 'error')
    return redirect(url_for('admin_home_content'))


@app.get('/admin/clients')
@admin_required
def admin_clients():
    search = request.args.get('q', '').strip()
    clients = get_admin_clients(search=search or None)
    return render_template('admin/clients.html', clients=clients, search=search)


@app.get('/admin/clients/<int:client_id>')
@admin_required
def admin_client_detail(client_id):
    client = get_admin_client(client_id)
    if not client:
        flash('Клієнта не знайдено.', 'error')
        return redirect(url_for('admin_clients'))
    return render_template('admin/client_detail.html', client=client)


def announcement_public_media_url(announcement):
    media_url = announcement.get('media_url')
    if not media_url:
        return None
    if media_url.startswith('http://') or media_url.startswith('https://'):
        return media_url
    if SITE_BASE_URL:
        return f"{SITE_BASE_URL.rstrip('/')}{media_url}"
    return None


def run_announcement_delivery(announcement_id, retry_failed=False):
    with app.app_context():
        try:
            announcement, recipients = prepare_announcement_recipients(announcement_id, retry_failed=retry_failed)
            media_url = announcement_public_media_url(announcement)
            for recipient in recipients:
                ok, error = send_announcement_message(
                    recipient['telegram_user_id'],
                    announcement['title'],
                    announcement['body'],
                    media_url=media_url,
                    media_type=announcement.get('media_type'),
                )
                mark_announcement_recipient_result(recipient['id'], ok, error)
                time.sleep(0.08)
            finish_announcement_if_sent(announcement_id)
        except Exception:
            app.logger.exception('Announcement delivery failed')


@app.get('/admin/announcements')
@admin_required
def admin_announcements():
    announcements = get_announcements()
    recipients_count = count_announcement_recipients()
    return render_template('admin/announcements.html', announcements=announcements, recipients_count=recipients_count)


@app.route('/admin/announcements/new', methods=['GET', 'POST'])
@admin_required
def admin_announcement_new():
    if request.method == 'POST':
        try:
            media_url, media_type = save_uploaded_announcement_media(request.files.get('media'))
            announcement = save_announcement(request.form, media_url=media_url, media_type=media_type)
            flash('Оголошення збережено.', 'success')
            return redirect(url_for('admin_announcement_detail', announcement_id=announcement['id']))
        except ValueError as exc:
            flash(str(exc), 'error')
        except (DatabaseUnavailable, Error):
            flash('Не вдалося зберегти оголошення.', 'error')
    return render_template('admin/announcement_form.html', announcement=None)


@app.route('/admin/announcements/<int:announcement_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_announcement_edit(announcement_id):
    announcement = get_announcement(announcement_id, include_recipients=True)
    if not announcement:
        flash('Оголошення не знайдено.', 'error')
        return redirect(url_for('admin_announcements'))
    if request.method == 'POST':
        try:
            media_url, media_type = save_uploaded_announcement_media(request.files.get('media'))
            announcement = save_announcement(
                request.form,
                announcement_id=announcement_id,
                media_url=media_url,
                media_type=media_type,
            )
            flash('Оголошення оновлено.', 'success')
            return redirect(url_for('admin_announcement_detail', announcement_id=announcement['id']))
        except ValueError as exc:
            flash(str(exc), 'error')
        except (DatabaseUnavailable, Error):
            flash('Не вдалося оновити оголошення.', 'error')
    return render_template('admin/announcement_form.html', announcement=announcement)


@app.get('/admin/announcements/<int:announcement_id>')
@admin_required
def admin_announcement_detail(announcement_id):
    announcement = get_announcement(announcement_id, include_recipients=True)
    if not announcement:
        flash('Оголошення не знайдено.', 'error')
        return redirect(url_for('admin_announcements'))
    recipients_count = count_announcement_recipients()
    return render_template('admin/announcement_detail.html', announcement=announcement, recipients_count=recipients_count)


@app.post('/admin/announcements/<int:announcement_id>/delete')
@admin_required
def admin_announcement_delete(announcement_id):
    try:
        if delete_announcement(announcement_id):
            flash('Оголошення видалено.', 'success')
        else:
            flash('Оголошення не знайдено.', 'error')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('admin_announcements'))


@app.post('/admin/announcements/<int:announcement_id>/send')
@admin_required
def admin_announcement_send(announcement_id):
    announcement = get_announcement(announcement_id)
    if not announcement:
        flash('Оголошення не знайдено.', 'error')
    elif announcement['status'] == 'draft':
        flash('Чернетки не можна надсилати.', 'error')
    elif announcement['status'] == 'sent':
        flash('Це оголошення вже надіслано. Для повтору використайте надсилання невдалим отримувачам.', 'error')
    else:
        thread = threading.Thread(target=run_announcement_delivery, args=(announcement_id,), daemon=True)
        thread.start()
        flash('Розсилку запущено у фоні.', 'success')
    return redirect(url_for('admin_announcement_detail', announcement_id=announcement_id))


@app.post('/admin/announcements/<int:announcement_id>/retry-failed')
@admin_required
def admin_announcement_retry_failed(announcement_id):
    thread = threading.Thread(target=run_announcement_delivery, args=(announcement_id, True), daemon=True)
    thread.start()
    flash('Повторне надсилання невдалим отримувачам запущено у фоні.', 'success')
    return redirect(url_for('admin_announcement_detail', announcement_id=announcement_id))


@app.get('/admin/settings')
@admin_required
def admin_settings():
    settings = {
        'telegram_token_configured': bool(TELEGRAM_BOT_TOKEN),
        'telegram_chat_configured': bool(os.environ.get('TELEGRAM_BOOKINGS_CHAT_ID')),
        'admin_username_configured': bool(ADMIN_USERNAME),
    }
    return render_template('admin/settings.html', settings=settings)


@app.patch('/api/bookings/<int:booking_id>/cancel')
def api_cancel_booking(booking_id):
    try:
        client = get_current_client()
        if not client:
            return error_response('Telegram authorization is required', 401)

        booking = cancel_booking(client['id'], booking_id)
        if not booking:
            return error_response('Booking not found', 404)
        return jsonify({'booking': booking})
    except DatabaseUnavailable as exc:
        return error_response(str(exc), 503)
    except Error:
        return error_response('Database error', 500)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

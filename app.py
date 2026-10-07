import hashlib
import hmac
import json
import os
import time
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

from config import ADMIN_NAME, ADMIN_PASSWORD, ADMIN_USERNAME, SECRET_KEY, TELEGRAM_BOT_TOKEN
from db import (
    BOOKING_STATUSES,
    DatabaseUnavailable,
    Error,
    IntegrityError,
    cancel_booking,
    create_admin_user,
    create_booking,
    get_admin_booking,
    get_admin_bookings,
    get_admin_by_id,
    get_admin_by_username,
    get_admin_client,
    get_admin_clients,
    get_availability,
    get_booking_notification_payload,
    get_client_bookings,
    get_dashboard_summary,
    get_menu_categories,
    get_menu_category,
    get_menu_item,
    get_menu_items,
    get_public_menu,
    get_recent_bookings,
    get_services,
    mark_admin_login,
    save_menu_category,
    save_menu_item,
    serialize_client,
    set_menu_category_active,
    set_menu_item_active,
    update_booking_status,
    upsert_client_from_telegram,
)
from notifications import send_booking_notification


app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 6 * 1024 * 1024

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'menu')
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}

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


def bool_from_form(name, default=False):
    if name not in request.form:
        return default
    return request.form.get(name) in ('1', 'true', 'on', 'yes')


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
    return render_template('index.html')

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
    return render_template('rooms.html')

@app.route('/house', methods=['GET', 'POST'])
def house():
    if request.method == 'POST':
        data = request.get_json()
        session['house_data'] = data
        return '', 204

    data = session.get('house_data') or DEFAULT_HOUSE_DATA
    
    return render_template(
        'house.html',
        data=data
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
    )


@app.get('/admin/bookings/<int:booking_id>')
@admin_required
def admin_booking_detail(booking_id):
    booking = get_admin_booking(booking_id)
    if not booking:
        flash('Бронювання не знайдено.', 'error')
        return redirect(url_for('admin_bookings'))
    return render_template('admin/booking_detail.html', booking=booking, statuses=BOOKING_STATUSES)


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

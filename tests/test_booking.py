import hashlib
import hmac
import json
import time
import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import app as web
import db

ROOM = {'id': 7, 'name': 'Номер із каталогу', 'is_active': True, 'price': 2400,
        'description': '', 'area': '24', 'guests_count': 2, 'sleeping_places': '',
        'photos': [], 'primary_photo_url': '/static/img/vodogray.png',
        'amenities_list': [], 'tags_list': []}
ARRIVAL = (date.today() + timedelta(days=10)).isoformat()
DEPARTURE = (date.today() + timedelta(days=12)).isoformat()


class BookingFlowTests(unittest.TestCase):
    def setUp(self):
        web.app.config.update(TESTING=True)
        self.client = web.app.test_client()
        self.patches = [patch.object(web, 'get_room', return_value=ROOM.copy()),
                        patch.object(web, 'get_public_rooms', return_value=[ROOM.copy()]),
                        patch.object(web, 'send_room_booking_admin_notification', return_value=False)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.client.get('/service')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf_token']

    def submit(self, **overrides):
        data = dict(check_in=ARRIVAL, check_out=DEPARTURE, guest_phone='+380991234567',
                    comment='Прохання', guest_name='Гість', csrf_token=self.csrf)
        data.update(overrides)
        return self.client.post('/rooms/7/book', data=data)

    def test_room_detail_has_real_date_form_and_id(self):
        page = self.client.get('/house/7').get_data(as_text=True)
        self.assertIn('action="/rooms/7/book"', page)
        self.assertIn('name="check_in"', page)
        self.assertIn('24 м²', page)
        self.assertNotIn('reserved_date', page)
        self.assertNotIn('Лісова хатина', page)

    def test_no_dates_keeps_room_and_allows_date_entry(self):
        response = self.client.get('/rooms/7/book')
        self.assertEqual(response.status_code, 200)
        self.assertIn('type="date" name="check_in"', response.get_data(as_text=True))

    def test_complete_flow_and_duplicate_submit(self):
        response = self.submit()
        self.assertTrue(response.location.endswith('/rooms/booking/preview'))
        with self.client.session_transaction() as session:
            payload = dict(session['pending_room_booking'])
            token = session['room_booking_submit_token']
        self.assertEqual(payload['room_id'], 7)
        self.assertEqual(payload['check_in'], ARRIVAL)
        self.assertEqual(payload['check_out'], DEPARTURE)
        self.assertEqual(self.client.get(response.location).status_code, 200)
        with patch.object(web, 'create_public_room_booking', return_value={'id': 90}) as save:
            response = self.client.post('/rooms/booking/confirm', data={'csrf_token': self.csrf, 'submit_token': token})
            self.assertTrue(response.location.endswith('/success/90'))
            self.client.post('/rooms/booking/confirm', data={'csrf_token': self.csrf, 'submit_token': token})
            self.assertEqual(save.call_count, 1)
        with patch.object(web, 'get_room_booking', return_value={'id': 90, 'room_name': ROOM['name'],
                         'status': 'pending', 'check_in': ARRIVAL, 'check_out': DEPARTURE}):
            self.assertEqual(self.client.get(response.location).status_code, 200)

    def test_return_to_edit_keeps_contact_and_comment(self):
        self.submit()
        page = self.client.get(f'/rooms/7/book?check_in={ARRIVAL}&check_out={DEPARTURE}').get_data(as_text=True)
        self.assertIn('+380991234567', page)
        self.assertIn('Прохання', page)

    def test_invalid_phone_no_pending_booking(self):
        self.assertEqual(self.submit(guest_phone='abc').status_code, 200)
        with self.client.session_transaction() as session:
            self.assertNotIn('pending_room_booking', session)

    def test_invalid_and_past_dates_rejected(self):
        for arrival, departure in [(DEPARTURE, ARRIVAL), ('bad', DEPARTURE),
                                   ('2000-01-01', '2000-01-02')]:
            with self.subTest(arrival=arrival):
                response = self.submit(check_in=arrival, check_out=departure)
                self.assertEqual(response.status_code, 200)
                with self.client.session_transaction() as session:
                    self.assertNotIn('pending_room_booking', session)

    def test_unavailable_room_keeps_selection_and_fields(self):
        with patch.object(web, 'get_public_rooms', return_value=[]):
            response = self.submit()
        self.assertEqual(response.status_code, 200)
        self.assertIn('Номер зайнятий', response.get_data(as_text=True))
        self.assertIn('+380991234567', response.get_data(as_text=True))

    def test_unsigned_telegram_id_never_linked(self):
        self.submit(telegram_user_id='1234', telegram_first_name='Підміна')
        with self.client.session_transaction() as session:
            self.assertIsNone(session['pending_room_booking']['telegram_user_id'])

    def test_csrf_rejected(self):
        self.assertEqual(self.submit(csrf_token='wrong').status_code, 400)
        self.assertEqual(self.submit(csrf_token='невірний').status_code, 400)

    def test_conflict_at_confirmation_does_not_clear_request(self):
        self.submit()
        with self.client.session_transaction() as session:
            token = session['room_booking_submit_token']
        with patch.object(web, 'create_public_room_booking', side_effect=db.IntegrityError('busy')):
            response = self.client.post('/rooms/booking/confirm', data={'csrf_token': self.csrf, 'submit_token': token})
        self.assertIn('/rooms/7/book', response.location)
        with self.client.session_transaction() as session:
            self.assertIn('pending_room_booking', session)

    def test_api_requires_telegram(self):
        self.assertEqual(self.client.post('/api/bookings', json={}).status_code, 401)

    def test_service_bad_payload_is_validation_error(self):
        with patch.object(web, 'get_current_client', return_value={'id': 1}):
            for payload in [{}, {'service_id': 1, 'booking_time': '10:00'},
                            {'service_id': 1, 'booking_time': 'invalid', 'booking_date': ARRIVAL}]:
                self.assertEqual(self.client.post('/api/bookings', json=payload).status_code, 400)

    def test_database_failure_graceful(self):
        with patch.object(web, 'get_services', side_effect=db.Error('offline')):
            response = self.client.get('/api/services')
            self.assertGreaterEqual(response.status_code, 500)
        with patch.object(web, 'get_room', side_effect=db.Error('offline')):
            self.assertEqual(self.client.get('/rooms/7/book').status_code, 302)

    def test_all_templates_compile(self):
        for template in web.app.jinja_env.list_templates():
            with self.subTest(template=template):
                web.app.jinja_env.get_template(template)


class DatabaseLogicTests(unittest.TestCase):
    def test_area_formats_once(self):
        for value, expected in [('24', '24 м²'), ('24 м²', '24 м²'), ('24.5', '24.5 м²'), (None, '')]:
            self.assertEqual(web.format_area(value), expected)

    def test_conditions_normalization(self):
        for value in [None, 'none', ' None ', 'null', 'undefined', '']:
            self.assertEqual(db.clean_optional_text(value), '')
        self.assertEqual(db.clean_optional_text('Правила закладу'), 'Правила закладу')

    def test_overlap_uses_checkout_then_checkin(self):
        with patch.object(db, 'fetch_one', return_value=None) as query:
            db.room_has_overlap(7, ARRIVAL, DEPARTURE)
            args = query.call_args.args[1]
            self.assertEqual(args, (7, date.fromisoformat(DEPARTURE), date.fromisoformat(ARRIVAL)))

    def test_public_dates_rejected_before_database(self):
        with patch.object(db, 'get_connection') as connection:
            with self.assertRaises(ValueError):
                db.create_public_room_booking({'room_id': 7, 'check_in': '2000-01-01', 'check_out': '2000-01-02'}, 'token')
            connection.assert_not_called()

    def test_public_booking_locks_room_checks_overlap_then_commits(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [{'id': 7}, None]
        cursor.lastrowid = 92
        connection = MagicMock()
        connection.cursor.return_value = cursor
        @contextmanager
        def connect():
            yield connection
        with patch.object(db, 'get_connection', connect), patch.object(db, 'get_room_booking', return_value={'id': 92}):
            result = db.create_public_room_booking(dict(room_id=7, check_in=ARRIVAL, check_out=DEPARTURE,
                  guest_name='Гість', guest_phone='+380991234567'), 'test-token')
        self.assertEqual(result['id'], 92)
        sql = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn('FOR UPDATE', sql[0])
        self.assertIn('check_in < %(check_out)s', sql[1])
        self.assertIn('INSERT INTO room_bookings', sql[2])
        connection.commit.assert_called_once()

    def test_public_overlap_prevents_insert(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [{'id': 7}, {'id': 91}]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        @contextmanager
        def connect():
            yield connection
        with patch.object(db, 'get_connection', connect):
            with self.assertRaises(db.IntegrityError):
                db.create_public_room_booking(dict(room_id=7, check_in=ARRIVAL, check_out=DEPARTURE,
                      guest_name='Гість', guest_phone='+380991234567'), 'test-token')
        connection.commit.assert_not_called()
        self.assertEqual(cursor.execute.call_count, 2)


class ServiceAvailabilityTests(unittest.TestCase):
    def test_duration_blocks_overlapping_start_but_allows_adjacent(self):
        occupied = dict(booking_date=date.fromisoformat(ARRIVAL), booking_time='10:00')
        with patch.object(db, 'fetch_one', return_value={'id': 1, 'duration_minutes': 180}), patch.object(db, 'fetch_all', return_value=[occupied]):
            availability = db.get_availability(1, start_date=ARRIVAL, days=1)
        self.assertNotIn('10:00', availability[0]['slots'])
        self.assertNotIn('12:00', availability[0]['slots'])
        self.assertIn('14:00', availability[0]['slots'])

    def test_missing_booking_date_is_validation_error(self):
        with self.assertRaises(ValueError):
            db.create_booking(1, 1, None, '10:00')

    def test_service_insert_after_lock_and_conflict_check(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [dict(id=1), dict(id=2, duration_minutes=180), None,
            dict(id=4, client_id=1, service_id=2, service_name='Послуга', booking_date=date.fromisoformat(ARRIVAL), booking_time='14:00', status='pending')]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        @contextmanager
        def connect():
            yield connection
        with patch.object(db, 'get_connection', connect):
            result = db.create_booking(1, 2, ARRIVAL, '14:00')
        self.assertEqual(result['id'], 4)
        sql = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn('FOR UPDATE', sql[1])
        self.assertIn('TIMESTAMPADD', sql[2])
        self.assertIn('INSERT INTO bookings', sql[3])
        connection.commit.assert_called_once()

    def test_admin_reactivation_cannot_overlap(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [dict(id=4, service_id=2, booking_date=date.fromisoformat(ARRIVAL), booking_time='14:00'), dict(duration_minutes=180), dict(id=5)]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        @contextmanager
        def connect():
            yield connection
        with patch.object(db, 'get_connection', connect):
            with self.assertRaises(db.IntegrityError):
                db.update_booking_status(4, 'confirmed')
        connection.commit.assert_not_called()

    def test_service_conflict_prevents_insert(self):
        cursor = MagicMock()
        cursor.fetchone.side_effect = [dict(id=1), dict(id=2, duration_minutes=60), dict(id=4)]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        @contextmanager
        def connect():
            yield connection
        with patch.object(db, 'get_connection', connect):
            with self.assertRaises(db.IntegrityError):
                db.create_booking(1, 2, ARRIVAL, '14:00')
        connection.commit.assert_not_called()


class TelegramSignatureTests(unittest.TestCase):
    def signed(self, user, auth_date=None):
        values = dict(auth_date=str(auth_date or int(time.time())), user=json.dumps(user))
        secret = hmac.new(b'WebAppData', b'test-token', hashlib.sha256).digest()
        data = '\n'.join(f'{key}={value}' for key, value in sorted(values.items()))
        values['hash'] = hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()
        return urlencode(values)

    def test_valid_invalid_expired_future_auth(self):
        with patch.object(web, 'TELEGRAM_BOT_TOKEN', 'test-token'):
            self.assertEqual(web.verify_telegram_init_data(self.signed({'id': 8})), {'id': 8})
            self.assertIsNone(web.verify_telegram_init_data(self.signed({'id': 8}) + 'tampered'))
            self.assertIsNone(web.verify_telegram_init_data(self.signed({'id': 8}, int(time.time())-90000)))
            self.assertIsNone(web.verify_telegram_init_data(self.signed({'id': 8}, int(time.time())+3600)))
            self.assertIsNone(web.verify_telegram_init_data(self.signed([])))


class PublicPageTests(unittest.TestCase):
    def test_public_routes_and_local_assets(self):
        from html.parser import HTMLParser
        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.urls = []
            def handle_starttag(self, tag, attrs):
                for key, value in attrs:
                    if key in ('src', 'href') and value and value.startswith('/'):
                        self.urls.append(value)
        with patch.object(web, 'get_banners', return_value=[]), patch.object(web, 'get_site_setting', side_effect=lambda key, default=None: default), patch.object(web, 'get_public_rooms', return_value=[ROOM]), patch.object(web, 'get_room', return_value=ROOM):
            client = web.app.test_client()
            for path in ['/', '/rooms', '/house/7', '/service', '/contact', '/menu', '/my-bookings', '/rooms/7/book']:
                response = client.get(path)
                self.assertEqual(response.status_code, 200, path)
                parser = Links()
                parser.feed(response.get_data(as_text=True))
                for url in parser.urls:
                    if url.startswith('/static/'):
                        with client.get(url) as asset:
                            self.assertEqual(asset.status_code, 200, url)

    def test_non_object_payload_rejected(self):
        response = web.app.test_client().post('/api/bookings', json=['bad'])
        self.assertEqual(response.status_code, 400)

    def test_admin_redirect_stays_local(self):
        from werkzeug.security import generate_password_hash
        client = web.app.test_client()
        client.get('/admin/login')
        with client.session_transaction() as session:
            token = session['csrf_token']
        admin = dict(id=1, username='test', password_hash=generate_password_hash('test'))
        with patch.object(web, 'get_admin_by_username', return_value=admin), patch.object(web, 'mark_admin_login'):
            response = client.post('/admin/login?next=https://outside.invalid', data=dict(username='test', password='test', csrf_token=token))
        self.assertEqual(response.location, '/admin/dashboard')


class BotTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        import importlib
        with patch('config.TELEGRAM_BOT_TOKEN', '123456:' + 'A'*35):
            cls.module = importlib.import_module('bot')

    def callback(self, data):
        from unittest.mock import AsyncMock
        callback = MagicMock(data=data)
        callback.answer = AsyncMock()
        callback.message.answer = AsyncMock()
        callback.message.answer_photo = AsyncMock()
        return callback

    def test_unique_menu_and_selected_service_url(self):
        menu = self.module.main_menu_keyboard()
        callbacks = [button.callback_data for row in menu.inline_keyboard for button in row if button.callback_data]
        self.assertEqual(callbacks.count('services'), 1)
        self.assertNotIn('prices', callbacks)
        keyboard = self.module.service_detail_keyboard(7)
        button = keyboard.inline_keyboard[0][0]
        self.assertIn('service_id=7', button.web_app.url if button.web_app else button.url)

    async def test_services_and_legacy_prices_callback(self):
        for data in ['services', 'prices']:
            callback = self.callback(data)
            with patch.object(self.module, 'get_services', return_value=[dict(id=1, name='Басейн', price=150)]):
                await self.module.callback_services(callback)
            callback.answer.assert_awaited_once()
            callback.message.answer.assert_awaited_once()

    async def test_details_hide_none_conditions(self):
        callback = self.callback('service:1')
        service = dict(id=1, name='Басейн', price=150, conditions='none', is_active=True)
        with patch.object(self.module, 'get_service', return_value=service):
            await self.module.callback_service_detail(callback)
        text = callback.message.answer.call_args.args[0]
        self.assertNotIn('none', text)
        self.assertIn('150', text)

    async def test_missing_service_and_contacts(self):
        callback = self.callback('service:99')
        with patch.object(self.module, 'get_service', return_value=None):
            await self.module.callback_service_detail(callback)
        self.assertIn('не знайдено', callback.message.answer.call_args.args[0])
        callback = self.callback('contacts')
        await self.module.callback_contacts(callback)
        callback.message.answer.assert_awaited_once()

    async def test_menu_and_bookings_callbacks(self):
        from unittest.mock import AsyncMock
        callback = self.callback('menu')
        with patch.object(self.module, 'send_main_menu', new_callable=AsyncMock) as send:
            await self.module.callback_menu(callback)
            send.assert_awaited_once()
        callback = self.callback('bookings')
        with patch.object(self.module, 'sync_client', new_callable=AsyncMock, return_value={'id': 1}), patch.object(self.module, 'get_client_bookings', return_value=[]), patch.object(self.module, 'get_client_room_bookings_by_telegram', return_value=[]):
            await self.module.callback_bookings(callback)
        callback.message.answer.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()

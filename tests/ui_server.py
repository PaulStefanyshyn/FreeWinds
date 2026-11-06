"""Isolated UI harness. Never deploy: fixtures only, no MySQL or Telegram writes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import date, timedelta
import app as web
from test_booking import ROOM

services = [dict(id=i, name=name, description=description, price=price, price_unit='год',
                duration_minutes=60, conditions='', image_url='/static/img/vodogray.png', is_active=True)
            for i, name, description, price in [
                (1, 'Басейн', 'Відпочинок у басейні серед гір.', 150),
                (2, 'Чани', 'Теплі чани для релаксу після прогулянки.', 180),
                (3, 'Баня', 'Класична баня для відновлення сил.', 50),
                (4, 'Більярд', 'Більярд для вечірнього відпочинку.', 360)]]
web.get_services = lambda **kwargs: services
web.get_room = lambda room_id, **kwargs: ROOM.copy() if room_id == 7 else None
web.get_public_rooms = lambda **kwargs: [ROOM.copy()]
web.get_site_setting = lambda key, default=None: default
web.get_banners = lambda **kwargs: []
web.get_public_menu = lambda: []
web.get_availability = lambda service_id, **kwargs: [dict(date=(date.today()+timedelta(days=i)).isoformat(), slots=['10:00', '12:00']) for i in range(1, 8)]
def prohibit_write(*args, **kwargs):
    raise web.DatabaseUnavailable('UI harness prohibits database writes')
import db
db.get_connection = prohibit_write
web.get_current_client = lambda: None
web.create_public_room_booking = prohibit_write
web.create_booking = prohibit_write
web.get_room_booking = lambda booking_id: None
web.send_room_booking_admin_notification = lambda *args, **kwargs: False
web.send_booking_notification = lambda *args, **kwargs: False
if __name__ == '__main__':
    print('ISOLATED UI FIXTURES: MySQL and outbound notifications disabled')
    web.app.run(host='127.0.0.1', port=5057, debug=False)

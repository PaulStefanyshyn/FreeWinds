import os

SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-production')

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_BOOKINGS_CHAT_ID = os.environ.get('TELEGRAM_BOOKINGS_CHAT_ID', '')
WEB_APP_URL = os.environ.get('WEB_APP_URL', 'http://localhost:5000/service')

ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', '')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
ADMIN_NAME = os.environ.get('ADMIN_NAME', 'Administrator')

MYSQL_HOST = os.environ.get('MYSQL_HOST', '127.0.0.1')
MYSQL_PORT = int(os.environ.get('MYSQL_PORT', '3306'))
MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'freewinds')
MYSQL_USER = os.environ.get('MYSQL_USER', 'freewinds_user')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')

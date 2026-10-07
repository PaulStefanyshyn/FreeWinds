import asyncio 
import logging 
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.client.default import DefaultBotProperties

from config import TELEGRAM_BOT_TOKEN, WEB_APP_URL
from db import DatabaseUnavailable, Error, upsert_client_from_telegram

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

@dp.message(CommandStart())
async def command_start(message: types.Message):
    user = message.from_user
    if user:
        try:
            upsert_client_from_telegram({
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "language_code": user.language_code,
                "is_premium": user.is_premium,
            })
        except (DatabaseUnavailable, Error) as exc:
            logging.exception("Could not sync Telegram client: %s", exc)

    web_app_btn = InlineKeyboardButton(
        text='Додаток',
        web_app=WebAppInfo(url=WEB_APP_URL)
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[web_app_btn]])

    await message.answer(
        "Вітаю! Натисніть кнопку нижче, щоб переглянути номери та забронювати послуги.",
        reply_markup=keyboard
    )

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())


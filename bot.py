import asyncio 
import logging 
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = "8898080463:AAEL48lQWxCHNsWGEheaTKCu4FnL6AsvJcs"
WEB_APP_URL = "https://youtube.com"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

@dp.message(CommandStart())
async def command_start(message: types.Message):
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





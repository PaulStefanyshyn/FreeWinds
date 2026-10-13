import asyncio
import logging
from html import escape

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import SITE_BASE_URL, TELEGRAM_BOT_TOKEN, WEB_APP_URL
from db import (
    DatabaseUnavailable,
    Error,
    get_client_bookings,
    get_client_room_bookings_by_telegram,
    get_service,
    get_services,
    link_room_booking_to_telegram,
    upsert_client_from_telegram,
)

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()


def get_site_url(path="/"):
    base = (SITE_BASE_URL or WEB_APP_URL.rsplit("/", 1)[0]).rstrip("/")
    return f"{base}{path}"


def web_or_url_button(text, url):
    if url.startswith("https://"):
        return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))
    return InlineKeyboardButton(text=text, url=url)


def main_menu_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [web_or_url_button("🏡 Забронювати номер", get_site_url("/rooms"))],
            [
                InlineKeyboardButton(text="🛁 Чан, сауна та баня", callback_data="services"),
                InlineKeyboardButton(text="💰 Ціни та послуги", callback_data="prices"),
            ],
            [InlineKeyboardButton(text="🛎️ Мої бронювання", callback_data="bookings")],
            [InlineKeyboardButton(text="📍 Контакти й розташування", callback_data="contacts")],
            [web_or_url_button("🌐 Відкрити сайт", get_site_url("/"))],
        ]
    )


def back_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Головне меню", callback_data="menu")]]
    )


def services_keyboard(services):
    rows = [
        [InlineKeyboardButton(text=service["name"], callback_data=f"service:{service['id']}")]
        for service in services
    ]
    rows.append([web_or_url_button("Відкрити бронювання послуг", WEB_APP_URL)])
    rows.append([InlineKeyboardButton(text="⬅️ Головне меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_detail_keyboard(service_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [web_or_url_button("Забронювати послугу", WEB_APP_URL)],
            [InlineKeyboardButton(text="⬅️ До списку послуг", callback_data="services")],
            [InlineKeyboardButton(text="🏠 Головне меню", callback_data="menu")],
        ]
    )


def format_price(service):
    price = service.get("price")
    if price is None:
        return "ціну уточнюйте"
    return f"{price:g} грн / {service.get('price_unit') or 'год'}"


def format_service_detail(service):
    lines = [
        f"<b>{escape(service['name'])}</b>",
        "",
        escape(service.get("description") or "Опис поки не заповнено."),
        "",
        f"Ціна: {format_price(service)}",
    ]
    if service.get("duration_minutes"):
        lines.append(f"Тривалість: {service['duration_minutes']} хв")
    if service.get("conditions"):
        lines.extend(["", f"Умови: {escape(service['conditions'])}"])
    return "\n".join(lines)


async def sync_client(user):
    if not user:
        return None
    return upsert_client_from_telegram(
        {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "language_code": user.language_code,
            "is_premium": user.is_premium,
        }
    )


async def send_main_menu(message):
    await message.answer(
        "Вітаємо! 🌿\n\n"
        "Раді допомогти вам спланувати відпочинок!\n\n"
        "Оберіть, що вас цікавить, у меню нижче: переглядайте номери, "
        "бронюйте проживання, дізнавайтеся про наші послуги та зв'язуйтеся з адміністратором.",
        reply_markup=main_menu_keyboard(),
    )


@dp.message(CommandStart())
async def command_start(message: types.Message):
    user = message.from_user
    if user:
        try:
            await sync_client(user)
        except (DatabaseUnavailable, Error) as exc:
            logging.exception("Could not sync Telegram client: %s", exc)

    args = ""
    if message.text and len(message.text.split(maxsplit=1)) > 1:
        args = message.text.split(maxsplit=1)[1].strip()

    if args and user:
        try:
            booking = link_room_booking_to_telegram(args, user.id)
            if booking:
                await message.answer(
                    "Готово! Telegram привʼязано до вашої заявки "
                    f"#{booking['id']} на номер «{booking['room_name']}». "
                    "Ми повідомимо вас після підтвердження або скасування."
                )
                await send_main_menu(message)
                return
            await message.answer(
                "Не вдалося знайти активну заявку для привʼязки. "
                "Перевірте посилання або зверніться до адміністратора."
            )
            await send_main_menu(message)
            return
        except (DatabaseUnavailable, Error) as exc:
            logging.exception("Could not link room booking to Telegram: %s", exc)
            await message.answer("Не вдалося привʼязати заявку. Спробуйте пізніше.")
            return

    await send_main_menu(message)


@dp.callback_query(F.data == "menu")
async def callback_menu(callback: types.CallbackQuery):
    await callback.answer()
    await send_main_menu(callback.message)


@dp.callback_query(F.data.in_({"services", "prices"}))
async def callback_services(callback: types.CallbackQuery):
    await callback.answer()
    try:
        services = get_services(include_photos=True)
    except (DatabaseUnavailable, Error) as exc:
        logging.exception("Could not load services: %s", exc)
        await callback.message.answer(
            "Не вдалося завантажити послуги. Спробуйте пізніше.",
            reply_markup=back_keyboard(),
        )
        return

    if not services:
        await callback.message.answer(
            "Наразі ми оновлюємо інформацію про послуги. "
            "Будь ласка, зв'яжіться з адміністратором, щоб уточнити деталі.",
            reply_markup=back_keyboard(),
        )
        return

    text = "<b>Послуги та ціни</b>\n\n" + "\n".join(
        f"• {escape(service['name'])} - {format_price(service)}" for service in services
    )
    await callback.message.answer(text, reply_markup=services_keyboard(services))


@dp.callback_query(F.data.startswith("service:"))
async def callback_service_detail(callback: types.CallbackQuery):
    await callback.answer()
    try:
        service_id = int(callback.data.split(":", 1)[1])
        service = get_service(service_id, include_photos=True)
    except (TypeError, ValueError, DatabaseUnavailable, Error) as exc:
        logging.exception("Could not load service: %s", exc)
        service = None

    if not service or not service.get("is_active"):
        await callback.message.answer("Послугу не знайдено або тимчасово приховано.", reply_markup=back_keyboard())
        return

    text = format_service_detail(service)
    image_url = service.get("image_url")
    if image_url and image_url.startswith("/"):
        image_url = get_site_url(image_url)

    if image_url and image_url.startswith(("http://", "https://")):
        try:
            await callback.message.answer_photo(
                photo=image_url,
                caption=text,
                reply_markup=service_detail_keyboard(service["id"]),
            )
            return
        except Exception as exc:
            logging.warning("Could not send service photo %s: %s", image_url, exc)
    await callback.message.answer(text, reply_markup=service_detail_keyboard(service["id"]))


@dp.callback_query(F.data == "bookings")
async def callback_bookings(callback: types.CallbackQuery):
    await callback.answer()
    user = callback.from_user
    try:
        client = await sync_client(user)
        service_bookings = get_client_bookings(client["id"]) if client else []
        room_bookings = get_client_room_bookings_by_telegram(user.id) if user else []
    except (DatabaseUnavailable, Error) as exc:
        logging.exception("Could not load client bookings: %s", exc)
        await callback.message.answer("Не вдалося завантажити бронювання. Спробуйте пізніше.", reply_markup=back_keyboard())
        return

    lines = ["<b>Мої бронювання</b>"]
    if room_bookings:
        lines.extend(["", "Номери:"])
        for booking in room_bookings[:8]:
            lines.append(
                f"• #{booking['id']} {escape(booking['room_name'] or '')}: "
                f"{booking['check_in']} - {booking['check_out']} ({booking['status_label']})"
            )
    if service_bookings:
        lines.extend(["", "Послуги:"])
        for booking in service_bookings[:8]:
            lines.append(
                f"• #{booking['id']} {escape(booking['service_name'] or '')}: "
                f"{booking['booking_date']} о {booking['booking_time']} ({booking['status']})"
            )
    if len(lines) == 1:
        lines.append("")
        lines.append("Поки не бачу бронювань, прив'язаних до вашого Telegram.")
        lines.append("Якщо ви бронювали номер на сайті, відкрийте посилання прив'язки з екрана успішної заявки.")

    await callback.message.answer("\n".join(lines), reply_markup=back_keyboard())


@dp.callback_query(F.data == "contacts")
async def callback_contacts(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "<b>Контакти й розташування</b>\n\n"
        "Актуальні контакти та карту можна переглянути на сайті. "
        "Якщо потрібна швидка відповідь, напишіть адміністратору в цьому чаті або скористайтесь сторінкою контактів.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [web_or_url_button("Відкрити контакти", get_site_url("/contact"))],
                [InlineKeyboardButton(text="⬅️ Головне меню", callback_data="menu")],
            ]
        ),
    )


async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.set_my_commands([BotCommand(command="start", description="Головне меню")])
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging
import sqlite3
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    Message,
    LabeledPrice,
    PreCheckoutQuery
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

# =========================================================
# SOZLAMALAR
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

ADMIN_USERNAME = "javohirkasimov"

ADMIN_CHAT = int(os.getenv("5303864442"))

CARD_NUMBER = os.getenv("CARD_NUMBER")
CARD_OWNER = os.getenv("CARD_OWNER", "JAVOHIR QOSIMOV")

# TEST UCHUN 60 UC NARXI
# Bu 12 900 so'mning avtomatik kursi EMAS.
# Hozircha Telegram Stars test narxi sifatida 10 Stars.
PUBG_STARS_PRICE = 10


logging.basicConfig(level=logging.INFO)

dp = Dispatcher(storage=MemoryStorage())


# =========================================================
# MAHSULOTLAR
# =========================================================

PUBG_PRODUCTS = {
    "60": {
        "name": "PUBG Mobile 60 UC",
        "price": 12_900,
        "stars": PUBG_STARS_PRICE
    },
    "325": {
        "name": "PUBG Mobile 325 UC",
        "price": 61_000,
        "stars": 300
    },
    "660": {
        "name": "PUBG Mobile 660 UC",
        "price": 119_000,
        "stars": 550
    },
    "1800": {
        "name": "PUBG Mobile 1800 UC",
        "price": 303_000,
        "stars": 1400
    },
}


def fmt(price: int) -> str:
    return f"{price:,}".replace(",", " ")


# =========================================================
# DATABASE
# =========================================================

DB_PATH = "orders.db"


def db_init():
    with sqlite3.connect(DB_PATH) as db:

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                product TEXT NOT NULL,
                price INTEGER NOT NULL,
                player_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                receipt_file_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        # Stars uchun yangi ustunlar
        try:
            db.execute(
                "ALTER TABLE orders ADD COLUMN payment_method TEXT"
            )
        except sqlite3.OperationalError:
            pass

        try:
            db.execute(
                "ALTER TABLE orders ADD COLUMN telegram_charge_id TEXT"
            )
        except sqlite3.OperationalError:
            pass

        db.commit()


def db_create_order(
    user_id,
    username,
    product,
    price,
    player_id,
    payment_method="card"
) -> int:

    with sqlite3.connect(DB_PATH) as db:

        cur = db.execute(
            """
            INSERT INTO orders
            (
                user_id,
                username,
                product,
                price,
                player_id,
                status,
                payment_method,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                user_id,
                username,
                product,
                price,
                player_id,
                payment_method,
                datetime.now().strftime("%Y-%m-%d %H:%M")
            )
        )

        db.commit()

        return cur.lastrowid


def db_get_order(order_id: int):

    with sqlite3.connect(DB_PATH) as db:

        db.row_factory = sqlite3.Row

        return db.execute(
            "SELECT * FROM orders WHERE id = ?",
            (order_id,)
        ).fetchone()


def db_set_status(order_id: int, status: str):

    with sqlite3.connect(DB_PATH) as db:

        db.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id)
        )

        db.commit()


def db_set_receipt(order_id: int, file_id: str):

    with sqlite3.connect(DB_PATH) as db:

        db.execute(
            """
            UPDATE orders
            SET receipt_file_id = ?, status = 'checking'
            WHERE id = ?
            """,
            (file_id, order_id)
        )

        db.commit()


def db_set_stars_paid(order_id: int, charge_id: str):

    with sqlite3.connect(DB_PATH) as db:

        db.execute(
            """
            UPDATE orders
            SET status = 'paid',
                telegram_charge_id = ?,
                payment_method = 'telegram_stars'
            WHERE id = ?
            """,
            (charge_id, order_id)
        )

        db.commit()


def db_user_orders(user_id: int, limit: int = 10):

    with sqlite3.connect(DB_PATH) as db:

        db.row_factory = sqlite3.Row

        return db.execute(
            """
            SELECT *
            FROM orders
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit)
        ).fetchall()


STATUS_TEXT = {
    "pending": "⏳ To'lov kutilmoqda",
    "checking": "🔎 Tekshirilmoqda",
    "paid": "✅ Bajarildi",
    "rejected": "❌ Rad etildi",
    "cancelled": "🚫 Bekor qilindi",
}


# =========================================================
# FSM
# =========================================================

class OrderFlow(StatesGroup):

    waiting_player_id = State()
    waiting_receipt = State()
class PremiumFlow(StatesGroup):
    waiting_username = State()
    waiting_receipt = State()


PREMIUM_PRODUCTS = {
    "3": {
        "name": "Telegram Premium 3 oy",
        "price": 182_000
    },
    "6": {
        "name": "Telegram Premium 6 oy",
        "price": 235_000
    },
    "12": {
        "name": "Telegram Premium 12 oy",
        "price": 405_000
    }
}
# =========================================================
# YORDAMCHI
# =========================================================

async def safe_edit(
    callback: CallbackQuery,
    text: str,
    reply_markup=None
):

    try:

        await callback.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

    except TelegramBadRequest as e:

        if "message is not modified" not in str(e):
            raise


# =========================================================
# MENYU
# =========================================================

def main_menu():

    b = InlineKeyboardBuilder()

    b.button(
        text="🎮 PUBG Mobile",
        callback_data="pubg"
    )

    b.button(
        text="⭐ Telegram Stars",
        callback_data="stars"
    )

    b.button(
        text="💎 Telegram Premium",
        callback_data="premium"
    )

    b.button(
        text="📦 Buyurtmalarim",
        callback_data="orders"
    )

    b.button(
        text="📞 Yordam",
        callback_data="help"
    )

    b.adjust(1)

    return b.as_markup()


def back_button():

    b = InlineKeyboardBuilder()

    b.button(
        text="🔙 Bosh menyu",
        callback_data="back"
    )

    return b.as_markup()


# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await message.answer(
        "👋 Salom!\n\n"
        "🛒 <b>Kasimov TopUp</b> botiga xush kelibsiz!\n\n"
        "Xizmatlardan birini tanlang:",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )


@dp.message(Command("myid"))
async def my_id(message: Message):
    await message.answer(
        f"🆔 Sizning Telegram ID: <code>{message.from_user.id}</code>",
        parse_mode="HTML"
    )


# =========================================================
# BACK
# =========================================================

@dp.callback_query(F.data == "back")
async def back(
    callback: CallbackQuery,
    state: FSMContext
):

    await state.clear()

    await safe_edit(
        callback,
        "🛒 <b>Kasimov TopUp</b>\n\n"
        "Xizmatlardan birini tanlang:",
        main_menu()
    )

    await callback.answer()


# =========================================================
# PUBG
# =========================================================

@dp.callback_query(F.data == "pubg")
async def pubg(
    callback: CallbackQuery,
    state: FSMContext
):

    await state.clear()

    b = InlineKeyboardBuilder()

    for key, product in PUBG_PRODUCTS.items():

        b.button(
            text=(
                f"🔹 {key} UC — "
                f"{fmt(product['price'])} so'm"
            ),
            callback_data=f"buy_{key}"
        )

    b.button(
        text="🔙 Orqaga",
        callback_data="back"
    )

    b.adjust(1)

    await safe_edit(
        callback,
        "🎮 <b>PUBG Mobile</b>\n\n"
        "UC paketini tanlang:",
        b.as_markup()
    )

    await callback.answer()


# =========================================================
# PAKET TANLASH
# =========================================================

@dp.callback_query(F.data.startswith("buy_"))
async def choose_package(
    callback: CallbackQuery,
    state: FSMContext
):

    key = callback.data.removeprefix("buy_")

    product = PUBG_PRODUCTS.get(key)

    if not product:

        await callback.answer(
            "Paket topilmadi.",
            show_alert=True
        )

        return

    await state.set_state(
        OrderFlow.waiting_player_id
    )

    await state.update_data(
        product_key=key
    )

    b = InlineKeyboardBuilder()

    b.button(
        text="🔙 Orqaga",
        callback_data="pubg"
    )

    await safe_edit(
        callback,

        f"🎮 <b>{product['name']}</b>\n\n"
        f"💰 Narx: <b>{fmt(product['price'])} so'm</b>\n\n"
        f"⭐ Telegram Stars: <b>{product['stars']} Stars</b>\n\n"
        "🆔 Endi PUBG Mobile Player ID "
        "raqamingizni yuboring.\n\n"
        "Masalan:\n"
        "<code>5123456789</code>",

        b.as_markup()
    )

    await callback.answer()


# =========================================================
# PLAYER ID
# =========================================================

@dp.message(
    OrderFlow.waiting_player_id,
    F.text
)
async def receive_player_id(
    message: Message,
    state: FSMContext
):

    player_id = message.text.strip()

    if not player_id.isdigit() or not (
        5 <= len(player_id) <= 15
    ):

        await message.answer(
            "❌ Player ID faqat raqamlardan "
            "iborat bo'lishi kerak.\n\n"
            "Masalan:\n"
            "<code>5123456789</code>",
            parse_mode="HTML"
        )

        return

    data = await state.get_data()

    product = PUBG_PRODUCTS[
        data["product_key"]
    ]

    await state.update_data(
        player_id=player_id
    )

    b = InlineKeyboardBuilder()

    b.button(
        text="💳 Karta orqali to'lash",
        callback_data="pay_card"
    )

    b.button(
        text=f"⭐ {product['stars']} Stars orqali to'lash",
        callback_data="pay_stars"
    )

    b.button(
        text="❌ Bekor qilish",
        callback_data="cancel_order"
    )

    b.adjust(1)

    await message.answer(

        "📦 <b>Buyurtma ma'lumotlari</b>\n\n"

        f"🎮 Mahsulot: {product['name']}\n"
        f"🆔 Player ID: <code>{player_id}</code>\n"
        f"💰 Karta: <b>{fmt(product['price'])} so'm</b>\n"
        f"⭐ Stars: <b>{product['stars']} Stars</b>\n\n"

        "To'lov usulini tanlang:",

        reply_markup=b.as_markup(),

        parse_mode="HTML"
    )


# =========================================================
# KARTA TO'LOVI
# =========================================================

@dp.callback_query(F.data == "pay_card")
async def pay_card(
    callback: CallbackQuery,
    state: FSMContext
):

    data = await state.get_data()

    if (
        "product_key" not in data
        or "player_id" not in data
    ):

        await callback.answer(
            "Buyurtma topilmadi.",
            show_alert=True
        )

        return

    product = PUBG_PRODUCTS[
        data["product_key"]
    ]

    order_id = db_create_order(
        callback.from_user.id,
        callback.from_user.username,
        product["name"],
        product["price"],
        data["player_id"],
        "card"
    )

    await state.update_data(
        order_id=order_id
    )

    await state.set_state(
        OrderFlow.waiting_receipt
    )

    b = InlineKeyboardBuilder()

    b.button(
        text="❌ Bekor qilish",
        callback_data="cancel_order"
    )

    await safe_edit(

        callback,

        f"✅ <b>Buyurtma #{order_id}</b>\n\n"

        f"🎮 {product['name']}\n"
        f"🆔 Player ID: <code>{data['player_id']}</code>\n"
        f"💰 Summa: <b>{fmt(product['price'])} so'm</b>\n\n"

        "💳 <b>To'lov uchun karta:</b>\n"
        f"<code>{CARD_NUMBER}</code>\n"
        f"👤 {CARD_OWNER}\n\n"

        "To'lovni amalga oshirgach,\n"
        "📸 <b>chekni skrinshot qilib shu botga yuboring.</b>\n\n"
        "Chek adminingizga avtomatik yuboriladi.",

        b.as_markup()
    )

    await callback.answer(
        "Buyurtma yaratildi! ✅"
    )


# =========================================================
# CHEKNI QABUL QILISH
# =========================================================

@dp.message(
    OrderFlow.waiting_receipt,
    F.photo
)
async def receive_receipt(
    message: Message,
    state: FSMContext,
    bot: Bot
):

    data = await state.get_data()

    order_id = data.get("order_id")

    if not order_id:

        await message.answer(
            "❌ Buyurtma topilmadi.\n"
            "/start ni bosing."
        )

        await state.clear()

        return

    file_id = message.photo[-1].file_id

    db_set_receipt(
        order_id,
        file_id
    )

    order = db_get_order(
        order_id
    )

    if not order:

        await message.answer(
            "❌ Buyurtma topilmadi."
        )

        await state.clear()

        return

    username = (
        f"@{order['username']}"
        if order["username"]
        else "username yo'q"
    )

    b = InlineKeyboardBuilder()

    b.button(
        text="✅ Tasdiqlash",
        callback_data=f"adm_ok_{order_id}"
    )

    b.button(
        text="❌ Rad etish",
        callback_data=f"adm_no_{order_id}"
    )

    b.adjust(2)

    # ADMINGA CHEK RASMI + MA'LUMOT
    await bot.send_photo(
    ADMIN_CHAT,
    file_id,
    caption=(
        f"🆕 <b>YANGI TO'LOV</b>\n\n"
        f"📦 Buyurtma: <b>#{order_id}</b>\n"
        f"👤 Mijoz: {username} (<code>{order['user_id']}</code>)\n"
        f"🎮 {order['product']}\n"
        f"🆔 Player ID: <code>{order['player_id']}</code>\n"
        f"💰 Summa: <b>{fmt(order['price'])} so'm</b>\n\n"
        "📸 Chek skrinshoti yuqorida."
    ),
    reply_markup=b.as_markup(),
    parse_mode="HTML"
   )

    await state.clear()

    await message.answer(

        f"📸 <b>Chek qabul qilindi!</b>\n\n"
        f"📦 Buyurtma: <b>#{order_id}</b>\n\n"
        "🔎 Admin to'lovni tekshirmoqda.\n"
        "Tasdiqlangach sizga xabar keladi.",

        parse_mode="HTML",

        reply_markup=back_button()
    )


# =========================================================
# FOTO EMAS
# =========================================================

@dp.message(OrderFlow.waiting_receipt)
async def receipt_wrong_type(
    message: Message
):

    await message.answer(

        "📸 Iltimos, to'lov chekini "
        "<b>rasm/screenshot</b> ko'rinishida yuboring.",

        parse_mode="HTML"
    )


# =========================================================
# STARS TO'LOVI
# =========================================================

@dp.callback_query(F.data == "pay_stars")
async def pay_stars(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot
):

    data = await state.get_data()

    if (
        "product_key" not in data
        or "player_id" not in data
    ):

        await callback.answer(
            "Buyurtma topilmadi.",
            show_alert=True
        )

        return

    product = PUBG_PRODUCTS[
        data["product_key"]
    ]

    # Avval databasega buyurtma yaratamiz
    order_id = db_create_order(

        callback.from_user.id,

        callback.from_user.username,

        product["name"],

        product["price"],

        data["player_id"],

        "telegram_stars"
    )

    await state.update_data(
        order_id=order_id
    )

    # Telegram Stars invoice
    await bot.send_invoice(

        chat_id=callback.from_user.id,

        title=product["name"],

        description=(
            f"PUBG Mobile {product['name']} | "
            f"Player ID: {data['player_id']}"
        ),

        payload=f"PUBG_STARS:{order_id}",

        provider_token="",

        currency="XTR",

        prices=[
            LabeledPrice(
                label=product["name"],
                amount=product["stars"]
            )
        ]
    )

    await callback.answer()


# =========================================================
# PRE-CHECKOUT
# =========================================================

@dp.pre_checkout_query()
async def pre_checkout(
    query: PreCheckoutQuery
):

    payload = query.invoice_payload

    if not payload.startswith(
        "PUBG_STARS:"
    ):

        await query.answer(

            ok=False,

            error_message=(
                "❌ Buyurtma topilmadi."
            )
        )

        return

    try:

        order_id = int(
            payload.split(":")[1]
        )

    except (ValueError, IndexError):

        await query.answer(

            ok=False,

            error_message=(
                "❌ Buyurtma ID noto'g'ri."
            )
        )

        return

    order = db_get_order(
        order_id
    )

    if not order:

        await query.answer(

            ok=False,

            error_message=(
                "❌ Buyurtma topilmadi."
            )
        )

        return

    if order["status"] != "pending":

        await query.answer(

            ok=False,

            error_message=(
                "❌ Bu buyurtma allaqachon "
                "ishlangan."
            )
        )

        return

    await query.answer(
        ok=True
    )


# =========================================================
# STARS TO'LOVI MUVAFFAQIYATLI
# =========================================================

@dp.message(F.successful_payment)
async def successful_payment(
    message: Message,
    bot: Bot
):

    payment = message.successful_payment

    payload = payment.invoice_payload

    if not payload.startswith(
        "PUBG_STARS:"
    ):

        return

    try:

        order_id = int(
            payload.split(":")[1]
        )

    except (ValueError, IndexError):

        return

    order = db_get_order(
        order_id
    )

    if not order:

        return

    # Faqat haqiqiy successful_paymentdan
    # keyin paid qilamiz
    db_set_stars_paid(

        order_id,

        payment.telegram_payment_charge_id
    )

    await message.answer(

        f"✅ <b>To'lov muvaffaqiyatli!</b>\n\n"

        f"📦 Buyurtma: <b>#{order_id}</b>\n"
        f"🎮 {order['product']}\n"
        f"🆔 Player ID: "
        f"<code>{order['player_id']}</code>\n"
        f"⭐ To'lov: "
        f"<b>{payment.total_amount} Stars</b>\n\n"

        "💰 To'lov qabul qilindi.\n"
        "📦 Buyurtma tez orada bajariladi.",

        parse_mode="HTML"
    )

    # ADMINGA HAM STARS TO'LOVI HAQIDA XABAR
    await bot.send_message(

        ADMIN_CHAT,

        f"⭐ <b>YANGI STARS TO'LOVI</b>\n\n"

        f"📦 Buyurtma: <b>#{order_id}</b>\n"
        f"👤 User ID: <code>{order['user_id']}</code>\n"
        f"🎮 {order['product']}\n"
        f"🆔 Player ID: "
        f"<code>{order['player_id']}</code>\n"
        f"⭐ To'langan: "
        f"<b>{payment.total_amount} Stars</b>\n\n"

        "✅ Telegram Stars orqali to'lov muvaffaqiyatli.",

        parse_mode="HTML"
    )


# =========================================================
# ADMIN TASDIQLASH / RAD ETISH
# =========================================================

@dp.callback_query(
    F.data.startswith("adm_")
)
async def admin_decision(
    callback: CallbackQuery,
    bot: Bot
):

    # ADMIN USERNAME BILAN TEKSHIRISH
    username = callback.from_user.username

    if username != ADMIN_USERNAME:

        await callback.answer(
            "❌ Ruxsat yo'q.",
            show_alert=True
        )

        return

    parts = callback.data.split("_")

    if len(parts) != 3:

        await callback.answer(
            "Xato.",
            show_alert=True
        )

        return

    action = parts[1]
    order_id = int(parts[2])

    order = db_get_order(
        order_id
    )

    if not order:

        await callback.answer(
            "Buyurtma topilmadi.",
            show_alert=True
        )

        return

    if order["status"] != "checking":

        await callback.answer(

            "Bu buyurtma allaqachon "
            "ko'rib chiqilgan.",

            show_alert=True
        )

        return

    if action == "ok":

        db_set_status(
            order_id,
            "paid"
        )

        await bot.send_message(

            order["user_id"],

            f"✅ <b>Buyurtma #{order_id} tasdiqlandi!</b>\n\n"

            f"🎮 {order['product']}\n"
            f"🆔 Player ID: "
            f"<code>{order['player_id']}</code>\n\n"

            "📦 Buyurtmangiz tez orada yetkazib beriladi.",

            parse_mode="HTML"
        )

        mark = "✅ TASDIQLANDI"

    else:

        db_set_status(
            order_id,
            "rejected"
        )

        await bot.send_message(

            order["user_id"],

            f"❌ <b>Buyurtma #{order_id} rad etildi.</b>\n\n"

            "To'lov topilmadi yoki chekda muammo bor.\n"
            "Xatolik bo'lsa admin bilan bog'laning.",

            parse_mode="HTML"
        )

        mark = "❌ RAD ETILDI"

    try:

        await callback.message.edit_caption(

            caption=(
                (callback.message.caption or "")
                + f"\n\n<b>{mark}</b>"
            ),

            parse_mode="HTML"
        )

    except TelegramBadRequest:
        pass

    await callback.answer(
        "Bajarildi ✅"
    )


# =========================================================
# TELEGRAM STARS MENYUSI
# =========================================================

@dp.callback_query(F.data == "stars")
async def stars(
    callback: CallbackQuery
):

    await safe_edit(

        callback,

        "⭐ <b>Telegram Stars</b>\n\n"

        "Telegram Stars orqali PUBG Mobile "
        "uchun to'lov qilishingiz mumkin.\n\n"

        "🎮 PUBG → paket → Player ID → "
        "⭐ Stars orqali to'lash.",

        back_button()
    )

    await callback.answer()


# =========================================================
# PREMIUM
# =========================================================

@dp.callback_query(F.data == "premium")
async def premium(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()

    builder.button(
        text="💎 3 oy — 182 000 so'm",
        callback_data="premium_3"
    )
    builder.button(
        text="💎 6 oy — 235 000 so'm",
        callback_data="premium_6"
    )
    builder.button(
        text="💎 12 oy — 405 000 so'm",
        callback_data="premium_12"
    )
    builder.button(
        text="🔙 Orqaga",
        callback_data="back"
    )

    builder.adjust(1)

    await safe_edit(
        callback,
        "💎 <b>Telegram Premium</b>\n\n"
        "Premium muddatini tanlang:",
        builder.as_markup()
    )

    await callback.answer()

@dp.callback_query(F.data.startswith("premium_"))
async def choose_premium(callback: CallbackQuery, state: FSMContext):
    duration = callback.data.replace("premium_", "")

    if duration not in PREMIUM_PRODUCTS:
        await callback.answer("Noto'g'ri tanlov!", show_alert=True)
        return

    product = PREMIUM_PRODUCTS[duration]

    await state.update_data(
        premium_duration=duration,
        premium_product=product["name"],
        premium_price=product["price"]
    )

    await state.set_state(PremiumFlow.waiting_username)

    await safe_edit(
        callback,
        f"💎 <b>{product['name']}</b>\n\n"
        "👤 Premium oladigan Telegram username'ni yuboring.\n\n"
        "Masalan: <code>@username</code>",
        back_button()
    )

    await callback.answer()

@dp.message(PremiumFlow.waiting_username, F.text)
async def receive_premium_username(message: Message, state: FSMContext):
    username = message.text.strip()

    if username.startswith("@"):
        username = username[1:]

    if not username or " " in username:
        await message.answer(
            "❌ Username noto'g'ri.\n\n"
            "Masalan: <code>@username</code>"
        )
        return

    data = await state.get_data()

    product = data["premium_product"]
    price = data["premium_price"]

    order_id = db_create_order(
        message.from_user.id,
        message.from_user.username,
        product,
        price,
        f"@{username}",
        "premium_card"
    )

    await state.update_data(
    order_id=order_id,
    premium_username=f"@{username}"
)
    await state.set_state(PremiumFlow.waiting_receipt)

    await message.answer(
        f"💎 {product}\n\n"
        f"👤 Username: @{username}\n"
        f"💰 Summa: {price:,} so'm\n\n"
        f"💳 To'lov uchun karta:\n"
        f"{CARD_NUMBER}\n"
        f"👤 Karta egasi: {CARD_OWNER}\n\n"
        "⚠️ Muhim:\n"
        "Faqat belgilangan summani o'tkazing.\n"
        "Agar kam bo'lsa admin tomonidan rad etiladi.\n\n"
        "⏰:10 daqiqa ichida chekni yuboring!\n"
        "10 daqiqa ichida chek yuborilmasa, "
        "to'lovingiz avtomatik rad etiladi.\n\n"
        "📸 Chekni shu botga yuboring."
    )
@dp.message(PremiumFlow.waiting_receipt, F.photo)
async def receive_premium_receipt(
    message: Message,
    state: FSMContext,
    bot: Bot
):
    data = await state.get_data()

    order_id = data.get("order_id")
    product = data.get("premium_product")
    price = data.get("premium_price")

    username = message.from_user.username
    file_id = message.photo[-1].file_id

    # Buyurtmaga chekni saqlash
    db_set_receipt(order_id, file_id)

    # Admin uchun xabar
    caption = (
        "💎 <b>YANGI TELEGRAM PREMIUM TO'LOV</b>\n\n"
        f"📦 Buyurtma: <b>#{order_id}</b>\n"
        f"👤 Mijoz: @{username or 'username yo‘q'}\n"
        f"💎 Mahsulot: <b>{product}</b>\n"
        f"👤 Premium username: <b>{data.get('premium_username', 'noma’lum')}</b>\n"
        f"💰 Summa: <b>{price:,} so'm</b>\n\n"
        "👇 To'lovni tekshiring:"
    )

    builder = InlineKeyboardBuilder()

    builder.button(
        text="✅ Tasdiqlash",
        callback_data=f"adm_ok_{order_id}"
    )
    builder.button(
        text="❌ Rad etish",
        callback_data=f"adm_no_{order_id}"
    )

    builder.adjust(2)

    await bot.send_photo(
        ADMIN_ID,
        file_id,
        caption=caption,
        reply_markup=builder.as_markup()
    )

    await state.clear()

    await message.answer(
        "✅ Chekingiz qabul qilindi!\n\n"
        "⏳ Admin to'lovni tekshirmoqda."
    )
# =========================================================
# BUYURTMALAR
# =========================================================

@dp.callback_query(F.data == "orders")
async def orders_list(
    callback: CallbackQuery
):

    rows = db_user_orders(
        callback.from_user.id
    )

    if not rows:

        text = (
            "📦 <b>Buyurtmalarim</b>\n\n"
            "Hali buyurtmalaringiz yo'q."
        )

    else:

        lines = [
            "📦 <b>Buyurtmalarim</b>\n"
        ]

        for row in rows:

            payment = row["payment_method"]

            if payment == "telegram_stars":
                payment_text = "⭐ Stars"
            else:
                payment_text = "💳 Karta"

            lines.append(

                f"#{row['id']} — "
                f"{row['product']}\n"

                f"   {fmt(row['price'])} so'm | "
                f"{payment_text}\n"

                f"   {STATUS_TEXT.get(row['status'], row['status'])}\n"
            )

        text = "\n".join(lines)

    await safe_edit(

        callback,

        text,

        back_button()
    )

    await callback.answer()


# =========================================================
# YORDAM
# =========================================================

@dp.callback_query(F.data == "help")
async def help_command(
    callback: CallbackQuery
):

    await safe_edit(

        callback,

        "📞 <b>Yordam</b>\n\n"

        "Muammo bo'lsa administrator bilan "
        "bog'laning:\n"
        "@kasimov70",

        back_button()
    )

    await callback.answer()


# =========================================================
# ISHLAMAYOTGAN PAKET
# =========================================================

@dp.callback_query(F.data == "soon")
async def soon(
    callback: CallbackQuery
):

    await callback.answer(

        "Bu paket hozircha mavjud emas.",

        show_alert=True
    )


# =========================================================
# MAIN
# =========================================================

async def main():

    from aiohttp import web

    db_init()

    bot = Bot(
        token=TOKEN
    )

    async def health(request):
        return web.Response(text="Kasimov TopUp bot ishlayapti!")

    app = web.Application()
    app.router.add_get("/", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "10000"))

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    print("Kasimov TopUp bot ishga tushdi!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

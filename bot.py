import logging
import os
import json
import gspread
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from google.oauth2.service_account import Credentials
from datetime import datetime
from config import BOT_TOKEN, SPREADSHEET_ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

user_carts: dict = {}

MANAGER_LINK = "https://t.me/addservice0910"
MANAGER_USERNAME = "@addservice0910"

class OrderState(StatesGroup):
    waiting_name = State()
    waiting_phone = State()

def get_google_client():
    creds_json = os.getenv("GOOGLE_CREDENTIALS") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def fetch_products() -> list:
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        rows = sheet.get_all_records()
        if rows:
            logger.info(f"ЗАГОЛОВКИ: {list(rows[0].keys())}")
        if not rows:
            logger.warning("Таблица пуста!")
            return []
        result = []
        for r in rows:
            clean = {str(k).strip(): str(v).strip() for k, v in r.items()}
            if clean.get("Активен", "").lower().strip() == "да":
                result.append(clean)
        logger.info(f"Активных товаров: {len(result)}")
        return result
    except Exception as e:
        logger.error(f"Ошибка чтения таблицы: {e}")
        return []

def save_order(user_id, username, full_name, phone, cart) -> bool:
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Заказы")
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        for item in cart:
            sheet.append_row([
                date_str,
                str(user_id),
                f"@{username}" if username else "",
                full_name,
                phone,
                item["name"],
                item["qty"],
                item["price"],
                item["price"] * item["qty"]
            ])
        return True
    except Exception as e:
        logger.error(f"Ошибка записи заказа: {e}")
        return False

def get_cat_key(products: list) -> str:
    if not products:
        return "Категория"
    for key in products[0].keys():
        if "катег" in key.lower() or "categ" in key.lower() or "kategor" in key.lower():
            return key
    return "Категория"

def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍯 Mahsulotlar / Товары")],
            [KeyboardButton(text="🛒 Savatcha / Корзина"),
             KeyboardButton(text="📞 Kontaktlar / Контакты")],
        ],
        resize_keyboard=True,
    )

def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Raqamni yuborish / Отправить номер", request_contact=True)],
            [KeyboardButton(text="❌ Bekor / Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

def product_kb(name: str, vol: str, qty: int, category: str):
    kg_label = "✅ 1 kg" if vol == "kg" else "1 kg"
    l_label = "✅ 1 l" if vol == "l" else "1 l"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=kg_label, callback_data=f"pv|{name}|kg|{qty}|{category}"),
            InlineKeyboardButton(text=l_label, callback_data=f"pv|{name}|l|{qty}|{category}"),
        ],
        [
            InlineKeyboardButton(text="➖", callback_data=f"pv|{name}|{vol}|{max(1, qty - 1)}|{category}"),
            InlineKeyboardButton(text=f"  {qty}  ", callback_data="noop"),
            InlineKeyboardButton(text="➕", callback_data=f"pv|{name}|{vol}|{qty + 1}|{category}"),
        ],
        [InlineKeyboardButton(text="🛒 Savatga / В корзину", callback_data=f"add|{name}|{vol}|{qty}|{category}")],
        [InlineKeyboardButton(text="⬅️ Ortga / Назад", callback_data=f"cat|{category}")],
    ])

def product_text(p: dict, vol: str, qty: int) -> str:
    price_kg = int(p.get("Цена_КГ", 0))
    price_l = int(p.get("Цена_Литр", 0))
    price = price_l if vol == "l" else price_kg
    vol_label = "1 l" if vol == "l" else "1 kg"
    total = price * qty
    return (
        f"🍯 *{p['Название']}*\n\n"
        f"{p.get('Описание', '')}\n\n"
        f"💰 *Barcha narxlar / Все цены:*\n"
        f"  ⚖️ 1 kg — {price_kg:,} so'm\n"
        f"  💧 1 l  — {price_l:,} so'm\n\n"
        f"📍 *Tanlangan / Выбрано:* {qty} × {vol_label} = *{total:,} so'm*"
    )

@dp.message(CommandStart())
async def cmd_start(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer(
        "🍯 *Asal_shifo* botiga xush kelibsiz!\n"
        "Добро пожаловать в бот *Asal_shifo*!\n\n"
        "Kerakli bo'limni tanlang / Выберите нужный раздел:",
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )

@dp.message(F.text == "🍯 Mahsulotlar / Товары")
async def show_categories(m: types.Message):
    products = await asyncio.to_thread(fetch_products)
    if not products:
        await m.answer("❌ Mahsulotlar topilmadi. / Товары не найдены.")
        return
    cat_key = get_cat_key(products)
    cats = sorted({p[cat_key] for p in products if p.get(cat_key)})
    if not cats:
        await m.answer("❌ Kategoriyalar topilmadi. / Категории не найдены.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c, callback_data=f"cat|{c}")] for c in cats
    ])
    await m.answer(
        "📦 *Kategoriyani tanlang / Выберите категорию:*",
        reply_markup=kb, parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("cat|"))
async def show_products_in_cat(call: types.CallbackQuery):
    cat = call.data.split("|", 1)[1]
    products = await asyncio.to_thread(fetch_products)
    cat_key = get_cat_key(products)
    items = [p for p in products if p.get(cat_key) == cat]
    if not items:
        await call.answer("Mahsulotlar topilmadi. / Товары не найдены.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=p["Название"], callback_data=f"pv|{p['Название']}|l|1|{cat}")]
        for p in items
    ] + [[InlineKeyboardButton(text="⬅️ Kategoriyalar / Категории", callback_data="cats")]])
    await call.message.edit_text(
        f"🛍 *{cat}* — mahsulotni tanlang / выберите товар:",
        reply_markup=kb, parse_mode="Markdown"
    )

@dp.callback_query(F.data == "cats")
async def back_to_cats(call: types.CallbackQuery):
    products = await asyncio.to_thread(fetch_products)
    cat_key = get_cat_key(products)
    cats = sorted({p[cat_key] for p in products if p.get(cat_key)})
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c, callback_data=f"cat|{c}")] for c in cats
    ])
    await call.message.edit_text(
        "📦 *Kategoriyani tanlang / Выберите категорию:*",
        reply_markup=kb, parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("pv|"))
async def product_view(call: types.CallbackQuery):
    _, name, vol, qty_s, category = call.data.split("|")
    qty = int(qty_s)
    products = await asyncio.to_thread(fetch_products)
    p = next((x for x in products if x["Название"] == name), None)
    if not p:
        await call.answer("Mahsulot topilmadi. / Товар не найден.", show_alert=True)
        return
    text = product_text(p, vol, qty)
    kb = product_kb(name, vol, qty, category)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass
    await call.answer()

@dp.callback_query(F.data.startswith("add|"))
async def add_to_cart(call: types.CallbackQuery):
    _, name, vol, qty_s, category = call.data.split("|")
    qty = int(qty_s)
    products = await asyncio.to_thread(fetch_products)
    p = next((x for x in products if x["Название"] == name), None)
    if not p:
        await call.answer("Xatolik. / Ошибка.", show_alert=True)
        return
    price = int(p.get("Цена_Литр", 0)) if vol == "l" else int(p.get("Цена_КГ", 0))
    vol_label = "1 l" if vol == "l" else "1 kg"
    item_key = f"{name} ({vol_label})"
    cart = user_carts.setdefault(call.from_user.id, [])
    for item in cart:
        if item["name"] == item_key:
            item["qty"] += qty
            await call.answer(f"✅ {item_key} yangilandi! / обновлено! (+{qty})")
            return
    cart.append({"name": item_key, "qty": qty, "price": price})
    await call.answer(f"✅ {item_key} × {qty} — savatga qo'shildi! / добавлено в корзину!")

@dp.callback_query(F.data == "noop")
async def noop(call: types.CallbackQuery):
    await call.answer()

@dp.message(F.text == "🛒 Savatcha / Корзина")
async def show_cart(m: types.Message):
    cart = user_carts.get(m.from_user.id, [])
    if not cart:
        await m.answer("🛒 Savatcha bo'sh. / Корзина пуста.")
        return
    lines = [f"• {i['name']} × {i['qty']} = {i['price'] * i['qty']:,} so'm" for i in cart]
    total = sum(i["price"] * i["qty"] for i in cart)
    text = "🛒 *Savatcha / Корзина:*\n\n" + "\n".join(lines) + f"\n\n💰 *Jami / Итого: {total:,} so'm*"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Buyurtma berish / Оформить заказ", callback_data="checkout")],
        [InlineKeyboardButton(text="🗑 Tozalash / Очистить корзину", callback_data="clear_cart")],
    ])
    await m.answer(text, parse_mode="Markdown", reply_markup=kb)

@dp.callback_query(F.data == "clear_cart")
async def clear_cart(call: types.CallbackQuery):
    user_carts[call.from_user.id] = []
    await call.answer("🗑 Savatcha tozalandi. / Корзина очищена.")
    await call.message.edit_text("🛒 Savatcha bo'sh. / Корзина пуста.")

@dp.callback_query(F.data == "checkout")
async def checkout_start(call: types.CallbackQuery, state: FSMContext):
    cart = user_carts.get(call.from_user.id, [])
    if not cart:
        await call.answer("Savatcha bo'sh. / Корзина пуста.", show_alert=True)
        return
    await call.answer()
    await state.set_state(OrderState.waiting_name)
    await call.message.answer(
        "📝 Ismingizni kiriting / Введите ваше имя:\n_(Masalan: Rustam Karimov)_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

@dp.message(OrderState.waiting_name)
async def process_name(m: types.Message, state: FSMContext):
    await state.update_data(full_name=m.text.strip())
    await state.set_state(OrderState.waiting_phone)
    await m.answer(
        "📱 Telefon raqamingizni yuboring / Отправьте номер телефона:",
        reply_markup=phone_kb(),
    )

@dp.message(OrderState.waiting_phone, F.contact)
async def process_phone_contact(m: types.Message, state: FSMContext):
    await _finalize(m, state, m.contact.phone_number)

@dp.message(OrderState.waiting_phone, F.text)
async def process_phone_text(m: types.Message, state: FSMContext):
    if m.text == "❌ Bekor / Отмена":
        await state.clear()
        await m.answer("Buyurtma bekor qilindi. / Заказ отменён.", reply_markup=main_kb())
        return
    await _finalize(m, state, m.text.strip())

async def _finalize(m: types.Message, state: FSMContext, phone: str):
    data = await state.get_data()
    full_name = data.get("full_name", m.from_user.full_name or "")
    cart = user_carts.get(m.from_user.id, [])
    await m.answer("⏳ Buyurtma saqlanmoqda... / Сохраняем заказ...", reply_markup=ReplyKeyboardRemove())
    ok = await asyncio.to_thread(save_order, m.from_user.id, m.from_user.username or "", full_name, phone, cart)
    await state.clear()
    if ok:
        lines = "\n".join(f"• {i['name']} × {i['qty']} = {i['price'] * i['qty']:,} so'm" for i in cart)
        total = sum(i["price"] * i["qty"] for i in cart)
        user_carts[m.from_user.id] = []
        await m.answer(
            f"✅ *Buyurtmangiz qabul qilindi! / Ваш заказ принят!*\n\n"
            f"{lines}\n\n💰 *Jami / Итого: {total:,} so'm*\n\n"
            f"📱 {phone}\n👤 {full_name}\n\n"
            f"Tez orada siz bilan bog'lanamiz.\nМы свяжемся с вами в ближайшее время. 🙏",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )
    else:
        await m.answer(
            "❌ Xatolik yuz berdi. Qayta urinib ko'ring. / Произошла ошибка. Попробуйте снова.",
            reply_markup=main_kb()
        )

@dp.message(F.text == "📞 Kontaktlar / Контакты")
async def show_contacts(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Menejer / Менеджер", url=MANAGER_LINK)]
    ])
    await m.answer(
        f"📞 *Aloqa ma'lumotlari / Контакты:*\n\n"
        f"👤 Menejer: {MANAGER_USERNAME}",
        parse_mode="Markdown",
        reply_markup=kb,
    )

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main()

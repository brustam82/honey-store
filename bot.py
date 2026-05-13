import logging
import asyncio
import time
import json
import os
import gspread
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder
from google.oauth2.service_account import Credentials
from config import BOT_TOKEN, SPREADSHEET_ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
user_carts: dict = {}
_cache: dict = {"products": [], "ts": 0}

CONTACT_PHONE = "+998 90 XXX XX XX"
MANAGER_USERNAME = "@addservice0910"
MANAGER_LINK = "https://t.me/addservice0910"

class OrderState(StatesGroup):
    waiting_name = State()
    waiting_phone = State()

def get_google_client():
    creds_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'])
    return gspread.authorize(creds)

def _fetch_products() -> list:
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        rows = sheet.get_all_records()
        return [{str(k).strip(): str(v).strip() for k, v in r.items()} for r in rows if str(r.get("Активен", "")).lower() in ("да", "yes", "1", "true")]
    except Exception as e:
        logger.error(f"Ошибка: {e}"); return []

def _save_order(user_id, username, full_name, phone, cart) -> bool:
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Заказы")
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        for item in cart:
            sheet.append_row([date_str, str(user_id), f"@{username}" if username else "", full_name, phone, item["name"], item["qty"], item["price"], item["price"] * item["qty"]])
        return True
    except Exception as e:
        logger.error(f"Ошибка: {e}"); return False

async def get_products():
    if not _cache["products"] or time.time() - _cache["ts"] > 300:
        products = await asyncio.to_thread(_fetch_products)
        if products: _cache["products"] = products; _cache["ts"] = time.time()
    return _cache["products"]

def parse_prices(price_str):
    variants = []
    for part in str(price_str).split(","):
        if ":" in part:
            u, p = part.split(":", 1)
            variants.append({"unit": u.strip(), "price": float(p.replace(" ", ""))})
        else:
            variants.append({"unit": "ед.", "price": float(part.replace(" ", ""))})
    return variants or [{"unit": "ед.", "price": 0.0}]

def main_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🍯 Mahsulotlar ro'yhati / Перечень продукции")], [KeyboardButton(text="🛒 Savatcha / Корзина")], [KeyboardButton(text="📞 Aloqa ma'lumotlari / Контакты")]], resize_keyboard=True)

def product_kb(p_idx, variants, v_idx=0, qty=1):
    builder = InlineKeyboardBuilder()
    for i, v in enumerate(variants):
        builder.button(text=f"✅ {v['unit']}" if i == v_idx else v['unit'], callback_data=f"v:{p_idx}:{i}:{qty}")
    builder.button(text="➖", callback_data=f"q:{p_idx}:{v_idx}:{max(1, qty - 1)}")
    builder.button(text=f"  {qty}  ", callback_data="noop")
    builder.button(text="➕", callback_data=f"q:{p_idx}:{v_idx}:{qty + 1}")
    builder.button(text="🛒 Savatga / В корзину", callback_data=f"add:{p_idx}:{v_idx}:{qty}")
    builder.button(text="🔙 Ortga / Назад", callback_data="to_cats")
    builder.adjust(len(variants), 3, 1, 1)
    return builder.as_markup()

@dp.message(CommandStart())
async def cmd_start(m: types.Message, state: FSMContext):
    await state.clear(); await m.answer("Xush kelibsiz! / Добро пожаловать!", reply_markup=main_kb())

@dp.message(F.text == "🍯 Mahsulotlar ro'yhati / Перечень продукции")
async def show_cats(m: types.Message):
    products = await get_products()
    cats = sorted({p["Категория"] for p in products if p.get("Категория")})
    builder = InlineKeyboardBuilder()
    for cat in cats: builder.button(text=cat, callback_data=f"cat:{cat[:25]}")
    builder.adjust(2); await m.answer("Выберите категорию:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("cat:"))
async def list_products(cb: types.CallbackQuery):
    cat = cb.data.split(":")[1]
    products = await get_products()
    builder = InlineKeyboardBuilder()
    for i, p in enumerate(products):
        if p.get("Категория", "").startswith(cat): builder.button(text=p["Название"], callback_data=f"p:{i}")
    builder.button(text="🔙 Назад", callback_data="to_cats"); builder.adjust(1)
    await cb.message.edit_text("Выберите товар:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("p:"))
async def show_product(cb: types.CallbackQuery):
    p_idx = int(cb.data.split(":")[1])
    p = (await get_products())[p_idx]
    variants = parse_prices(p["Цена"])
    kb = product_kb(p_idx, variants)
    await cb.message.edit_text(f"*{p['Название']}*\n{p.get('Описание', '')}", parse_mode="Markdown", reply_markup=kb)

@dp.callback_query(F.data.startswith("add:"))
async def add_to_cart(cb: types.CallbackQuery):
    parts = cb.data.split(":")
    p = (await get_products())[int(parts[1])]
    variant = parse_prices(p["Цена"])[int(parts[2])]
    cart = user_carts.setdefault(cb.from_user.id, [])
    cart.append({"name": f"{p['Название']} ({variant['unit']})", "price": variant["price"], "qty": int(parts[3])})
    await cb.answer("✅ Добавлено в корзину!")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

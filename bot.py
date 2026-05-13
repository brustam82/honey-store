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
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from google.oauth2.service_account import Credentials
from config import BOT_TOKEN, SPREADSHEET_ID

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
user_carts: dict = {}
_cache: dict = {"products": [], "ts": 0}

def get_google_client():
    creds_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'])
    return gspread.authorize(creds)

def _fetch_products() -> list:
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        rows = sheet.get_all_records()
        logger.info(f"DEBUG: Получено строк из таблицы: {len(rows)}")
        
        products = []
        for r in rows:
            # Очистка ключей и значений от лишних пробелов
            clean_row = {str(k).strip(): str(v).strip() for k, v in r.items()}
            # Проверка статуса (регистронезависимо)
            status = clean_row.get("Активен", "").lower()
            if status in ("да", "yes", "1", "true"):
                products.append(clean_row)
        
        logger.info(f"DEBUG: Активных товаров найдено: {len(products)}")
        return products
    except Exception as e:
        logger.error(f"ОШИБКА при чтении таблицы: {e}")
        return []

async def get_products():
    if not _cache["products"] or time.time() - _cache["ts"] > 300:
        products = await asyncio.to_thread(_fetch_products)
        if products: 
            _cache["products"] = products
            _cache["ts"] = time.time()
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
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🍯 Mahsulotlar ro'yhati / Перечень продукции")], 
        [KeyboardButton(text="🛒 Savatcha / Корзина")], 
        [KeyboardButton(text="📞 Aloqa ma'lumotlari / Контакты")]
    ], resize_keyboard=True)

@dp.message(CommandStart())
async def cmd_start(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer("Xush kelibsiz! / Добро пожаловать!", reply_markup=main_kb())

@dp.message(F.text == "🍯 Mahsulotlar ro'yhati / Перечень продукции")
async def show_cats(m: types.Message):
    products = await get_products()
    if not products:
        await m.answer("Товары пока не найдены или возникла ошибка при подключении к таблице.")
        return
    
    cats = sorted({p["Категория"] for p in products if p.get("Категория")})
    builder = InlineKeyboardBuilder()
    for cat in cats: 
        builder.button(text=cat, callback_data=f"cat:{cat[:20]}")
    builder.adjust(2)
    await m.answer("Выберите категорию:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("cat:"))
async def list_products(

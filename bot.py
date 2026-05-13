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

# ── Логирование ──────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Инициализация ────────────────────────────────────────────────────────────
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

# ── Google Sheets (Адаптировано для Railway) ──────────────────────────────────
def get_google_client():
    creds_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
    creds = Credentials.from_service_account_info(
        creds_dict, 
        scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    )
    return gspread.authorize(creds)

def _fetch_products() -> list:
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        rows = sheet.get_all_records()
        result = [ {str(k).strip(): str(v).strip() for k, v in r.items()} for r in rows 
                   if str(r.get("Активен", "")).lower() in ("да", "yes", "1", "true") ]
        return result
    except Exception as e:
        logger.error(f"Ошибка чтения таблицы: {e}")
        return []

def _save_order(user_id: int, username: str, full_name: str, phone: str, cart: list) -> bool:
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Заказы")
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        for item in cart:
            sheet.append_row([date_str, str(user_id), f"@{username}" if username else "", 
                              full_name, phone, item["name"], item["qty"], item["price"], 
                              item["price"] * item["qty"]])
        return True
    except Exception as e:
        logger.error(f"Ошибка записи заказа: {e}")
        return False

async def get_products() -> list:
    if not _cache["products"] or time.time() - _cache["ts"] > 300:
        products = await asyncio.to_thread(_fetch_products)
        if products:
            _cache["products"] = products
            _cache["ts"] = time.time()
    return _cache["products"]

# ── ОСТАЛЬНАЯ ВАША ЛОГИКА (БЕЗ ИЗМЕНЕНИЙ) ────────────────────────────────────
# ВАЖНО: Весь ваш старый код (клавиатуры, parse_prices, хэндлеры) 
# нужно просто вставить ниже этой строки, если вы его еще не вставили.
# Если вы скопировали код выше — он заменит всё, что было раньше.

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

# ── Логи ─────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Инициализация (ОБЯЗАТЕЛЬНО ДО @dp) ───────────────────────────────────────
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ── Корзины пользователей ─────────────────────────────────────────────────────
user_carts: dict = {}

# ── Контакты магазина ─────────────────────────────────────────────────────────
MANAGER_LINK = "https://t.me/addservice0910"
MANAGER_USERNAME = "@addservice0910"

# ── FSM: оформление заказа ───────────────────────────────────────────────────
class OrderState(StatesGroup):
    waiting_name = State()
    waiting_phone = State()

# ── Google Sheets ─────────────────────────────────────────────────────────────
def get_google_client():
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
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
            logger.info(f"ЗАГОЛОВКИ ТАБЛИЦЫ: {list(rows[0].keys())}")
            logger.info(f"ПЕРВАЯ СТРОКА: {rows[0]}")
        else:

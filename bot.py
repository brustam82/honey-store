import logging
import asyncio
import json
import os
import gspread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from google.oauth2.service_account import Credentials
from config import BOT_TOKEN, SPREADSHEET_ID

# Инициализация
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Настройка Google Sheets
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

def get_google_client():
    creds_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

# Функция получения данных
def fetch_products():
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        return sheet.get_all_records()
    except Exception as e:
        logging.error(f"Ошибка при чтении таблицы: {e}")
        return []

# --- ОСТАЛЬНОЙ ВАШ КОД БОТА НИЖЕ ---
# (Вставьте сюда ваш остальной код с логикой кнопок и хэндлеров)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

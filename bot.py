import logging
import asyncio
import json
import os
import gspread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from google.oauth2.service_account import Credentials
from config import BOT_TOKEN, SPREADSHEET_ID

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Функция авторизации через google-auth
def get_google_client():
    try:
        creds_json = os.getenv("GOOGLE_CREDENTIALS")
        if not creds_json:
            raise ValueError("Переменная GOOGLE_CREDENTIALS не найдена")
        
        creds_dict = json.loads(creds_json)
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Ошибка авторизации Google: {e}")
        return None

# Функция получения данных
def fetch_products():
    client = get_google_client()
    if not client: return []
    try:
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        return sheet.get_all_records()
    except Exception as e:
        logger.error(f"Ошибка при чтении таблицы: {e}")
        return []

# --- ОСТАЛЬНОЙ ВАШ КОД БОТА НИЖЕ ---
# Сюда можно вставить вашу логику кнопок и обработчиков (хэндлеров)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("Бот запущен и готов к работе!")

async def main():
    # Удаляем вебхуки, чтобы использовать polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

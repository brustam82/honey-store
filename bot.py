import logging
import asyncio
import json
import os
import gspread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from google.oauth2.service_account import Credentials
from config import BOT_TOKEN, SPREADSHEET_ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def fetch_debug():
    try:
        creds_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
        creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        data = sheet.get_all_records()
        return f"УСПЕХ! Найдено строк: {len(data)}. Данные: {str(data)[:200]}"
    except Exception as e:
        return f"ОШИБКА: {str(e)}"

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    debug_info = fetch_debug()
    await message.answer(f"Диагностика:\n{debug_info}")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

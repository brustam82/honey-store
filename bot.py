import logging
import asyncio
import json
import os
import gspread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from google.oauth2.service_account import Credentials
from config import BOT_TOKEN, SPREADSHEET_ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- Настройка Google Sheets ---
def get_google_client():
    creds_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def fetch_products():
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        data = sheet.get_all_records()
        # Фильтруем только активные товары
        return [row for row in data if str(row.get("Активен", "")).lower() == "да"]
    except Exception as e:
        logger.error(f"Ошибка чтения таблицы: {e}")
        return []

# --- Интерфейс ---
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🍯 Mahsulotlar ro'yhati / Перечень продукции")],
        [KeyboardButton(text="🛒 Savatcha / Корзина")],
        [KeyboardButton(text="📞 Aloqa ma'lumotlari / Контакты")]
    ], resize_keyboard=True)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("Xush kelibsiz! / Добро пожаловать!", reply_markup=main_kb())

@dp.message(F.text == "🍯 Mahsulotlar ro'yhati / Перечень продукции")
async def show_categories(message: types.Message):
    products = fetch_products()
    if not products:
        await message.answer("Товары не найдены.")
        return
    
    categories = sorted({p["Категория"] for p in products if p.get("Категория")})
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat, callback_data=f"cat_{cat}")
    builder.adjust(1)
    await message.answer("Выберите категорию:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def show_products_in_cat(callback: types.CallbackQuery):
    cat = callback.data.split("_")[1]
    products = [p for p in fetch_products() if p.get("Категория") == cat]
    
    builder = InlineKeyboardBuilder()
    for p in products:
        builder.button(text=p["Название"], callback_data=f"prod_{p['Название']}")
    await callback.message.edit_text(f"Товары в категории {cat}:", reply_markup=builder.as_markup())

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

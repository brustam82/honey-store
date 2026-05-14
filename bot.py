import logging
import os
import json
import gspread
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from google.oauth2.service_account import Credentials
from config import BOT_TOKEN, SPREADSHEET_ID

logging.basicConfig(level=logging.INFO)

def get_google_client():
    # Берем данные из переменной окружения в Railway
    creds_json = os.getenv('GOOGLE_CREDENTIALS')
    if not creds_json:
        raise ValueError("Ошибка: Переменная GOOGLE_CREDENTIALS не задана!")
    
    creds_dict = json.loads(creds_json)
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def fetch_products():
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        return [r for r in sheet.get_all_records() if str(r.get("Активен", "")).lower() == "да"]
    except Exception as e:
        logging.error(f"Ошибка таблицы: {e}")
        return []

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🍯 Mahsulotlar / Товары")]], resize_keyboard=True)
    await m.answer("Asal_shifo botiga xush kelibsiz!", reply_markup=kb)

@dp.message(F.text == "🍯 Mahsulotlar / Товары")
async def show_categories(m: types.Message):
    products = fetch_products()
    categories = list(set([p['Категория'] for p in products if p.get('Категория')]))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c, callback_data=f"cat_{c}")] for c in categories])
    await m.answer("Выберите категорию:", reply_markup=kb)

@dp.callback_query(F.data.startswith("cat_"))
async def show_products(call: types.CallbackQuery):
    cat = call.data.split("_", 1)[1]
    products = [p for p in fetch_products() if p.get('Категория') == cat]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=p['Название'], callback_data=f"p_{p['Название']}")] for p in products])
    await call.message.answer(f"Товары в категории {cat}:", reply_markup=kb)

@dp.callback_query(F.data.startswith("p_"))
async def product_detail(call: types.CallbackQuery):
    name = call.data.split("_", 1)[1]
    p = next((item for item in fetch_products() if item['Название'] == name), None)
    if not p: return
    text = f"*{p['Название']}*\n\n{p.get('Описание', '')}\n\n⚖️ 1 кг: {p.get('Цена_КГ', 0)} сум\n💧 1 л: {p.get('Цена_Литр', 0)} сум"
    await call.message.answer(text, parse_mode="Markdown")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

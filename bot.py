import logging
import json
import gspread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from google.oauth2.service_account import Credentials
from config import BOT_TOKEN, SPREADSHEET_ID

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_google_client():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file('google_creds.json', scopes=scopes)
    return gspread.authorize(creds)

def fetch_products():
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        return [r for r in sheet.get_all_records() if str(r.get("Активен", "")).lower() == "да"]
    except Exception as e:
        logging.error(f"Error: {e}")
        return []

@dp.message(F.text == "🍯 Mahsulotlar / Товары")
async def show_categories(m: types.Message):
    products = fetch_products()
    categories = list(set([p['Категория'] for p in products]))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c, callback_data=f"cat_{c}")] for c in categories])
    await m.answer("Выберите категорию / Kategoriyani tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("cat_"))
async def show_products_by_cat(call: types.CallbackQuery):
    cat = call.data.split("_")[1]
    products = [p for p in fetch_products() if p['Категория'] == cat]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=p['Название'], callback_data=f"p_{p['Название']}")] for p in products])
    await call.message.answer(f"Товары в категории {cat}:", reply_markup=kb)

@dp.callback_query(F.data.startswith("p_"))
async def product_card(call: types.CallbackQuery):
    name = call.data.split("_", 1)[1]
    p = next((item for item in fetch_products() if item['Название'] == name), None)
    if not p: return

    desc = p.get('Описание', '...')
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⚖️ 1 kg: {p['Цена_КГ']} so'm", callback_data=f"buy_{name}_kg")],
        [InlineKeyboardButton(text=f"💧 1 l: {p['Цена_Питр']} so'm", callback_data=f"buy_{name}_l")]
    ])
    await call.message.answer(f"*{p['Название']}*\n\n{desc}", parse_mode="Markdown", reply_markup=kb)

# ... (остальной код для старта и кнопок)

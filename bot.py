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

# Настройка логов
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Функция авторизации
def get_google_client():
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

# Обработчики с улучшенным интерфейсом
@dp.message(CommandStart())
async def start(m: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🍯 Mahsulotlar / Товары")]], resize_keyboard=True)
    await m.answer("Asal_shifo botiga xush kelibsiz!", reply_markup=kb)

@dp.message(F.text == "🍯 Mahsulotlar / Товары")
async def show_categories(m: types.Message):
    products = fetch_products()
    categories = list(set([p['Категория'] for p in products if p.get('Категория')]))
    buttons = [[InlineKeyboardButton(text=c, callback_data=f"cat_{c}")] for c in categories]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await m.answer("📦 *Tanlang / Выберите категорию:*", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def show_products(call: types.CallbackQuery):
    cat = call.data.split("_", 1)[1]
    products = [p for p in fetch_products() if p.get('Категория') == cat]
    buttons = [[InlineKeyboardButton(text=p['Название'], callback_data=f"p_{p['Название']}")] for p in products]
    buttons.append([InlineKeyboardButton(text="⬅️ Ortga / Назад", callback_data="back_to_cats")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.edit_text(f"🛍 *{cat} bo'limidagi mahsulotlar / Товары в категории {cat}:*", 
                                 reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "back_to_cats")
async def back_to_categories(call: types.CallbackQuery):
    products = fetch_products()
    categories = list(set([p['Категория'] for p in products if p.get('Категория')]))
    buttons = [[InlineKeyboardButton(text=c, callback_data=f"cat_{c}")] for c in categories]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.edit_text("📦 *Tanlang / Выберите категорию:*", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("p_"))
async def product_detail(call: types.CallbackQuery):
    name = call.data.split("_", 1)[1]
    p = next((item for item in fetch_products() if item['Название'] == name), None)
    if not p: return
    text = (f"🍯 *{p['Название']}*\n\n"
            f"📝 {p.get('Описание', '')}\n\n"
            f"💰 *Narxlar / Цены:*\n"
            f"⚖️ 1 kg: {p.get('Цена_КГ', 0)} sum\n"
            f"💧 1 l: {p.get('Цена_Литр', 0)} sum")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Ortga / Назад", callback_data=f"cat_{p['Категория']}") ]])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

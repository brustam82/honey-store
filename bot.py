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
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_google_client():
    creds_json = os.getenv('GOOGLE_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def fetch_products():
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        return [r for r in sheet.get_all_records() if str(r.get("Активен", "")).lower() == "да"]
    except Exception: return []

# Стартовое меню
@dp.message(CommandStart())
async def start(m: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🍯 Mahsulotlar / Товары")]], resize_keyboard=True)
    await m.answer("Asal_shifo botiga xush kelibsiz!", reply_markup=kb)

# Список категорий
@dp.message(F.text == "🍯 Mahsulotlar / Товары")
async def show_categories(m: types.Message):
    products = fetch_products()
    categories = list(set([p['Категория'] for p in products if p.get('Категория')]))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c, callback_data=f"cat_{c}")] for c in categories])
    await m.answer("📦 *Tanlang / Выберите категорию:*", reply_markup=kb, parse_mode="Markdown")

# Список товаров
@dp.callback_query(F.data.startswith("cat_"))
async def show_products(call: types.CallbackQuery):
    cat = call.data.split("_", 1)[1]
    products = [p for p in fetch_products() if p.get('Категория') == cat]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=p['Название'], callback_data=f"p_{p['Название']}_1л_1")] for p in products] + [[InlineKeyboardButton(text="⬅️ Ortga / Назад", callback_data="back_main")]])
    await call.message.edit_text(f"🛍 *{cat}:*", reply_markup=kb, parse_mode="Markdown")

# ИНТЕРАКТИВНАЯ КАРТОЧКА ТОВАРА
@dp.callback_query(F.data.startswith("p_"))
async def product_detail(call: types.CallbackQuery):
    _, name, vol, count = call.data.split("_")
    count = int(count)
    p = next((item for item in fetch_products() if item['Название'] == name), None)
    if not p: return

    price = p.get('Цена_Литр') if vol == "1л" else p.get('Цена_КГ')
    text = f"🍯 *{p['Название']}*\n\n{p.get('Описание', '')}\n\n💰 *Narx / Цена:* {price * count} so'm\n\n📍 *Tanlangan / Выбрано:* {count} x {vol}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1кг" if vol=="1л" else "✅ 1кг", callback_data=f"p_{name}_1кг_{count}"), 
         InlineKeyboardButton(text="✅ 1л" if vol=="1кг" else "1л", callback_data=f"p_{name}_1л_{count}")],
        [InlineKeyboardButton(text="➖", callback_data=f"p_{name}_{vol}_{max(1, count-1)}"), 
         InlineKeyboardButton(text=str(count), callback_data="ignore"), 
         InlineKeyboardButton(text="➕", callback_data=f"p_{name}_{vol}_{count+1}")],
        [InlineKeyboardButton(text="🛒 Savatga / В корзину", callback_data="add_to_cart")],
        [InlineKeyboardButton(text="⬅️ Ortga / Назад", callback_data=f"cat_{p['Категория']}")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "back_main")
async def back_main(call: types.CallbackQuery):
    await show_categories(call.message)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

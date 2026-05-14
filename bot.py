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

# 1. ПРАВИЛЬНЫЙ ПОРЯДОК ИНИЦИАЛИЗАЦИИ
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher() # Переменная dp создана здесь, теперь ошибки "not defined" не будет

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
    except Exception as e:
        logging.error(f"Ошибка таблицы: {e}")
        return []

# 2. ОБРАБОТЧИКИ
@dp.message(CommandStart())
async def start(m: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🍯 Mahsulotlar / Товары")]], resize_keyboard=True)
    await m.answer("Asal_shifo botiga xush kelibsiz!", reply_markup=kb)

@dp.message(F.text == "🍯 Mahsulotlar / Товары")
async def show_categories(m: types.Message):
    products = fetch_products()
    categories = list(set([p['Категория'] for p in products if p.get('Категория')]))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c, callback_data=f"cat_{c}")] for c in categories])
    await m.answer("📦 *Tanlang / Выберите категорию:*", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def show_products(call: types.CallbackQuery):
    cat = call.data.split("_", 1)[1]
    products = [p for p in fetch_products() if p.get('Категория') == cat]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=p['Название'], callback_data=f"p_{p['Название']}_1л_1")] for p in products
    ] + [[InlineKeyboardButton(text="⬅️ Ortga / Назад", callback_data="back_main")]])
    
    # Редактируем сообщение, чтобы не было "лесенки"
    await call.message.edit_text(f"🛍 *{cat}:*", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("p_"))
async def product_detail(call: types.CallbackQuery):
    _, name, vol, count = call.data.split("_")
    count = int(count)
    p = next((item for item in fetch_products() if item['Название'] == name), None)
    if not p: return

    price = p.get('Цена_Литр') if vol == "1л" else p.get('Цена_КГ')
    photo_url = p.get('Фото')

    text = (f"🍯 *{p['Название']}*\n\n{p.get('Описание', '')}\n\n"
            f"💰 *Barcha narxlar / Все цены:*\n"
            f"⚖️ 1 kg — {p.get('Цена_КГ')} so'm\n"
            f"💧 1 l — {p.get('Цена_Литр')} so'm\n\n"
            f"📍 *Tanlangan / Выбрано: {count} × {vol} = {price * count} so'm*")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 kg" if vol=="1л" else "✅ 1 kg", callback_data=f"p_{name}_1кг_{count}"), 
         InlineKeyboardButton(text="✅ 1 l" if vol=="1кг" else "1 l", callback_data=f"p_{name}_1л_{count}")],
        [InlineKeyboardButton(text="➖", callback_data=f"p_{name}_{vol}_{max(1, count-1)}"), 
         InlineKeyboardButton(text=str(count), callback_data="ignore"), 
         InlineKeyboardButton(text="➕", callback_data=f"p_{name}_{vol}_{count+1}")],
        [InlineKeyboardButton(text="🛒 Savatga / В корзину", callback_data="add_to_cart")],
        [InlineKeyboardButton(text="⬅️ Ortga / Назад", callback_data=f"cat_{p['Категория']}")]
    ])

    try:
        if photo_url and str(photo_url).strip():
            # Если есть фото, удаляем старое и шлем новое сообщение с картинкой
            await call.message.delete()
            await call.message.answer_photo(photo=photo_url, caption=text, reply_markup=kb, parse_mode="Markdown")
        else:
            # Если фото нет, просто редактируем текст
            await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка при работе с фото: {e}")
        await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "back_main")
async def back_main(call: types.CallbackQuery):
    products = fetch_products()
    categories = list(set([p['Категория'] for p in products if p.get('Категория')]))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c, callback_data=f"cat_{c}")] for c in categories])
    await call.message.edit_text("📦 *Tanlang / Выберите категорию:*", reply_markup=kb, parse_mode="Markdown")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

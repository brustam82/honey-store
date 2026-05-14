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

# Авторизация (использует файл google_creds.json из репозитория)
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

# Главное меню
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🍯 Mahsulotlar / Товары")],
        [KeyboardButton(text="🛒 Savatcha / Корзина"), KeyboardButton(text="📞 Kontaktlar / Контакты")]
    ], resize_keyboard=True)

@dp.message(CommandStart())
async def start(m: types.Message):
    await m.answer("Xush kelibsiz! / Добро пожаловать!", reply_markup=main_kb())

@dp.message(F.text == "🍯 Mahsulotlar / Товары")
async def show_products(m: types.Message):
    products = fetch_products()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=p['Название'], callback_data=f"p_{i}")] for i, p in enumerate(products)])
    await m.answer("Tanlang / Выберите товар:", reply_markup=kb)

@dp.callback_query(F.data.startswith("p_"))
async def product_card(call: types.CallbackQuery):
    idx = int(call.data.split("_")[1])
    p = fetch_products()[idx]
    
    # Разделение описания
    desc = p.get('Описание', 'Uz: ... | Ru: ...')
    uz_desc, ru_desc = desc.split('|') if '|' in desc else (desc, desc)
    
    text = f"*{p['Название']}*\n\n{uz_desc}\n{ru_desc}\n\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⚖️ 1 kg: {p['Цена_кг']} so'm", callback_data=f"buy_{idx}_kg")],
        [InlineKeyboardButton(text=f"💧 1 l: {p['Цена_литр']} so'm", callback_data=f"buy_{idx}_l")]
    ])
    await call.message.answer(text, parse_mode="Markdown", reply_markup=kb)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

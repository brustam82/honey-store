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

# Инициализация
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Функция получения данных (как у вас)
def get_google_client():
    creds_json = os.getenv('GOOGLE_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def fetch_products():
    client = get_google_client()
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
    return [r for r in sheet.get_all_records() if str(r.get("Активен", "")).lower() == "да"]

# --- Ключевой обработчик карточки товара ---
@dp.callback_query(F.data.startswith("p_"))
async def product_detail(call: types.CallbackQuery):
    # data формат: p_Название_объем_количество
    parts = call.data.split("_")
    name = parts[1]
    volume = parts[2] if len(parts) > 2 else "1л"
    count = int(parts[3]) if len(parts) > 3 else 1
    
    p = next((item for item in fetch_products() if item['Название'] == name), None)
    if not p: return

    # Формируем текст
    price = p.get('Цена_Литр') if volume == "1л" else p.get('Цена_КГ')
    text = (f"🍯 *{p['Название']}*\n\n{p.get('Описание', '')}\n\n"
            f"💰 Narx: {price} so'm\n\n"
            f"📍 Tanlangan: {volume} — {price * count} so'm")

    # Создаем клавиатуру как на вашем скриншоте
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1кг" if volume == "1л" else "✅ 1кг", callback_data=f"p_{name}_1кг_{count}"),
            InlineKeyboardButton(text="✅ 1л" if volume == "1л" else "1л", callback_data=f"p_{name}_1л_{count}")
        ],
        [
            InlineKeyboardButton(text="➖", callback_data=f"p_{name}_{volume}_{max(1, count-1)}"),
            InlineKeyboardButton(text=str(count), callback_data="ignore"),
            InlineKeyboardButton(text="➕", callback_data=f"p_{name}_{volume}_{count+1}")
        ],
        [InlineKeyboardButton(text="🛒 Savatga / В корзину", callback_data="add_to_cart")],
        [InlineKeyboardButton(text="⬅️ Ortga / Назад", callback_data="back_to_main")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

# ... (остальные функции start и show_categories оставляем как были)

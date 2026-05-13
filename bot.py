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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def get_google_client():
    raw = os.getenv("GOOGLE_CREDENTIALS", "")
    creds_dict = json.loads(raw)
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def fetch_products():
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        data = sheet.get_all_records()
        logger.info(f"Загружено товаров: {len(data)}")
        return data
    except Exception as e:
        logger.error(f"Ошибка таблицы: {e}")
        return []

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
        await message.answer("Таблица пуста или нет доступа.")
        return
    categories = sorted({p["Категория"] for p in products if p.get("Категория")})
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat, callback_data=f"cat_{cat}")
    builder.adjust(1)
    await message.answer("Выберите категорию:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("cat_"))
async def show_products(callback: types.CallbackQuery):
    category = callback.data[4:]
    products = fetch_products()
    items = [p for p in products if p.get("Категория") == category]
    if not items:
        await callback.message.answer("В этой категории нет товаров.")
        await callback.answer()
        return
    for p in items:
        name = p.get("Название", "Без названия")
        desc = p.get("Описание", "")
        price = p.get("Цена", "")
        text = f"🍯 *{name}*\n"
        if desc:
            text += f"{desc}\n"
        if price:
            text += f"\n💰 Цена: {price}"
        builder = InlineKeyboardBuilder()
        builder.button(text="🛒 Добавить в корзину", callback_data=f"add_{name}")
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("add_"))
async def add_to_cart(callback: types.CallbackQuery):
    product_name = callback.data[4:]
    await callback.message.answer(f"✅ «{product_name}» добавлен в корзину!")
    await callback.answer()

@dp.message(F.text == "🛒 Savatcha / Корзина")
async def show_cart(message: types.Message):
    await message.answer("🛒 Корзина в разработке. Напишите нам для оформления заказа.")

@dp.message(F.text == "📞 Aloqa ma'lumotlari / Контакты")
async def show_contacts(message: types.Message):
    await message.answer("📞 Свяжитесь с нами:\nTelegram: @ваш_контакт")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

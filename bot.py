import logging
import asyncio
import json
import os
import gspread
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- FSM ---
class OrderState(StatesGroup):
    choosing_category = State()
    choosing_product = State()
    choosing_variant = State()
    choosing_quantity = State()
    entering_name = State()
    entering_phone = State()
    confirming = State()

# --- Google Sheets ---
def get_google_client():
    creds_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS", "{}"))
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
        return data
    except Exception as e:
        logger.error(f"Ошибка чтения таблицы Товары: {e}")
        return []

def save_order(user_id, username, name, phone, items_text, total):
    try:
        client = get_google_client()
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Заказы")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        sheet.append_row([now, user_id, username, name, phone, items_text, total, "Yangi / Новый"])
        return True
    except Exception as e:
        logger.error(f"Ошибка записи заказа: {e}")
        return False

# --- Главное меню ---
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🍯 Mahsulotlar / Товары")],
        [KeyboardButton(text="🛒 Savatcha / Корзина")],
        [KeyboardButton(text="📞 Kontaktlar / Контакты")]
    ], resize_keyboard=True)

# --- /start ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Xush kelibsiz! / Добро пожаловать!\n\n"
        "🍯 *Asal Shifo* — tabiiy asal do'koni / магазин натурального мёда\n\n"
        "Mahsulotlarni ko'rish uchun quyidagi tugmani bosing.\n"
        "Для просмотра товаров нажмите кнопку ниже.",
        reply_markup=main_kb(),
        parse_mode="Markdown"
    )

# --- Категории ---
@dp.message(F.text == "🍯 Mahsulotlar / Товары")
async def show_categories(message: types.Message, state: FSMContext):
    products = fetch_products()
    if not products:
        await message.answer(
            "⚠️ Mahsulotlar vaqtincha mavjud emas. Keyinroq urinib ko'ring.\n"
            "⚠️ Товары временно недоступны. Попробуйте позже."
        )
        return
    categories = sorted({p["Категория"] for p in products if p.get("Категория")})
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat, callback_data=f"cat_{cat}")
    builder.adjust(1)
    await state.set_state(OrderState.choosing_category)
    await message.answer(
        "📦 Kategoriyani tanlang / Выберите категорию:",
        reply_markup=builder.as_markup()
    )

# --- Товары категории ---
@dp.callback_query(F.data.startswith("cat_"))
async def show_products(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data[4:]
    products = fetch_products()
    items = [p for p in products if p.get("Категория") == category]
    if not items:
        await callback.message.answer(
            "Bu kategoriyada mahsulot yo'q.\n"
            "В этой категории нет товаров."
        )
        await callback.answer()
        return
    builder = InlineKeyboardBuilder()
    seen = set()
    for p in items:
        name = p.get("Название", "")
        base = name.split(" (")[0]
        if base not in seen:
            seen.add(base)
            builder.button(text=f"🍯 {base}", callback_data=f"prod_{base}")
    builder.button(text="◀️ Orqaga / Назад", callback_data="back_categories")
    builder.adjust(1)
    await state.set_state(OrderState.choosing_product)
    await callback.message.edit_text(
        f"📦 *{category}*\n\nMahsulotni tanlang / Выберите товар:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await callback.answer()

# --- Назад к категориям ---
@dp.callback_query(F.data == "back_categories")
async def back_to_categories(callback: types.CallbackQuery, state: FSMContext):
    products = fetch_products()
    categories = sorted({p["Категория"] for p in products if p.get("Категория")})
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat, callback_data=f"cat_{cat}")
    builder.adjust(1)
    await state.set_state(OrderState.choosing_category)
    await callback.message.edit_text(
        "📦 Kategoriyani tanlang / Выберите категорию:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# --- Варианты (1кг / 1л) ---
@dp.callback_query(F.data.startswith("prod_"))
async def show_variants(callback: types.CallbackQuery, state: FSMContext):
    base_name = callback.data[5:]
    products = fetch_products()
    variants = [p for p in products if p.get("Название", "").startswith(base_name)]

    if not variants:
        await callback.message.answer(
            "Mahsulot topilmadi.\nТовар не найден."
        )
        await callback.answer()
        return

    desc = variants[0].get("Описание", "")
    text = f"🍯 *{base_name}*\n"
    if desc:
        text += f"_{desc}_\n"
    text += (
        "\nHajm yoki og'irlikni tanlang:\n"
        "Выберите объём или вес:"
    )

    builder = InlineKeyboardBuilder()
    for v in variants:
        vname = v.get("Название", "")
        price = v.get("Цена", "")
        if "(" in vname and ")" in vname:
            label = vname[vname.find("(")+1:vname.find(")")]
        else:
            label = vname
        try:
            price_fmt = f"{int(str(price).replace(' ','').replace(',','')):,}"
        except:
            price_fmt = str(price)
        builder.button(
            text=f"📦 {label} — {price_fmt} so'm/сум",
            callback_data=f"var_{vname}"
        )
    builder.button(
        text="◀️ Orqaga / Назад",
        callback_data=f"cat_{variants[0].get('Категория','')}"
    )
    builder.adjust(1)
    await state.update_data(base_name=base_name)
    await state.set_state(OrderState.choosing_variant)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

# --- Выбор количества ---
@dp.callback_query(F.data.startswith("var_"))
async def choose_quantity(callback: types.CallbackQuery, state: FSMContext):
    variant_name = callback.data[4:]
    products = fetch_products()
    product = next((p for p in products if p.get("Название") == variant_name), None)
    if not product:
        await callback.message.answer("Mahsulot topilmadi.\nТовар не найден.")
        await callback.answer()
        return

    price = product.get("Цена", 0)
    try:
        price_int = int(str(price).replace(" ", "").replace(",", ""))
    except:
        price_int = 0

    await state.update_data(
        selected_product=variant_name,
        selected_price=price_int,
        selected_category=product.get("Категория", "")
    )

    builder = InlineKeyboardBuilder()
    for qty in [1, 2, 3, 5, 10]:
        builder.button(text=str(qty), callback_data=f"qty_{qty}")
    builder.button(text="✏️ Boshqa miqdor / Другое количество", callback_data="qty_manual")
    builder.adjust(5, 1)

    await state.set_state(OrderState.choosing_quantity)
    await callback.message.edit_text(
        f"✅ *{variant_name}*\n"
        f"💰 Narxi / Цена: {price_int:,} so'm/сум\n\n"
        f"Miqdorni tanlang / Выберите количество:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await callback.answer()

# --- Количество кнопкой ---
@dp.callback_query(F.data.startswith("qty_"))
async def set_quantity(callback: types.CallbackQuery, state: FSMContext):
    qty_str = callback.data[4:]
    if qty_str == "manual":
        await state.set_state(OrderState.choosing_quantity)
        await callback.message.answer(
            "Miqdorni kiriting (masalan: 3) / Введите количество (например: 3):"
        )
        await callback.answer()
        return

    qty = int(qty_str)
    data = await state.get_data()
    cart = data.get("cart", [])
    price_int = data.get("selected_price", 0)
    product = data.get("selected_product", "")

    cart.append({"name": product, "qty": qty, "price": price_int, "total": price_int * qty})
    await state.update_data(cart=cart)

    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Savatchaga o'tish / Перейти в корзину", callback_data="go_cart")
    builder.button(text="🍯 Xarid davom ettirish / Продолжить покупки", callback_data="back_categories")
    builder.adjust(1)
    await callback.message.edit_text(
        f"✅ *{product}* x{qty} — savatchaga qo'shildi / добавлен в корзину!\n\n"
        f"💰 Jami / Сумма: {price_int * qty:,} so'm/сум",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await callback.answer()

# --- Ручной ввод количества ---
@dp.message(OrderState.choosing_quantity)
async def manual_quantity(message: types.Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
        if qty <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "Iltimos, musbat son kiriting.\nПожалуйста, введите целое число больше 0:"
        )
        return

    data = await state.get_data()
    cart = data.get("cart", [])
    price_int = data.get("selected_price", 0)
    product = data.get("selected_product", "")

    cart.append({"name": product, "qty": qty, "price": price_int, "total": price_int * qty})
    await state.update_data(cart=cart)

    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Savatchaga o'tish / Перейти в корзину", callback_data="go_cart")
    builder.button(text="🍯 Xarid davom ettirish / Продолжить покупки", callback_data="back_categories")
    builder.adjust(1)
    await message.answer(
        f"✅ *{product}* x{qty} — savatchaga qo'shildi / добавлен в корзину!\n\n"
        f"💰 Jami / Сумма: {price_int * qty:,} so'm/сум",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# --- Корзина ---
@dp.message(F.text == "🛒 Savatcha / Корзина")
async def show_cart_btn(message: types.Message, state: FSMContext):
    await show_cart_content(message, state, edit=False)

@dp.callback_query(F.data == "go_cart")
async def go_cart(callback: types.CallbackQuery, state: FSMContext):
    await show_cart_content(callback.message, state, edit=False)
    await callback.answer()

async def show_cart_content(message, state: FSMContext, edit=False):
    data = await state.get_data()
    cart = data.get("cart", [])
    if not cart:
        await message.answer(
            "🛒 Savatcha bo'sh.\n"
            "🛒 Корзина пуста.\n\n"
            "Mahsulot tanlash uchun *🍯 Mahsulotlar / Товары* tugmasini bosing.\n"
            "Нажмите *🍯 Mahsulotlar / Товары* для выбора товаров.",
            parse_mode="Markdown",
            reply_markup=main_kb()
        )
        return

    text = "🛒 *Savatchangiz / Ваша корзина:*\n\n"
    grand_total = 0
    for i, item in enumerate(cart, 1):
        text += f"{i}. {item['name']} × {item['qty']} = {item['total']:,} so'm/сум\n"
        grand_total += item['total']
    text += f"\n💰 *Jami / Итого: {grand_total:,} so'm/сум*"

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Buyurtma berish / Оформить заказ", callback_data="checkout")
    builder.button(text="🗑 Tozalash / Очистить корзину", callback_data="clear_cart")
    builder.button(text="🍯 Xarid davom ettirish / Продолжить покупки", callback_data="back_categories")
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# --- Очистить корзину ---
@dp.callback_query(F.data == "clear_cart")
async def clear_cart(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(cart=[])
    await callback.message.edit_text(
        "🗑 Savatcha tozalandi / Корзина очищена."
    )
    await callback.answer()

# --- Оформление заказа ---
@dp.callback_query(F.data == "checkout")
async def checkout(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(OrderState.entering_name)
    await callback.message.answer(
        "📝 Ismingizni kiriting / Введите ваше имя:",
        reply_markup=ReplyKeyboardRemove()
    )
    await callback.answer()

@dp.message(OrderState.entering_name)
async def enter_name(message: types.Message, state: FSMContext):
    await state.update_data(customer_name=message.text.strip())
    await state.set_state(OrderState.entering_phone)
    await message.answer(
        "📞 Telefon raqamingizni kiriting / Введите номер телефона\n"
        "(masalan/например: +998901234567):"
    )

@dp.message(OrderState.entering_phone)
async def enter_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    await state.update_data(customer_phone=phone)

    data = await state.get_data()
    cart = data.get("cart", [])
    name = data.get("customer_name", "")
    grand_total = sum(i['total'] for i in cart)

    text = (
        "📋 *Buyurtmani tasdiqlang / Подтвердите заказ:*\n\n"
        f"👤 Ism / Имя: {name}\n"
        f"📞 Telefon / Телефон: {phone}\n\n"
    )
    for item in cart:
        text += f"• {item['name']} × {item['qty']} = {item['total']:,} so'm/сум\n"
    text += f"\n💰 *Jami / Итого: {grand_total:,} so'm/сум*"

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash / Подтвердить", callback_data="confirm_order")
    builder.button(text="❌ Bekor qilish / Отмена", callback_data="cancel_order")
    builder.adjust(1)
    await state.set_state(OrderState.confirming)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "confirm_order")
async def confirm_order(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart = data.get("cart", [])
    name = data.get("customer_name", "")
    phone = data.get("customer_phone", "")
    user = callback.from_user
    grand_total = sum(i['total'] for i in cart)
    items_text = "; ".join([f"{i['name']} x{i['qty']}" for i in cart])

    ok = save_order(
        user.id,
        f"@{user.username}" if user.username else user.first_name,
        name, phone, items_text, grand_total
    )

    await state.clear()
    if ok:
        await callback.message.edit_text(
            f"✅ *Buyurtmangiz qabul qilindi! / Заказ принят!*\n\n"
            f"Rahmat, {name}!\n"
            f"Siz bilan {phone} raqami orqali bog'lanamiz.\n"
            f"Мы свяжемся с вами по номеру {phone}.\n\n"
            f"💰 Buyurtma summasi / Сумма заказа: {grand_total:,} so'm/сум",
            parse_mode="Markdown"
        )
        await callback.message.answer(
            "Asosiy menyu / Главное меню:",
            reply_markup=main_kb()
        )
    else:
        await callback.message.answer(
            "⚠️ Xatolik yuz berdi. Iltimos, bizga to'g'ridan-to'g'ri murojaat qiling.\n"
            "⚠️ Ошибка сохранения заказа. Пожалуйста, свяжитесь с нами напрямую.",
            reply_markup=main_kb()
        )
    await callback.answer()

@dp.callback_query(F.data == "cancel_order")
async def cancel_order(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Buyurtma bekor qilindi / Заказ отменён."
    )
    await callback.message.answer(
        "Asosiy menyu / Главное меню:",
        reply_markup=main_kb()
    )
    await callback.answer()

# --- Контакты ---
@dp.message(F.text == "📞 Kontaktlar / Контакты")
async def show_contacts(message: types.Message):
    await message.answer(
        "📞 *Biz bilan bog'laning / Свяжитесь с нами:*\n\n"
        "Telegram: @ваш_контакт\n"
        "📱 Telefon / Телефон: +998 XX XXX XX XX\n"
        "🕐 Ish vaqti / Время работы: 9:00 – 20:00",
        parse_mode="Markdown"
    )

# --- Запуск ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

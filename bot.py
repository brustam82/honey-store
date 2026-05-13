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

# ---------------------------------------------------------------------------
# FSM states
# ---------------------------------------------------------------------------
class OrderState(StatesGroup):
    choosing_category = State()
    choosing_product   = State()
    choosing_unit      = State()   # выбор ед. измерения (1кг / 1л)
    choosing_quantity  = State()   # ввод количества вручную
    entering_name      = State()
    entering_phone     = State()
    confirming         = State()

# ---------------------------------------------------------------------------
# Google Sheets helpers
# ---------------------------------------------------------------------------
def get_google_client():
    creds_dict = json.loads(os.getenv("GOOGLE_CREDENTIALS", "{}"))
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def fetch_products():
    try:
        client = get_google_client()
        sheet  = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        return sheet.get_all_records()
    except Exception as e:
        logger.error(f"fetch_products error: {e}")
        return []

def save_order(user_id, username, name, phone, items_text, total):
    try:
        client = get_google_client()
        sheet  = client.open_by_key(SPREADSHEET_ID).worksheet("Заказы")
        now    = datetime.now().strftime("%Y-%m-%d %H:%M")
        sheet.append_row([now, user_id, username, name, phone, items_text, total, "Yangi / Новый"])
        return True
    except Exception as e:
        logger.error(f"save_order error: {e}")
        return False

# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------
def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍯 Mahsulotlar / Товары")],
            [KeyboardButton(text="🛒 Savatcha / Корзина")],
            [KeyboardButton(text="📞 Kontaktlar / Контакты")],
        ],
        resize_keyboard=True,
    )

def fmt_price(raw) -> int:
    try:
        return int(str(raw).replace(" ", "").replace(",", ""))
    except Exception:
        return 0

def unit_and_qty_keyboard(variants: list, selected_unit: str | None = None, qty: int = 1):
    """
    Строит клавиатуру в стиле скриншота:
    Строка 1 — кнопки выбора ед. измерения (1 кг / 1 л …)
    Строка 2 — кнопки быстрого количества: − 1 + (и текущее)
    Строка 3 — «Добавить в корзину»
    """
    builder = InlineKeyboardBuilder()

    # --- ряд единиц ---
    for v in variants:
        vname = v.get("Название", "")
        if "(" in vname and ")" in vname:
            label = vname[vname.find("(") + 1 : vname.find(")")]
        else:
            label = vname
        mark = "✅ " if vname == selected_unit else ""
        builder.button(
            text=f"{mark}{label}",
            callback_data=f"unit_{vname}",
        )

    # --- ряд количества ---
    builder.button(text="➖", callback_data="qminus")
    builder.button(text=f"  {qty}  ", callback_data="qshow")
    builder.button(text="➕", callback_data="qplus")

    # --- добавить в корзину ---
    if selected_unit:
        product = next((v for v in variants if v.get("Название") == selected_unit), None)
        price = fmt_price(product.get("Цена", 0)) if product else 0
        total = price * qty
        builder.button(
            text=f"🛒 Savatchaga qo'shish / В корзину  {total:,} so'm",
            callback_data="add_to_cart",
        )
    else:
        builder.button(text="🛒 Hajmni tanlang / Выберите объём", callback_data="qshow")

    # --- назад ---
    builder.button(text="◀️ Orqaga / Назад", callback_data="back_categories")

    # компоновка: [единицы по 2], [- qty +], [корзина], [назад]
    unit_count = len(variants)
    builder.adjust(min(unit_count, 2), 3, 1, 1)
    return builder.as_markup()

# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Xush kelibsiz! / Добро пожаловать! 🍯\n\n"
        "*Asal Shifo* — tabiiy asal do'koni / магазин натурального мёда\n\n"
        "Mahsulot tanlash uchun quyidagi tugmani bosing.\n"
        "Нажмите кнопку ниже для выбора товаров.",
        reply_markup=main_kb(),
        parse_mode="Markdown",
    )

# ---------------------------------------------------------------------------
# Категории
# ---------------------------------------------------------------------------
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
        reply_markup=builder.as_markup(),
    )

# ---------------------------------------------------------------------------
# Товары категории
# ---------------------------------------------------------------------------
@dp.callback_query(F.data.startswith("cat_"))
async def show_products(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data[4:]
    products = fetch_products()
    items    = [p for p in products if p.get("Категория") == category]
    if not items:
        await callback.message.answer(
            "Bu kategoriyada mahsulot yo'q.\nВ этой категории нет товаров."
        )
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    seen    = set()
    for p in items:
        vname = p.get("Название", "")
        base  = vname.split(" (")[0]
        if base not in seen:
            seen.add(base)
            builder.button(text=f"🍯 {base}", callback_data=f"prod_{base}")
    builder.button(text="◀️ Orqaga / Назад", callback_data="back_categories")
    builder.adjust(1)

    await state.set_state(OrderState.choosing_product)
    await callback.message.edit_text(
        f"📦 *{category}*\n\nMahsulotni tanlang / Выберите товар:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )
    await callback.answer()

# ---------------------------------------------------------------------------
# Назад к категориям
# ---------------------------------------------------------------------------
@dp.callback_query(F.data == "back_categories")
async def back_to_categories(callback: types.CallbackQuery, state: FSMContext):
    products   = fetch_products()
    categories = sorted({p["Категория"] for p in products if p.get("Категория")})
    builder    = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat, callback_data=f"cat_{cat}")
    builder.adjust(1)
    await state.set_state(OrderState.choosing_category)
    await callback.message.edit_text(
        "📦 Kategoriyani tanlang / Выберите категорию:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()

# ---------------------------------------------------------------------------
# Экран товара — единицы + количество на одном экране
# ---------------------------------------------------------------------------
async def render_product_screen(target_message, state: FSMContext, edit: bool = True):
    """Отрисовывает / обновляет экран выбора единицы и количества."""
    data          = await state.get_data()
    base_name     = data.get("base_name", "")
    selected_unit = data.get("selected_unit")   # полное название варианта
    qty           = data.get("qty", 1)
    variants      = data.get("variants", [])

    # Описание из первого варианта
    desc = variants[0].get("Описание", "") if variants else ""

    # Формируем текст карточки товара
    text = f"🍯 *{base_name}*\n"
    if desc:
        text += f"_{desc}_\n"
    text += "\n"

    # Показываем цены всех вариантов
    for v in variants:
        vname = v.get("Название", "")
        if "(" in vname and ")" in vname:
            label = vname[vname.find("(") + 1 : vname.find(")")]
        else:
            label = vname
        price = fmt_price(v.get("Цена", 0))
        text += f"• {label}: {price:,} so'm/сум\n"

    text += "\n"
    if selected_unit:
        product   = next((v for v in variants if v.get("Название") == selected_unit), None)
        price     = fmt_price(product.get("Цена", 0)) if product else 0
        total     = price * qty
        unit_label = selected_unit[selected_unit.find("(") + 1 : selected_unit.find(")")] \
                     if "(" in selected_unit else selected_unit
        text += (
            f"✅ *Tanlangan / Выбрано:* {unit_label}\n"
            f"🔢 *Miqdor / Количество:* {qty} dona\n"
            f"💰 *Jami / Итого:* {total:,} so'm/сум"
        )
    else:
        text += "👇 Hajm yoki og'irlikni tanlang / Выберите объём или вес"

    markup = unit_and_qty_keyboard(variants, selected_unit, qty)

    if edit:
        await target_message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await target_message.answer(text, reply_markup=markup, parse_mode="Markdown")


@dp.callback_query(F.data.startswith("prod_"))
async def show_product_card(callback: types.CallbackQuery, state: FSMContext):
    base_name = callback.data[5:]
    products  = fetch_products()
    variants  = [p for p in products if p.get("Название", "").startswith(base_name + " (")
                 or p.get("Название", "") == base_name]

    if not variants:
        await callback.message.answer("Mahsulot topilmadi.\nТовар не найден.")
        await callback.answer()
        return

    await state.update_data(
        base_name=base_name,
        variants=variants,
        selected_unit=None,
        qty=1,
    )
    await state.set_state(OrderState.choosing_unit)
    await render_product_screen(callback.message, state, edit=True)
    await callback.answer()

# ---------------------------------------------------------------------------
# Выбор единицы измерения
# ---------------------------------------------------------------------------
@dp.callback_query(F.data.startswith("unit_"))
async def select_unit(callback: types.CallbackQuery, state: FSMContext):
    unit_name = callback.data[5:]
    await state.update_data(selected_unit=unit_name, qty=1)
    await render_product_screen(callback.message, state, edit=True)
    await callback.answer()

# ---------------------------------------------------------------------------
# Кнопки ➕ / ➖
# ---------------------------------------------------------------------------
@dp.callback_query(F.data == "qplus")
async def qty_plus(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    qty  = data.get("qty", 1) + 1
    await state.update_data(qty=qty)
    await render_product_screen(callback.message, state, edit=True)
    await callback.answer()

@dp.callback_query(F.data == "qminus")
async def qty_minus(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    qty  = max(1, data.get("qty", 1) - 1)
    await state.update_data(qty=qty)
    await render_product_screen(callback.message, state, edit=True)
    await callback.answer()

@dp.callback_query(F.data == "qshow")
async def qty_show(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()   # просто игнорируем нажатие на индикатор

# ---------------------------------------------------------------------------
# Добавить в корзину
# ---------------------------------------------------------------------------
@dp.callback_query(F.data == "add_to_cart")
async def add_to_cart(callback: types.CallbackQuery, state: FSMContext):
    data          = await state.get_data()
    selected_unit = data.get("selected_unit")
    qty           = data.get("qty", 1)
    variants      = data.get("variants", [])

    if not selected_unit:
        await callback.answer(
            "Iltimos, hajmni tanlang / Пожалуйста, выберите объём!", show_alert=True
        )
        return

    product   = next((v for v in variants if v.get("Название") == selected_unit), None)
    price     = fmt_price(product.get("Цена", 0)) if product else 0
    total     = price * qty
    unit_label = selected_unit[selected_unit.find("(") + 1 : selected_unit.find(")")] \
                 if "(" in selected_unit else selected_unit

    cart = data.get("cart", [])
    # Если такой вариант уже в корзине — суммируем количество
    existing = next((i for i in cart if i["name"] == selected_unit), None)
    if existing:
        existing["qty"]   += qty
        existing["total"] += total
    else:
        cart.append({"name": selected_unit, "unit": unit_label, "qty": qty,
                     "price": price, "total": total})
    await state.update_data(cart=cart, selected_unit=None, qty=1)

    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Savatchaga o'tish / Перейти в корзину", callback_data="go_cart")
    builder.button(text="🍯 Xarid davom ettirish / Продолжить покупки", callback_data="back_categories")
    builder.adjust(1)

    await callback.message.edit_text(
        f"✅ *{selected_unit}* × {qty} — savatchaga qo'shildi / добавлен в корзину!\n\n"
        f"💰 {total:,} so'm/сум",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )
    await callback.answer()

# ---------------------------------------------------------------------------
# Корзина
# ---------------------------------------------------------------------------
@dp.message(F.text == "🛒 Savatcha / Корзина")
async def show_cart_btn(message: types.Message, state: FSMContext):
    await show_cart_content(message, state)

@dp.callback_query(F.data == "go_cart")
async def go_cart(callback: types.CallbackQuery, state: FSMContext):
    await show_cart_content(callback.message, state)
    await callback.answer()

async def show_cart_content(message, state: FSMContext):
    data = await state.get_data()
    cart = data.get("cart", [])
    if not cart:
        await message.answer(
            "🛒 Savatcha bo'sh / Корзина пуста.\n\n"
            "Mahsulot tanlash uchun *🍯 Mahsulotlar / Товары* tugmasini bosing.\n"
            "Нажмите *🍯 Mahsulotlar / Товары* для выбора товаров.",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )
        return

    text        = "🛒 *Savatchangiz / Ваша корзина:*\n\n"
    grand_total = 0
    for i, item in enumerate(cart, 1):
        text        += f"{i}. {item['name']} × {item['qty']} = {item['total']:,} so'm/сум\n"
        grand_total += item["total"]
    text += f"\n💰 *Jami / Итого: {grand_total:,} so'm/сум*"

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Buyurtma berish / Оформить заказ", callback_data="checkout")
    builder.button(text="🗑 Tozalash / Очистить корзину",        callback_data="clear_cart")
    builder.button(text="🍯 Xarid davom ettirish / Продолжить", callback_data="back_categories")
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# ---------------------------------------------------------------------------
# Очистить корзину
# ---------------------------------------------------------------------------
@dp.callback_query(F.data == "clear_cart")
async def clear_cart(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(cart=[])
    await callback.message.edit_text("🗑 Savatcha tozalandi / Корзина очищена.")
    await callback.answer()

# ---------------------------------------------------------------------------
# Оформление заказа
# ---------------------------------------------------------------------------
@dp.callback_query(F.data == "checkout")
async def checkout(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(OrderState.entering_name)
    await callback.message.answer(
        "📝 Ismingizni kiriting / Введите ваше имя:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await callback.answer()

@dp.message(OrderState.entering_name)
async def enter_name(message: types.Message, state: FSMContext):
    await state.update_data(customer_name=message.text.strip())
    await state.set_state(OrderState.entering_phone)
    await message.answer(
        "📞 Telefon raqamingizni kiriting / Введите номер телефона\n"
        "(masalan / например: +998901234567):"
    )

@dp.message(OrderState.entering_phone)
async def enter_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    await state.update_data(customer_phone=phone)

    data        = await state.get_data()
    cart        = data.get("cart", [])
    name        = data.get("customer_name", "")
    grand_total = sum(i["total"] for i in cart)

    text  = "📋 *Buyurtmani tasdiqlang / Подтвердите заказ:*\n\n"
    text += f"👤 Ism / Имя: {name}\n"
    text += f"📞 Telefon / Телефон: {phone}\n\n"
    for item in cart:
        text += f"• {item['name']} × {item['qty']} = {item['total']:,} so'm/сум\n"
    text += f"\n💰 *Jami / Итого: {grand_total:,} so'm/сум*"

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash / Подтвердить", callback_data="confirm_order")
    builder.button(text="❌ Bekor qilish / Отмена",    callback_data="cancel_order")
    builder.adjust(1)
    await state.set_state(OrderState.confirming)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "confirm_order")
async def confirm_order(callback: types.CallbackQuery, state: FSMContext):
    data        = await state.get_data()
    cart        = data.get("cart", [])
    name        = data.get("customer_name", "")
    phone       = data.get("customer_phone", "")
    user        = callback.from_user
    grand_total = sum(i["total"] for i in cart)
    items_text  = "; ".join([f"{i['name']} x{i['qty']}" for i in cart])

    ok = save_order(
        user.id,
        f"@{user.username}" if user.username else user.first_name,
        name, phone, items_text, grand_total,
    )
    await state.clear()

    if ok:
        await callback.message.edit_text(
            f"✅ *Buyurtmangiz qabul qilindi! / Заказ принят!*\n\n"
            f"Rahmat, {name}! 🙏\n"
            f"Siz bilan {phone} raqami orqali bog'lanamiz.\n"
            f"Мы свяжемся с вами по номеру {phone}.\n\n"
            f"💰 {grand_total:,} so'm/сум",
            parse_mode="Markdown",
        )
        await callback.message.answer("Asosiy menyu / Главное меню:", reply_markup=main_kb())
    else:
        await callback.message.answer(
            "⚠️ Xatolik yuz berdi. Iltimos, bizga to'g'ridan-to'g'ri murojaat qiling.\n"
            "⚠️ Ошибка сохранения заказа. Пожалуйста, свяжитесь с нами напрямую.",
            reply_markup=main_kb(),
        )
    await callback.answer()

@dp.callback_query(F.data == "cancel_order")
async def cancel_order(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Buyurtma bekor qilindi / Заказ отменён.")
    await callback.message.answer("Asosiy menyu / Главное меню:", reply_markup=main_kb())
    await callback.answer()

# ---------------------------------------------------------------------------
# Контакты
# ---------------------------------------------------------------------------
@dp.message(F.text == "📞 Kontaktlar / Контакты")
async def show_contacts(message: types.Message):
    await message.answer(
        "📞 *Biz bilan bog'laning / Свяжитесь с нами:*\n\n"
        "Telegram: @ваш_контакт\n"
        "📱 Telefon / Телефон: +998 XX XXX XX XX\n"
        "🕐 Ish vaqti / Время работы: 9:00 – 20:00",
        parse_mode="Markdown",
    )

# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

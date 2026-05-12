import logging
import asyncio
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import BOT_TOKEN, SPREADSHEET_ID

# ── Логирование ──────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Инициализация ────────────────────────────────────────────────────────────
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

user_carts: dict = {}
_cache: dict = {"products": [], "ts": 0}

# ── Контактные данные ─────────────────────────────────────────────────────────
CONTACT_PHONE = "+998 90 XXX XX XX"
MANAGER_USERNAME = "@addservice0910"
MANAGER_LINK = "https://t.me/addservice0910"


# ── FSM: сбор данных при оформлении заказа ───────────────────────────────────
class OrderState(StatesGroup):
    waiting_name = State()
    waiting_phone = State()


# ── Google Sheets ─────────────────────────────────────────────────────────────

def _fetch_products() -> list:
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Товары")
        rows = sheet.get_all_records()
        result = []
        for r in rows:
            clean = {str(k).strip(): str(v).strip() for k, v in r.items()}
            if clean.get("Активен", "").lower() in ("да", "yes", "1", "true"):
                result.append(clean)
        logger.info(f"Загружено товаров: {len(result)}")
        return result
    except Exception as e:
        logger.error(f"Ошибка чтения таблицы: {e}")
        return []


def _save_order(user_id: int, username: str, full_name: str, phone: str, cart: list) -> bool:
    """
    Записывает каждый товар отдельной строкой строго по столбцам:
    Дата | ID пользователя | Username | Имя | Телефон | Товар | Кол-во | Цена | Сумма
    """
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Заказы")
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        for item in cart:
            subtotal = item["price"] * item["qty"]
            sheet.append_row([
                date_str,
                str(user_id),
                f"@{username}" if username else "",
                full_name,
                phone,
                item["name"],
                item["qty"],
                item["price"],
                subtotal,
            ])
        return True
    except Exception as e:
        logger.error(f"Ошибка записи заказа: {e}")
        return False


async def get_products() -> list:
    if not _cache["products"] or time.time() - _cache["ts"] > 300:
        products = await asyncio.to_thread(_fetch_products)
        if products:
            _cache["products"] = products
            _cache["ts"] = time.time()
    return _cache["products"]


# ── Парсинг цен ───────────────────────────────────────────────────────────────

def parse_prices(price_str: str) -> list:
    """'1кг:310000, 1л:210000' → [{"unit":"1кг","price":310000.0}, ...]"""
    variants = []
    try:
        for part in str(price_str).strip().split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                idx = part.index(":")
                unit = part[:idx].strip()
                price_raw = part[idx + 1:].strip().replace(" ", "")
                try:
                    variants.append({"unit": unit, "price": float(price_raw)})
                except ValueError:
                    pass
            else:
                try:
                    variants.append({"unit": "ед.", "price": float(part.replace(" ", ""))})
                except ValueError:
                    pass
    except Exception as e:
        logger.error(f"parse_prices error: {e}")
    return variants or [{"unit": "ед.", "price": 0.0}]


# ── Клавиатуры ────────────────────────────────────────────────────────────────

def main_kb() -> ReplyKeyboardMarkup:
    # Кнопка "Мои заказы" убрана
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍯 Mahsulotlar ro'yhati / Перечень продукции")],
            [KeyboardButton(text="🛒 Savatcha / Корзина")],
            [KeyboardButton(text="📞 Aloqa ma'lumotlari / Контакты")],
        ],
        resize_keyboard=True,
    )


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telefon raqamini yuborish / Отправить номер", request_contact=True)],
            [KeyboardButton(text="❌ Bekor qilish / Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def product_kb(p_idx: int, variants: list, v_idx: int = 0, qty: int = 1):
    builder = InlineKeyboardBuilder()
    for i, v in enumerate(variants):
        label = f"✅ {v['unit']}" if i == v_idx else v['unit']
        builder.button(text=label, callback_data=f"v:{p_idx}:{i}:{qty}")

    builder.button(text="➖", callback_data=f"q:{p_idx}:{v_idx}:{max(1, qty - 1)}")
    builder.button(text=f"  {qty}  ", callback_data="noop")
    builder.button(text="➕", callback_data=f"q:{p_idx}:{v_idx}:{qty + 1}")

    builder.button(text="🛒 Savatga / В корзину", callback_data=f"add:{p_idx}:{v_idx}:{qty}")
    builder.button(text="🔙 Ortga / Назад", callback_data="to_cats")

    builder.adjust(len(variants), 3, 1, 1)
    return builder.as_markup()


def card_text(p: dict, variants: list, v_idx: int) -> str:
    sel = variants[v_idx]
    all_prices = "\n".join(f"• {v['unit']}: {v['price']:.0f} so'm" for v in variants)
    return (
        f"*{p['Название']}*\n\n"
        f"{p.get('Описание', '').strip()}\n\n"
        f"💰 *Barcha narxlar / Все цены:*\n{all_prices}\n\n"
        f"📍 *Tanlangan / Выбрано: {sel['unit']} — {sel['price']:.0f} so'm*"
    )


# ── Обработчики главного меню ─────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer(
        "Xush kelibsiz! Kerakli bo'limni tanlang.\n"
        "Добро пожаловать! Выберите нужный раздел.",
        reply_markup=main_kb(),
    )


@dp.message(F.text == "🍯 Mahsulotlar ro'yhati / Перечень продукции")
async def show_categories(m: types.Message):
    products = await get_products()
    if not products:
        await m.answer(
            "❌ Ma'lumotlarni yuklab bo'lmadi. Keyinroq urinib ko'ring.\n"
            "❌ Не удалось загрузить товары. Попробуйте позже."
        )
        return
    cats = sorted({p["Категория"] for p in products if p.get("Категория")})
    if not cats:
        await m.answer(
            "❌ Kategoriyalar topilmadi. Jadvalda 'Kategoriya' ustunini to'ldiring.\n"
            "❌ Категории не найдены. Заполните колонку 'Категория' в таблице."
        )
        return
    builder = InlineKeyboardBuilder()
    for cat in cats:
        builder.button(text=cat, callback_data=f"cat:{cat[:25]}")
    builder.adjust(2)
    await m.answer(
        "Kategoriyani tanlang / Выберите категорию:",
        reply_markup=builder.as_markup(),
    )


@dp.message(F.text == "🛒 Savatcha / Корзина")
async def show_cart(m: types.Message):
    cart = user_carts.get(m.from_user.id, [])
    if not cart:
        await m.answer("🛒 Savatcha bo'sh. / Корзина пуста.")
        return

    lines = []
    total = 0.0
    for item in cart:
        subtotal = item["price"] * item["qty"]
        total += subtotal
        lines.append(f"• {item['name']} × {item['qty']} = {subtotal:.0f} so'm")

    text = (
        "🛒 *Savatcha / Корзина:*\n\n"
        + "\n".join(lines)
        + f"\n\n💰 *Jami / Итого: {total:.0f} so'm*"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Buyurtma berish / Оформить заказ", callback_data="checkout")
    builder.button(text="🗑 Tozalash / Очистить корзину", callback_data="clear_cart")
    builder.adjust(1)
    await m.answer(text, parse_mode="Markdown", reply_markup=builder.as_markup())


@dp.message(F.text == "📞 Aloqa ma'lumotlari / Контакты")
async def show_contacts(m: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Menejer bilan bog'lanish / Написать менеджеру", url=MANAGER_LINK)
    await m.answer(
        f"📞 *Aloqa ma'lumotlari / Контакты:*\n\n"
        f"☎️ Tel: {CONTACT_PHONE}\n"
        f"👤 Menejer / Менеджер: {MANAGER_USERNAME}",
        parse_mode="Markdown",
        reply_markup=builder.as_markup(),
    )


# ── Оформление заказа (FSM) ───────────────────────────────────────────────────

@dp.callback_query(F.data == "checkout")
async def checkout_start(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()
    cart = user_carts.get(cb.from_user.id, [])
    if not cart:
        await cb.answer("Savatcha bo'sh. / Корзина пуста.", show_alert=True)
        return
    await state.set_state(OrderState.waiting_name)
    await cb.message.answer(
        "📝 Ismingizni kiriting (masalan: Rustam Karimov).\n"
        "Введите ваше имя (например: Rustam Karimov).",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(OrderState.waiting_name)
async def process_name(m: types.Message, state: FSMContext):
    await state.update_data(full_name=m.text.strip())
    await state.set_state(OrderState.waiting_phone)
    await m.answer(
        "📱 Telefon raqamingizni yuboring yoki qo'lda kiriting (+998XXXXXXXXX).\n"
        "Отправьте номер телефона или введите вручную (+998XXXXXXXXX).",
        reply_markup=phone_kb(),
    )


@dp.message(OrderState.waiting_phone, F.contact)
async def process_phone_contact(m: types.Message, state: FSMContext):
    await _finalize_order(m, state, m.contact.phone_number)


@dp.message(OrderState.waiting_phone, F.text)
async def process_phone_text(m: types.Message, state: FSMContext):
    text = m.text.strip()
    if text == "❌ Bekor qilish / Отмена":
        await state.clear()
        await m.answer(
            "Buyurtma bekor qilindi. / Заказ отменён.",
            reply_markup=main_kb(),
        )
        return
    if len("".join(c for c in text if c.isdigit())) < 7:
        await m.answer(
            "❌ Noto'g'ri raqam. Iltimos, qayta kiriting.\n"
            "❌ Неверный номер. Пожалуйста, введите ещё раз."
        )
        return
    await _finalize_order(m, state, text)


async def _finalize_order(m: types.Message, state: FSMContext, phone: str):
    data = await state.get_data()
    full_name = data.get("full_name", m.from_user.full_name or "")
    cart = user_carts.get(m.from_user.id, [])

    await m.answer(
        "⏳ Buyurtma saqlanmoqda... / Сохраняем заказ...",
        reply_markup=ReplyKeyboardRemove(),
    )

    success = await asyncio.to_thread(
        _save_order,
        m.from_user.id,
        m.from_user.username or "",
        full_name,
        phone,
        cart,
    )

    await state.clear()

    if success:
        lines = "\n".join(
            f"• {i['name']} × {i['qty']} = {i['price'] * i['qty']:.0f} so'm"
            for i in cart
        )
        total = sum(i["price"] * i["qty"] for i in cart)
        user_carts[m.from_user.id] = []
        await m.answer(
            f"✅ *Buyurtmangiz qabul qilindi! / Ваш заказ принят!*\n\n"
            f"{lines}\n\n"
            f"💰 *Jami / Итого: {total:.0f} so'm*\n\n"
            f"📱 Tel: {phone}\n"
            f"👤 {full_name}\n\n"
            f"Tez orada siz bilan bog'lanamiz.\n"
            f"Мы свяжемся с вами в ближайшее время.",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )
    else:
        await m.answer(
            "❌ Xatolik yuz berdi. Qayta urinib ko'ring.\n"
            "❌ Произошла ошибка. Попробуйте снова.",
            reply_markup=main_kb(),
        )


# ── Обработчики callback (каталог) ───────────────────────────────────────────

@dp.callback_query(F.data.startswith("cat:"))
async def list_products(cb: types.CallbackQuery):
    await cb.answer()
    cat_prefix = cb.data.split(":", 1)[1]
    products = await get_products()

    builder = InlineKeyboardBuilder()
    found = 0
    for i, p in enumerate(products):
        if p.get("Категория", "").startswith(cat_prefix):
            builder.button(text=p["Название"], callback_data=f"p:{i}")
            found += 1

    if found == 0:
        await cb.answer("Mahsulotlar topilmadi. / Товары не найдены.", show_alert=True)
        return

    builder.button(text="🔙 Ortga / Назад", callback_data="to_cats")
    builder.adjust(1)
    await cb.message.edit_text(
        "Mahsulotni tanlang / Выберите товар:",
        reply_markup=builder.as_markup(),
    )


@dp.callback_query(F.data.startswith("p:"))
async def show_product(cb: types.CallbackQuery):
    await cb.answer()
    p_idx = int(cb.data.split(":")[1])
    products = await get_products()

    if p_idx >= len(products):
        await cb.answer("Mahsulot topilmadi. / Товар не найден.", show_alert=True)
        return

    p = products[p_idx]
    variants = parse_prices(p["Цена"])
    text = card_text(p, variants, 0)
    kb = product_kb(p_idx, variants, 0, 1)

    photo = str(p.get("Фото", "")).strip()
    if (
        photo.startswith("http")
        and "photos.app.goo" not in photo
        and "google.com/photos" not in photo
    ):
        try:
            await cb.message.answer_photo(
                photo=photo, caption=text, parse_mode="Markdown", reply_markup=kb
            )
            await cb.message.delete()
            return
        except Exception as e:
            logger.warning(f"Фото не загрузилось: {e}")

    await cb.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data.startswith("v:") | F.data.startswith("q:"))
async def update_product_view(cb: types.CallbackQuery):
    await cb.answer()
    parts = cb.data.split(":")
    p_idx, v_idx, qty = int(parts[1]), int(parts[2]), int(parts[3])

    products = await get_products()
    if p_idx >= len(products):
        return

    p = products[p_idx]
    variants = parse_prices(p["Цена"])
    if v_idx >= len(variants):
        v_idx = 0

    text = card_text(p, variants, v_idx)
    kb = product_kb(p_idx, variants, v_idx, qty)

    try:
        if cb.message.caption is not None:
            await cb.message.edit_caption(caption=text, parse_mode="Markdown", reply_markup=kb)
        else:
            await cb.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        pass


@dp.callback_query(F.data.startswith("add:"))
async def add_to_cart(cb: types.CallbackQuery):
    parts = cb.data.split(":")
    p_idx, v_idx, qty = int(parts[1]), int(parts[2]), int(parts[3])

    products = await get_products()
    if p_idx >= len(products):
        await cb.answer("Xatolik. / Ошибка.", show_alert=True)
        return

    p = products[p_idx]
    variants = parse_prices(p["Цена"])
    if v_idx >= len(variants):
        v_idx = 0
    variant = variants[v_idx]

    cart = user_carts.setdefault(cb.from_user.id, [])
    item_name = f"{p['Название']} ({variant['unit']})"

    for item in cart:
        if item["name"] == item_name:
            item["qty"] += qty
            await cb.answer(f"✅ {item_name} yangilandi! (+{qty})")
            return

    cart.append({"name": item_name, "price": variant["price"], "qty": qty})
    await cb.answer(f"✅ {item_name} × {qty} qo'shildi!")


@dp.callback_query(F.data == "clear_cart")
async def clear_cart_cb(cb: types.CallbackQuery):
    user_carts[cb.from_user.id] = []
    await cb.answer("🗑 Savatcha tozalandi. / Корзина очищена.")
    await cb.message.edit_text("🛒 Savatcha bo'sh. / Корзина пуста.")


@dp.callback_query(F.data == "to_cats")
async def back_to_cats(cb: types.CallbackQuery):
    await cb.answer()
    await cb.message.delete()
    await show_categories(cb.message)


@dp.callback_query(F.data == "noop")
async def noop(cb: types.CallbackQuery):
    await cb.answer()


@dp.callback_query()
async def fallback_cb(cb: types.CallbackQuery):
    await cb.answer()


# ── Запуск ────────────────────────────────────────────────────────────────────

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    products = await asyncio.to_thread(_fetch_products)
    if products:
        _cache["products"] = products
        _cache["ts"] = time.time()
    logger.info(f"Бот запущен! Товаров в кэше: {len(_cache['products'])}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")

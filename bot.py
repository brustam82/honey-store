# Замените эти функции в вашем bot.py для обновления интерфейса

@dp.message(F.text == "🍯 Mahsulotlar / Товары")
async def show_categories(m: types.Message):
    products = fetch_products()
    # Получаем уникальные категории
    categories = list(set([p['Категория'] for p in products if p.get('Категория')]))
    
    if not categories:
        await m.answer("В данный момент товаров нет.")
        return

    # Создаем клавиатуру с категориями
    buttons = [[InlineKeyboardButton(text=c, callback_data=f"cat_{c}")] for c in categories]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await m.answer("📦 *Kategoriyani tanlang / Выберите категорию:*", 
                   reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("cat_"))
async def show_products(call: types.CallbackQuery):
    cat = call.data.split("_", 1)[1]
    products = [p for p in fetch_products() if p.get('Категория') == cat]
    
    # Кнопки для конкретных товаров в категории
    buttons = [[InlineKeyboardButton(text=p['Название'], callback_data=f"p_{p['Название']}")] for p in products]
    buttons.append([InlineKeyboardButton(text="⬅️ Ortga / Назад", callback_data="back_to_cats")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await call.message.edit_text(f"🛍 *{cat} bo'limidagi mahsulotlar / Товары в категории {cat}:*", 
                                 reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("p_"))
async def product_detail(call: types.CallbackQuery):
    name = call.data.split("_", 1)[1]
    p = next((item for item in fetch_products() if item['Название'] == name), None)
    
    if not p: return
    
    # Красивый вывод деталей товара
    text = (f"🍯 *{p['Название']}*\n\n"
            f"📝 {p.get('Описание', '')}\n\n"
            f"💰 *Narxlar / Цены:*\n"
            f"⚖️ 1 kg: {p.get('Цена_КГ', 0)} sum\n"
            f"💧 1 l: {p.get('Цена_Литр', 0)} sum")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Ortga / Назад", callback_data=f"cat_{p['Категория']}")]])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

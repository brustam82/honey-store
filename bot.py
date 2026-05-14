@dp.callback_query(F.data.startswith("p_"))
async def product_detail(call: types.CallbackQuery):
    _, name, vol, count = call.data.split("_")
    count = int(count)
    p = next((item for item in fetch_products() if item['Название'] == name), None)
    if not p: return

    price = p.get('Цена_Литр') if vol == "1л" else p.get('Цена_КГ')
    photo_url = p.get('Фото') # Бот ищет колонку "Фото" в Google Таблице

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
        # Если есть ссылка на фото, пытаемся отредактировать сообщение с медиа или отправить новое
        if photo_url:
            # Telegram не умеет менять текст на фото (edit_text -> edit_media)
            # Чтобы не усложнять, мы просто удаляем старое сообщение и шлем красивое с фото
            await call.message.delete()
            await call.message.answer_photo(photo=photo_url, caption=text, reply_markup=kb, parse_mode="Markdown")
        else:
            await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка при отправке фото: {e}")
        await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

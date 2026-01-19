import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InputMediaPhoto,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession

# --- ⚙️ ВАШИ НАСТРОЙКИ ---
TOKEN = "8586666424:AAHneQ_M9esmiq1_OhByXfk4fnHJWKWn5DI"
SUPERADMIN_ID = 6269786133
CHANNEL_ID = -1002347138762

# --- 📁 БАЗА ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS buttons (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, url TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

def add_user_db(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
    finally:
        conn.close()

def get_all_users():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def get_admins():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins")
    admins = [row[0] for row in c.fetchall()]
    if SUPERADMIN_ID not in admins:
        admins.append(SUPERADMIN_ID)
    conn.close()
    return admins

def add_admin_db(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO admins (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_admin_db(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def add_collab_button(title, url):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("INSERT INTO buttons (title, url) VALUES (?, ?)", (title, url))
    conn.commit()
    conn.close()

def get_collab_buttons():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("SELECT id, title, url FROM buttons")
    buttons = c.fetchall()
    conn.close()
    return buttons

def delete_collab_button(btn_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("DELETE FROM buttons WHERE id = ?", (btn_id,))
    conn.commit()
    conn.close()

# --- 🤖 ИНИЦИАЛИЗАЦИЯ БОТА ---
session = AiohttpSession(proxy="http://proxy.server:3128")

bot = Bot(
    token=TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# --- 📊 FSM ---
class PostState(StatesGroup):
    waiting_for_text = State()
    waiting_for_photos = State()
    confirm = State()

class AdminState(StatesGroup):
    add_admin = State()
    add_btn_title = State()
    waiting_for_edit_text = State()
    waiting_for_broadcast = State()

# --- ⌨️ КЛАВИАТУРЫ ---
def main_menu_kb(user_id):
    kb = [
        [KeyboardButton(text="📨 Создать объявление")],
        [KeyboardButton(text="🤝 Сотрудничество")]
    ]
    if user_id == SUPERADMIN_ID:
        kb.append([KeyboardButton(text="⚙️ Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def yes_no_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")]
    ], resize_keyboard=True, one_time_keyboard=True)

def finish_photos_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Готово (закончить загрузку)")]
    ], resize_keyboard=True)

def pre_publish_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Отправить на модерацию", callback_data="send_mod")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_post")]
    ])

def admin_mod_kb(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"approve_{user_id}")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{user_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{user_id}")]
    ])

def admin_panel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="start_broadcast")],
        [InlineKeyboardButton(text="👥 Администраторы", callback_data="manage_admins")],
        [InlineKeyboardButton(text="🤝 Кнопки Сотрудничества", callback_data="manage_buttons")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_panel")]
    ])

# --- 🚀 ХЕНДЛЕРЫ ---

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    add_user_db(message.from_user.id)
    await message.answer(
        "👋 Привет! Я бот для предложки.\nВыберите действие в меню:",
        reply_markup=main_menu_kb(message.from_user.id)
    )

# --- СОЗДАНИЕ ПОСТА ---
@router.message(F.text == "📨 Создать объявление")
async def start_post(message: Message, state: FSMContext):
    await state.set_state(PostState.waiting_for_text)
    await message.answer("📝 Отправьте <b>текст</b> вашего объявления:", reply_markup=ReplyKeyboardRemove())

@router.message(PostState.waiting_for_text)
async def get_text(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Ошибка: отправьте текст объявления.")
        return
    await state.update_data(text=message.text, photos=[])
    await state.set_state(PostState.waiting_for_photos)
    await message.answer("📸 Хотите добавить фото?", reply_markup=yes_no_kb())

@router.message(PostState.waiting_for_photos, F.text == "❌ Нет")
async def no_photos(message: Message, state: FSMContext):
    await show_preview(message, state)

@router.message(PostState.waiting_for_photos, F.text == "✅ Да")
async def ask_photos(message: Message, state: FSMContext):
    await message.answer("Отправляйте фото по одному (до 10 шт).\nКогда закончите, нажмите кнопку внизу.", reply_markup=finish_photos_kb())

@router.message(PostState.waiting_for_photos, F.photo)
async def save_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get('photos', [])
    if len(photos) >= 10:
        await message.answer("⚠️ Максимум 10 фото. Нажмите 'Готово'.")
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(f"📸 Фото добавлено ({len(photos)}/10). Еще или 'Готово'?")

@router.message(PostState.waiting_for_photos, F.text == "✅ Готово (закончить загрузку)")
async def finish_photos(message: Message, state: FSMContext):
    await show_preview(message, state)

@router.message(PostState.waiting_for_photos)
async def wrong_type_photo(message: Message):
    if message.text not in ["✅ Да", "❌ Нет"]:
        await message.answer("❌ Пришлите фото или нажмите кнопку 'Готово'.")

async def show_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    preview_text = f"🖥️ <b>Предварительный просмотр:</b>\n\n📝 Текст:\n{data['text']}\n\n📸 Фото: {len(data.get('photos', []))}/10\n\n🔎 Проверьте перед отправкой."
    if data.get('photos'):
        await message.answer_photo(photo=data['photos'][0], caption=preview_text, reply_markup=pre_publish_kb())
    else:
        await message.answer(preview_text, reply_markup=pre_publish_kb())
    await state.set_state(PostState.confirm)

# --- МОДЕРАЦИЯ (С ЗАПОМИНАНИЕМ СООБЩЕНИЙ) ---
@router.callback_query(F.data == "cancel_post")
async def cancel_post(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("❌ Объявление отменено.", reply_markup=main_menu_kb(callback.from_user.id))

@router.callback_query(F.data == "send_mod")
async def send_to_moderation(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = callback.from_user.id

    if not hasattr(bot, 'pending_posts'): bot.pending_posts = {}

    # Добавляем список для хранения ID сообщений у админов
    data['admin_messages'] = []
    bot.pending_posts[user_id] = data

    admins = get_admins()
    text = f"📩 <b>Новое объявление</b> от {callback.from_user.full_name} (ID: {user_id})\n\n{data['text']}"

    sent_count = 0
    for admin_id in admins:
        try:
            msg = None
            if data['photos']:
                msg = await bot.send_photo(admin_id, photo=data['photos'][0], caption=text, reply_markup=admin_mod_kb(user_id))
            else:
                msg = await bot.send_message(admin_id, text, reply_markup=admin_mod_kb(user_id))

            if msg:
                bot.pending_posts[user_id]['admin_messages'].append((admin_id, msg.message_id))

            sent_count += 1
        except Exception as e:
            print(f"Ошибка отправки админу {admin_id}: {e}")

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"📤 Отправлено {sent_count} администраторам.", reply_markup=main_menu_kb(user_id))
    await state.clear()

# --- ЛОГИКА РЕДАКТИРОВАНИЯ ---
@router.callback_query(F.data.startswith("edit_"))
async def edit_post_start(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    if not hasattr(bot, 'pending_posts') or user_id not in bot.pending_posts:
        await callback.answer("⚠️ Пост устарел.", show_alert=True)
        return
    await state.update_data(editing_user_id=user_id)
    await state.set_state(AdminState.waiting_for_edit_text)
    current_text = bot.pending_posts[user_id]['text']
    await callback.message.answer(f"📝 <b>Режим редактирования</b>\n\nТекущий текст:\n{current_text}\n\n👇 <b>Пришлите новый текст:</b>")
    await callback.answer()

@router.message(AdminState.waiting_for_edit_text)
async def edit_post_finish(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("❌ Пришлите текст.")
        return
    data = await state.get_data()
    user_id = data.get('editing_user_id')

    if hasattr(bot, 'pending_posts') and user_id in bot.pending_posts:
        bot.pending_posts[user_id]['text'] = message.text
        updated_data = bot.pending_posts[user_id]

        new_text = f"📩 <b>Объявление (ОТРЕДАКТИРОВАНО ВАМИ)</b>\nАвтор: ID {user_id}\n\n{updated_data['text']}"

        if updated_data['photos']:
             await message.answer_photo(photo=updated_data['photos'][0], caption=new_text, reply_markup=admin_mod_kb(user_id))
        else:
             await message.answer(new_text, reply_markup=admin_mod_kb(user_id))

        await message.answer("✅ Текст изменен! Опубликуйте в новом сообщении.")
    else:
        await message.answer("⚠️ Пост не найден.")
    await state.clear()

# --- ПРИНЯТИЕ РЕШЕНИЯ (С СИНХРОНИЗАЦИЕЙ) ---
@router.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_"))
async def mod_decision(callback: CallbackQuery):
    action, author_id = callback.data.split("_")
    author_id = int(author_id)

    if not hasattr(bot, 'pending_posts') or author_id not in bot.pending_posts:
        await callback.answer("⚠️ Пост устарел.", show_alert=True)
        try: await callback.message.edit_reply_markup(reply_markup=None)
        except: pass
        return

    post_data = bot.pending_posts[author_id]
    admin_name = callback.from_user.full_name

    if action == "reject":
        try: await bot.send_message(author_id, "❌ Ваше объявление отклонено.")
        except: pass
        final_text = f"❌ <b>Отклонено</b> админом {admin_name}"

    elif action == "approve":
        try:
            if post_data['photos']:
                if len(post_data['photos']) == 1:
                    await bot.send_photo(CHANNEL_ID, photo=post_data['photos'][0], caption=post_data['text'])
                else:
                    media = [InputMediaPhoto(media=p) for p in post_data['photos']]
                    media[0].caption = post_data['text']
                    await bot.send_media_group(CHANNEL_ID, media=media)
            else:
                await bot.send_message(CHANNEL_ID, post_data['text'])

            await bot.send_message(author_id, "✅ Ваше объявление опубликовано!")
            final_text = f"✅ <b>Опубликовано</b> админом {admin_name}"
        except Exception as e:
            await callback.message.answer(f"❌ Ошибка публикации: {e}")
            final_text = f"⚠️ Ошибка публикации ({admin_name})"

    # СИНХРОНИЗАЦИЯ: Удаляем кнопки у ВСЕХ админов
    messages_to_edit = post_data.get('admin_messages', [])
    for adm_chat_id, adm_msg_id in messages_to_edit:
        try:
            await bot.edit_message_reply_markup(chat_id=adm_chat_id, message_id=adm_msg_id, reply_markup=None)
        except Exception as e:
            print(f"Не удалось обновить сообщение у админа {adm_chat_id}: {e}")

    await callback.message.answer(final_text)
    del bot.pending_posts[author_id]

# --- СОТРУДНИЧЕСТВО (ВЕРНУЛ КНОПКУ!) ---
@router.message(F.text == "🤝 Сотрудничество")
async def collaboration_menu(message: Message):
    buttons_data = get_collab_buttons()
    kb_rows = []
    try:
        for _, title, url in buttons_data:
            kb_rows.append([InlineKeyboardButton(text=title, url=url)])
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        if not buttons_data: await message.answer("Раздел пока пуст.")
        else: await message.answer("🤝 Наши контакты и партнеры:", reply_markup=kb)
    except: await message.answer("⚠️ Ошибка кнопки. Удалите последнюю добавленную в админке.")

# --- РАССЫЛКА ---
@router.callback_query(F.data == "start_broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📢 <b>Режим рассылки</b>\n\nОтправьте текст (или фото с текстом), который нужно разослать всем пользователям бота.\n\nНапишите 'отмена', чтобы передумать.")
    await state.set_state(AdminState.waiting_for_broadcast)
    await callback.answer()

@router.message(AdminState.waiting_for_broadcast)
async def process_broadcast(message: Message, state: FSMContext):
    if message.text and message.text.lower() == "отмена":
        await message.answer("❌ Рассылка отменена.", reply_markup=admin_panel_kb())
        await state.clear()
        return
    users = get_all_users()
    if not users:
        await message.answer("⚠️ В базе пока нет пользователей (кроме админов).")
        await state.clear()
        return
    await message.answer(f"⏳ Начинаю рассылку на {len(users)} пользователей...")
    good = 0
    bad = 0
    for uid in users:
        try:
            await message.send_copy(chat_id=uid)
            good += 1
            await asyncio.sleep(0.05)
        except: bad += 1
    await message.answer(f"✅ <b>Рассылка завершена!</b>\n\nДоставлено: {good}\nОшибок: {bad}", reply_markup=admin_panel_kb())
    await state.clear()

# --- АДМИН ПАНЕЛЬ ---
@router.message(F.text == "⚙️ Админ-панель")
async def open_admin_panel(message: Message):
    if message.from_user.id != SUPERADMIN_ID: return
    await message.answer("⚙️ Панель управления:", reply_markup=admin_panel_kb())

@router.callback_query(F.data == "manage_admins")
async def manage_admins(callback: CallbackQuery, state: FSMContext):
    admins = get_admins()
    text = "👥 <b>Список администраторов:</b>\n" + "\n".join([f"- <code>{aid}</code>" for aid in admins])
    text += "\n\nОтправьте ID пользователя, чтобы добавить, или ID с минусом, чтобы удалить."
    await callback.message.answer(text)
    await state.set_state(AdminState.add_admin)
    await callback.answer()

@router.message(AdminState.add_admin)
async def process_admin_id(message: Message, state: FSMContext):
    try:
        uid = int(message.text)
        if uid < 0:
            remove_admin_db(abs(uid))
            await message.answer(f"🗑 Администратор {abs(uid)} удален.")
        else:
            if add_admin_db(uid): await message.answer(f"➕ Администратор {uid} добавлен.")
            else: await message.answer("⚠️ Уже есть в списке.")
    except: await message.answer("❌ Пришлите числовой ID.")
    await state.clear()
    await message.answer("⚙️ Админ-панель", reply_markup=admin_panel_kb())

@router.callback_query(F.data == "manage_buttons")
async def manage_buttons(callback: CallbackQuery, state: FSMContext):
    buttons = get_collab_buttons()
    text = "🤝 <b>Управление кнопками:</b>\n"
    for bid, title, url in buttons:
        text += f"{bid}. {title} - {url}\n"
    text += "\nЧтобы добавить: <code>Название | Ссылка</code>\nЧтобы удалить: <code>del ID</code>"
    await callback.message.answer(text)
    await state.set_state(AdminState.add_btn_title)
    await callback.answer()

@router.message(AdminState.add_btn_title)
async def process_btn(message: Message, state: FSMContext):
    txt = message.text
    if txt.lower().startswith("del "):
        try:
            bid = int(txt.split()[1])
            delete_collab_button(bid)
            await message.answer(f"🗑 Кнопка {bid} удалена.")
        except: await message.answer("❌ Пишите: del ID")
    elif "|" in txt:
        parts = txt.split("|")
        if len(parts) == 2:
            title = parts[0].strip()
            raw = parts[1].strip()
            if raw.isdigit(): url = f"tg://user?id={raw}"
            elif raw.startswith("@"): url = f"https://t.me/{raw[1:]}"
            elif "://" not in raw: url = f"https://{raw}"
            else: url = raw
            add_collab_button(title, url)
            await message.answer(f"➕ Кнопка '{title}' добавлена.\nURL: {url}")
        else: await message.answer("❌ Формат: Название | Ссылка")
    else: await message.answer("❌ Используйте разделитель |")
    await state.clear()
    await message.answer("⚙️ Админ-панель", reply_markup=admin_panel_kb())

@router.callback_query(F.data == "close_panel")
async def close_panel(callback: CallbackQuery):
    await callback.message.delete()

# --- ЗАПУСК ---
async def main():
    init_db()
    print("🤖 Бот запущен! (Final Version 6.1)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try: asyncio.run(main())
    except KeyboardInterrupt: print("Бот остановлен")
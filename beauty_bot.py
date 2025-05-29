from dotenv import load_dotenv
import os
import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes,
    MessageHandler, filters
)
from datetime import datetime, timedelta
import collections

# Завантаження змінних середовища
load_dotenv()

TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Створюємо глобальний об'єкт бота
bot = Bot(token=TOKEN)

# Ініціалізація планувальника для нагадувань
scheduler = BackgroundScheduler()
scheduler.start()

# Функція для відправки нагадувань
async def send_reminder(user_id, procedure, date, time, mode="day"):
    try:
        if mode == "day":
            text = f"⏰ Нагадування: завтра у тебе запис на *{procedure}* о {time} {date}."
        elif mode == "2h":
            text = f"⏰ Нагадування: через 2 години у тебе запис на *{procedure}* о {time} {date}."
        else:
            text = f"⏰ Нагадування: у тебе запис на *{procedure}* о {time} {date}."

        # Надсилаємо повідомлення користувачу
        await bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending reminder to {user_id}: {e}")

# Функція ініціалізації бази даних
def init_db():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()

    # Створення таблиць, якщо їх ще немає
    c.execute("""CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    phone TEXT UNIQUE,
                    first_seen TEXT,
                    last_seen TEXT,
                    total_visits INTEGER DEFAULT 1,
                    notes TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS deleted_days (
                    date TEXT PRIMARY KEY)""")

    c.execute("""CREATE TABLE IF NOT EXISTS price_list (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    price INTEGER)""")

    # Заповнення прайсу дефолтними значеннями, якщо він порожній
    c.execute("SELECT COUNT(*) FROM price_list")
    if c.fetchone()[0] == 0:
        services = [
            ("Корекція брів (воск/пінцет)", 200),
            ("Фарбування брів (фарба/хна)", 150),
            ("Корекція брів + фарбування", 300),
            ("Ламінування брів + корекція", 400),
            ("Ламінування брів + корекція + фарбування", 500),
            ("Ламінування вій без фарбування + ботокс", 400),
            ("Ламінування вій + фарбування + ботокс", 450),
            ("Ваксинг над губою", 100),
            ("Ваксинг нижня зона обличчя", 100),
            ("Фарбування вій", 150),
        ]
        c.executemany("INSERT INTO price_list (name, price) VALUES (?, ?)", services)

    # Додаємо колонку "note" до bookings, якщо її ще немає
    try:
        c.execute("ALTER TABLE bookings ADD COLUMN note TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

# Функція для оновлення або додавання клієнта
def update_or_add_client(user_name, user_phone):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")

    # Перевірка чи є клієнт у базі
    c.execute("SELECT id, total_visits FROM clients WHERE phone=?", (user_phone,))
    existing = c.fetchone()

    if existing:
        client_id, total_visits = existing
        # Якщо клієнт існує, оновлюємо його дані
        c.execute("""UPDATE clients
                    SET last_seen=?, total_visits=?
                    WHERE id = ?""", (today, total_visits + 1, client_id))
    else:
        # Якщо клієнт новий, додаємо його
        c.execute("""INSERT INTO clients (name, phone, first_seen, last_seen, total_visits)
                    VALUES (?, ?, ?, ?, 1)""", (user_name, user_phone, today, today))

    conn.commit()
    conn.close()

# Функція для отримання та форматування прайсу
def get_price_text():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()

    # Виконуємо запит для отримання всіх послуг і цін з таблиці price_list
    c.execute("SELECT name, price FROM price_list")
    rows = c.fetchall()
    conn.close()

    # Словник для відображення емодзі
    emoji_map = {
        "Корекція брів": "✏️",
        "Фарбування брів": "🎨",
        "Ламінування брів": "💎",
        "Ламінування вій": "🌟",
        "Ботокс": "💧",
        "Ваксинг": "🧊",
        "Фарбування вій": "👁️"
    }

    # Словник категорій послуг
    cats = {
        "Брови": {"emoji": "👁️", "items": []},
        "Вії": {"emoji": "🌸", "items": []},
        "Інше": {"emoji": "💫", "items": []}
    }

    # Формуємо список послуг для кожної категорії
    for name, price in rows:
        decorated_name = name
        # Перевіряємо наявність емодзі для кожної послуги
        for key in emoji_map:
            if key.lower() in name.lower():
                decorated_name = f"{emoji_map[key]} {decorated_name}"

        # Визначаємо категорію для кожної послуги
        if "брів" in name.lower():
            cats["Брови"]["items"].append((decorated_name, price))
        elif "вій" in name.lower():
            cats["Вії"]["items"].append((decorated_name, price))
        else:
            cats["Інше"]["items"].append((decorated_name, price))

    # Формуємо текстовий блок прайсу
    txt = "💎 *Прайс-лист Safroniuk Brows & Lashes*\n\n"
    for category in cats:
        if cats[category]["items"]:
            txt += f"{cats[category]['emoji']} *{category}:*\n"
            for item_name, item_price in cats[category]["items"]:
                txt += f"   └─ {item_name} — *{item_price} грн*\n"
            txt += "\n"

    # Додаємо інформацію для запису та консультації
    txt += "📲 *Запис і консультація:*\n"
    txt += "• Телефон: +380976853623\n\n"
    txt += "🔗 *Instagram:*\n"
    txt += "• @safroniuk.brows.lashes\n"
    txt += "https://www.instagram.com/safroniuk_brows_lashes\n"

    return txt
# --- ГОЛОВНЕ МЕНЮ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Створення кнопок меню
    keyboard = [
        [InlineKeyboardButton("💎 Записатися на процедуру", callback_data='book')],
        [InlineKeyboardButton("📋 Мої записи", callback_data='check_booking')],
        [InlineKeyboardButton("📋 Прайс", callback_data='show_price')],
        [InlineKeyboardButton("📸 Instagram", url=INSTAGRAM_LINK)],
        [InlineKeyboardButton("📍 Геолокація", url=MASTER_GEO_LINK)],
        [InlineKeyboardButton(f"👩‍🎨 Ваш майстер: {MASTER_NAME}", callback_data='master_phone')]
    ]

    # Додаємо кнопку адмін-сервіс, якщо користувач є адміністратором
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Адмін-сервіс", callback_data='admin_service')])

    # Вітальне повідомлення
    welcome = (
        "✨ *Beauty-бот* зустрічає тебе з посмішкою! Тут кожна красуня знаходить свій стиль і настрій 💖\n\n"
        "Обирай, що хочеш:\n"
        "— записатися на процедуру\n"
        "— подивитися свої записи\n"
        "— знайти салон на мапі\n"
        "— глянути Instagram або написати майстру\n\n"
        "🌸 Краса починається тут!"
    )

    # Перевірка на тип повідомлення
    if hasattr(update, "message") and update.message:
        await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif hasattr(update, "callback_query"):
        await update.callback_query.edit_message_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- РЕДАГУВАННЯ ГРАФІКУ (АДМІН) ---
async def edit_day_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    day = query.data.replace('edit_day_', '')  # Отримуємо вибрану дату
    context.user_data['edit_day'] = day  # Зберігаємо вибрану дату у контексті користувача

    # Підключення до БД для отримання існуючого графіка
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT times FROM schedule WHERE date = ?", (day,))  # Отримуємо існуючі години
    row = c.fetchone()
    conn.close()

    # Визначаємо вже зайняті або доступні години для вибраного дня
    chosen_times = [t.strip() for t in row[0].split(',')] if row and row[0] else []
    context.user_data['chosen_times'] = chosen_times

    # Стандартні години для робочих та вихідних днів
    weekday = datetime.strptime(day + f".{datetime.now().year}", "%d.%m.%Y").weekday()
    if weekday < 5:
        standard_times = [f"{h:02d}:00" for h in range(14, 19)]  # Робочі дні: з 14:00 до 18:00
    else:
        standard_times = [f"{h:02d}:00" for h in range(11, 19)]  # Вихідні дні: з 11:00 до 18:00

    # Створення кнопок для вибору години
    keyboard = []
    for t in standard_times:
        mark = "✅" if t in chosen_times else "☐"
        keyboard.append([InlineKeyboardButton(f"{mark} {t}", callback_data=f"settime_{t}")])

    # Кнопка для введення часу вручну та кнопка для збереження
    keyboard.append([InlineKeyboardButton("Додати вручну", callback_data="custom_time")])
    keyboard.append([InlineKeyboardButton("Зберегти", callback_data="save_times")])
    keyboard.append([InlineKeyboardButton("⬅️ Дні", callback_data="edit_schedule")])

    # Виводимо повідомлення з вибраними часами
    selected = ', '.join(chosen_times) if chosen_times else "нічого не вибрано"
    await query.edit_message_text(
        f"Вибрані години: {selected}\nНатискай на час, щоб додати або прибрати його зі списку, або введи свій.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- ДОДАТИ ЧАС ВРУЧНУ ---
async def custom_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    day = context.user_data['edit_day']

    # Запитуємо користувача, щоб він ввів час вручну
    await query.edit_message_text(
        "Введіть час вручну в форматі 'HH:MM' (наприклад, 15:00), щоб додати його в графік."
    )

    # Очікуємо відповідь від користувача
    await context.bot.register_next_step_handler(update, process_custom_time, day)

async def process_custom_time(update: Update, context: ContextTypes.DEFAULT_TYPE, day):
    time_input = update.message.text.strip()

    # Перевіряємо правильність введення
    try:
        datetime.strptime(time_input, "%H:%M")  # Перевіряємо формат часу
        # Додаємо час до вибраних годин
        if 'chosen_times' not in context.user_data:
            context.user_data['chosen_times'] = []
        context.user_data['chosen_times'].append(time_input)

        # Оновлюємо графік в БД
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        times = ', '.join(context.user_data['chosen_times'])
        c.execute("UPDATE schedule SET times = ? WHERE date = ?", (times, day))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"Час {time_input} додано до графіка.")
    except ValueError:
        await update.message.reply_text("Неправильний формат часу. Будь ласка, введіть час у форматі 'HH:MM'.")

# Функція для виконання запитів до БД
def execute_db_query(query, params=()):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute(query, params)
    result = c.fetchall()
    conn.close()
    return result

# --- CALLBACK HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Підтвердження для callback
    user_id = query.from_user.id

    # --- Редагування або перегляд примітки клієнта ---
    if query.data.startswith("edit_client_note_") or query.data.startswith("view_note_"):
        phone = query.data.replace("edit_client_note_", "").replace("view_note_", "")
        context.user_data["edit_note_phone"] = phone
        context.user_data["step"] = "edit_client_note"

        if query.data.startswith("edit_client_note_"):
            await query.message.reply_text("✍️ Введіть нову примітку для клієнта:")
        else:
            # Перегляд примітки
            booking_id = int(query.data.split("_")[-1])

            row = execute_db_query("""SELECT name, phone, date, procedure, time, status, note FROM bookings WHERE id=?""", (booking_id,))
            if row:
                name, phone, date, procedure, time, status, note = row[0]
                msg = (
                    f"👤 *{name}*\n"
                    f"📱 `{phone}`\n"
                    f"Дата: {date}\n"
                    f"Процедура: {procedure}\n"
                    f"Час: {time}\n"
                    f"Статус: {status}\n"
                )
                msg += f"\n📝 Примітка: _{note if note else 'немає'}_"
                buttons = [[InlineKeyboardButton("⬅️ До клієнтської бази", callback_data="client_base")]]
                await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
            else:
                await query.message.reply_text("Запис не знайдено. Можливо, він був видалений.")
        return

    # --- Відкриття картки клієнта ---
    if query.data.startswith("client_card_"):
        phone = query.data.replace("client_card_", "")

        row = execute_db_query("SELECT name, first_seen, last_seen, total_visits, notes FROM clients WHERE phone=?", (phone,))
        if row:
            name, first_seen, last_seen, visits, notes = row[0]
            msg = (
                f"👤 *{name}*\n"
                f"📱 `{phone}`\n"
                f"📆 Перший візит: {first_seen}\n"
                f"🔁 Візитів: {visits}\n"
                f"🗓 Останній візит: {last_seen}\n"
            )
            msg += f"\n📝 Примітка: _{notes if notes else 'немає'}_"
            buttons = [
                [InlineKeyboardButton("📝 Редагувати примітку", callback_data=f"edit_client_note_{phone}")],
                [InlineKeyboardButton("📖 Переглянути історію записів", callback_data=f"client_history_{phone}")],
                [InlineKeyboardButton("⬅️ До клієнтської бази", callback_data="client_base")]
            ]
            await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await query.message.reply_text("Клієнта не знайдено.")
        return

    # --- Перегляд історії записів клієнта ---
    if query.data.startswith("client_history_"):
        phone = query.data.replace("client_history_", "")
        rows = execute_db_query("""SELECT date, time, procedure, status FROM bookings WHERE phone=? ORDER BY date DESC""", (phone,))

        if not rows:
            await query.message.reply_text("📭 Історія записів порожня.")
            return

        msg = f"📖 *Історія записів* для `{phone}`:\n\n"
        for date, time, procedure, status in rows:
            msg += f"📅 {date} о {time} — *{procedure}* (_{status}_)\n"

        buttons = [[InlineKeyboardButton("⬅️ Назад до картки", callback_data=f"client_card_{phone}")]]
        await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # --- Повернення у клієнтську базу ---
    if query.data == "client_base":
        rows = execute_db_query("""SELECT name, phone, total_visits, last_seen FROM clients ORDER BY total_visits DESC""")

        if not rows:
            await query.message.reply_text("Клієнтська база порожня.")
            return

        for name, phone, visits, last_seen in rows:
            msg = (
                f"👤 *{name}*\n"
                f"📱 `{phone}`\n"
                f"🔁 Візитів: *{visits}*\n"
                f"🕓 Останній візит: {last_seen}"
            )
            buttons = [
                [InlineKeyboardButton("👁 Картка клієнта", callback_data=f"client_card_{phone}")],
                [InlineKeyboardButton("📝 Редагувати примітку", callback_data=f"edit_client_note_{phone}")]
            ]
            await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        return
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Підтвердження для callback

    # --- Меню для керування графіком, адмінськими функціями та прайсом ---
    if query.data == "manage_schedule":
        await manage_schedule_handler(update, context)
        return

    if query.data == "admin_service":
        await admin_service_handler(update, context)
        return

    if query.data == 'edit_schedule':
        await edit_schedule_handler(update, context)
        return

    if query.data == 'show_price':
        price_text = get_price_text()  # Функція для отримання тексту прайсу
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад до меню", callback_data="back_to_menu")]
        ]
        await query.edit_message_text(price_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    # --- Редагування прайсу ---
    if query.data == 'edit_price':
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT id, name, price FROM price_list")
        services = c.fetchall()
        conn.close()

        # Створюємо кнопки для кожної послуги з поточною ціною
        keyboard = [
            [InlineKeyboardButton(f"{name}: {price} грн", callback_data=f'edit_price_{id}')]
            for id, name, price in services
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Адмін-сервіс", callback_data="admin_service")])

        # Виводимо повідомлення з переліком послуг
        await query.edit_message_text("Оберіть послугу для зміни ціни:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # --- Редагування ціни для конкретної послуги ---
    if query.data.startswith('edit_price_'):
        service_id = int(query.data.replace('edit_price_', ''))
        context.user_data['edit_price_id'] = service_id

        # Отримуємо дані послуги для редагування
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT name, price FROM price_list WHERE id=?", (service_id,))
        name, old_price = c.fetchone()
        conn.close()

        # Підготовка повідомлення для введення нової ціни
        await query.edit_message_text(
            f"Введіть нову ціну для:\n*{name}* (зараз: {old_price} грн)", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="edit_price")]])
        )

        context.user_data['step'] = 'update_price'
        return
async def update_price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_price = update.message.text.strip()

    # Перевіряємо чи введено правильну ціну
    try:
        new_price = int(new_price)
    except ValueError:
        await update.message.reply_text("Ціна повинна бути числом. Спробуйте ще раз.")
        return

    service_id = context.user_data.get('edit_price_id')
    if not service_id:
        await update.message.reply_text("Помилка! Не знайдено послугу для зміни ціни.")
        return

    # Оновлюємо ціну в базі даних
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("UPDATE price_list SET price=? WHERE id=?", (new_price, service_id))
    conn.commit()
    conn.close()

    # Підтверджуємо зміни адміністратору
    await update.message.reply_text(f"Ціна для послуги оновлена на {new_price} грн.")

    # Повертаємося до списку послуг
    keyboard = [
        [InlineKeyboardButton("⬅️ Адмін-сервіс", callback_data="admin_service")]
    ]
    await update.message.reply_text("Ціна успішно оновлена.", reply_markup=InlineKeyboardMarkup(keyboard))

if query.data.startswith('edit_price_'):
    service_id = int(query.data.replace('edit_price_', ''))
    context.user_data['edit_price_id'] = service_id

import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

# Функція для виконання запитів до бази даних
def execute_db_query(query, params=()):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

# --- Отримання даних послуги для редагування ---
async def edit_price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    service_id = int(query.data.split('_')[1])  # ID послуги з кнопки
    context.user_data['edit_price_id'] = service_id  # Зберігаємо ID в контексті

    # Отримуємо дані послуги з бази
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT name, price FROM price_list WHERE id=?", (service_id,))
    row = c.fetchone()
    conn.close()

    if row:
        name, old_price = row
        # Підготовка повідомлення для введення нової ціни
        await query.edit_message_text(
            f"Введіть нову ціну для:\n*{name}* (зараз: {old_price} грн)",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="edit_price")]])
        )
        context.user_data['step'] = 'update_price'  # Встановлюємо крок
    else:
        await query.edit_message_text("Послуга не знайдена.")
    return

# --- Обробка введеної ціни ---
async def update_price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_price = update.message.text.strip()

    # Перевіряємо, чи введено правильну ціну
    try:
        new_price = int(new_price)
    except ValueError:
        await update.message.reply_text("Ціна повинна бути числом. Спробуйте ще раз.")
        return

    service_id = context.user_data.get('edit_price_id')
    if not service_id:
        await update.message.reply_text("Помилка! Не знайдено послугу для зміни ціни.")
        return

    # Оновлюємо ціну в базі даних
    execute_db_query("UPDATE price_list SET price=? WHERE id=?", (new_price, service_id))

    # Підтверджуємо зміни адміністратору
    await update.message.reply_text(f"Ціна для послуги оновлена на {new_price} грн.")

    # Повертаємося до списку послуг
    keyboard = [
        [InlineKeyboardButton("⬅️ Адмін-сервіс", callback_data="admin_service")]
    ]
    await update.message.reply_text("Ціна успішно оновлена.", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Перевірка записів користувача ---
async def check_booking_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT id, procedure, date, time, status, note FROM bookings WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()

    if rows:
        # Виводимо інформацію про кожен запис
        for rec in rows:
            booking_id, procedure, date, time, status, note = rec
            msg = f"✨ {procedure}\n🗓️ {date} о {time}\nСтатус: *{status}*"

            # Додаємо примітку, якщо вона є
            if note:
                msg += f"\n📝 Примітка: _{note}_"

            buttons = []
            if status == "Очікує підтвердження":
                buttons.append(InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm_{booking_id}"))
                buttons.append(InlineKeyboardButton("❌ Відмінити", callback_data=f"cancel_{booking_id}"))

            # Додаємо кнопку примітки тільки для адміна
            if user_id == ADMIN_ID:
                buttons.append(InlineKeyboardButton("📝 Примітка", callback_data=f"note_{booking_id}"))

            reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None
            await query.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await query.message.reply_text("Записів не знайдено. Час оновити свій образ! 💄")
    return

# --- Додавання/редагування примітки для запису ---
async def note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    booking_id = int(query.data.replace('note_', ''))
    context.user_data['note_booking_id'] = booking_id
    await query.message.reply_text("Введіть примітку для цього запису:")
    context.user_data['step'] = 'add_note'
    return


# --- Інші callback-обробники ---
async def edit_day_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Реалізація обробника редагування дня
    pass

async def admin_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Реалізація обробника статистики для адміністраторів
    pass

async def delete_day_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Реалізація обробника для видалення дня
    pass

async def show_stats_for_period(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str):
    # Реалізація обробника для статистики за певний період
    pass

# --- Обробка вибору години для дня (settime_) ---
async def set_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    time = query.data.replace("settime_", "")
    chosen = context.user_data.get('chosen_times', [])

    # Додаємо або видаляємо годину з вибраного списку
    if time in chosen:
        chosen.remove(time)
    else:
        chosen.append(time)

    context.user_data['chosen_times'] = chosen

    # Сформуємо кнопки для всіх стандартних годин
    weekday = datetime.strptime(context.user_data['edit_day'] + f".{datetime.now().year}", "%d.%m.%Y").weekday()
    if weekday < 5:
        times = [f"{h:02d}:00" for h in range(14, 19)]
    else:
        times = [f"{h:02d}:00" for h in range(11, 19)]

    keyboard = []
    for t in times:
        mark = "✅" if t in chosen else "☐"
        keyboard.append([InlineKeyboardButton(f"{mark} {t}", callback_data=f"settime_{t}")])

    keyboard.append([InlineKeyboardButton("Додати вручну", callback_data="custom_time")])
    keyboard.append([InlineKeyboardButton("Зберегти", callback_data="save_times")])
    keyboard.append([InlineKeyboardButton("⬅️ Дні", callback_data="edit_schedule")])

    selected = ', '.join(chosen) if chosen else "нічого не вибрано"
    await query.edit_message_text(
        f"Вибрані години: {selected}\nНатискай на час, щоб додати або прибрати його зі списку, або введи свій.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return

# --- Зберегти вибрані години ---
async def save_times_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    day = context.user_data.get('edit_day')
    times = context.user_data.get('chosen_times', [])
    times_str = ",".join(times)

    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT id FROM schedule WHERE date = ?", (day,))
    exists = c.fetchone()

    if exists:
        c.execute("UPDATE schedule SET times=? WHERE date=?", (times_str, day))
    else:
        c.execute("INSERT INTO schedule (date, times) VALUES (?, ?)", (day, times_str))

    conn.commit()
    conn.close()

    await query.edit_message_text(f"✅ Для дня {day} встановлено години: {times_str if times_str else 'жодної'}")
    context.user_data['step'] = None
    context.user_data['edit_day'] = None
    context.user_data['chosen_times'] = []
    return

# --- Ввести години вручну ---
async def custom_time_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text(
        "Введіть свої години для цього дня через кому (наприклад: 10:00,11:30,12:00):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Дні", callback_data="edit_schedule")]])
    )
    context.user_data['step'] = 'edit_times'
    return
# --- Функція для обробки натискання кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()  # Відповідаємо на callback

    # --- Перевірка записів користувача ---
    if query.data == 'check_booking':
        await check_booking_handler(update, context)
        return

    # --- Додавання/редагування примітки для запису ---
    if query.data.startswith('note_'):
        await note_handler(update, context)
        return

    # --- Редагування графіку (schedule) ---
    if query.data == 'edit_schedule':
        await edit_schedule_handler(update, context)
        return

    # --- Редагування конкретного дня ---
    if query.data.startswith('edit_day_'):
        await edit_day_handler(update, context)
        return

    # --- Повернення до головного меню ---
    if query.data == "back_to_menu":
        await start(update, context)
        return

    # --- Встановлення вихідного дня ---
    if query.data.startswith('set_dayoff_'):
        date = query.data.replace('set_dayoff_', '')
        await set_day_off(update, context, date)
        return

    # --- Перегляд календаря на сьогодні ---
    if query.data == "calendar":
        await calendar_handler(update, context)
        return

    # --- Перегляд календаря на тиждень ---
    if query.data == "weekcalendar":
        await week_calendar_handler(update, context)
        return

    # --- Видалення дня для вихідного (тільки для адміна) ---
    if query.data.startswith("delday_") and user_id == ADMIN_ID:
        date = query.data.replace('delday_', '')
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO deleted_days (date) VALUES (?)", (date,))
        conn.commit()
        conn.close()
        await query.edit_message_text(
            f"✅ День {date} зроблено вихідним! Більше недоступний для запису.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")]])
        )
        return

# --- Обробка вибору дати ---
if query.data.startswith('date_'):
    date = query.data.replace('date_', '')  # Отримуємо вибрану дату
    context.user_data['date'] = date

    # Підключення до бази даних для отримання доступних годин
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT times FROM schedule WHERE date = ?", (date,))
    row = c.fetchone()
    conn.close()

    if row:
        # Якщо є конкретні години для вибраної дати
        times = [t.strip() for t in row[0].split(',')]
    else:
        # Якщо годин немає в базі, визначаємо стандартні години
        day = datetime.strptime(date + f".{datetime.now().year}", "%d.%m.%Y").weekday()
        if day < 5:
            times = [f"{h:02d}:00" for h in range(14, 19)]  # З понеділка по п'ятницю
        else:
            times = [f"{h:02d}:00" for h in range(11, 19)]  # На вихідних інші години

    # Підключення до бази для перевірки вже заброньованих годин
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT time FROM bookings WHERE date = ?", (date,))
    booked_times = {row[0] for row in c.fetchall()}  # Використовуємо set для швидкої перевірки
    conn.close()

    # Знаходимо доступні години
    free_times = [t for t in times if t not in booked_times]

    if not free_times:
        # Якщо всі години вже зайняті
        await query.edit_message_text("😔 Всі години на цей день вже зайняті. Спробуй обрати інший день!")
        return

    # Створення кнопок для вибору вільних годин
    keyboard = [
        [InlineKeyboardButton(f"🕒 {time} | Моє ідеальне віконце 💖", callback_data=f'time_{time}')]
        for time in free_times
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад до календаря", callback_data='back_to_date')])

    # Відправка повідомлення з вільними годинами
    await query.edit_message_text(
        "👑 Час бути зіркою! Обирай ідеальний час ❤️\n"
        "Хочеш змінити дату? Натискай ⬅️",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    # Очистка кроку для подальших дій
    context.user_data['step'] = None
    return

# --- Обробка вибору часу ---
if query.data.startswith("time_"):
    time = query.data.replace("time_", "")
    context.user_data['time'] = time
    await query.edit_message_text(
        "💕 Твоя краса вже майже у мене в руках!\n"
        "Залиш, будь ласка, *Ім'я, прізвище та номер телефону*, щоб я могла тобі написати або зателефонувати ✨\n\n"
        "_Наприклад: Марія Сафронюк, +380976853623_",
        parse_mode='Markdown'
    )
    context.user_data['step'] = 'get_fullinfo'
    return

# --- Перевірка записів ---
if query.data == 'check_booking':
    user_id = query.from_user.id
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT id, procedure, date, time, status FROM bookings WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()

    if rows:
        for rec in rows:
            booking_id, procedure, date, time, status = rec
            msg = f"✨ {procedure}\n🗓️ {date} о {time}\nСтатус: *{status}*"
            buttons = []
            if status == "Очікує підтвердження":
                buttons.append(InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm_{booking_id}"))
                buttons.append(InlineKeyboardButton("❌ Відмінити", callback_data=f"cancel_{booking_id}"))
            reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None
            await query.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await query.message.reply_text("Записів не знайдено. Час оновити свій образ! 💄")
    return

# --- Повернення до вибору дати ---
if query.data == 'back_to_date':
    procedure = context.user_data.get('procedure')
    if not procedure:
        await query.edit_message_text("Вибір процедури не знайдено. Спробуйте спочатку.")
        return

    today = datetime.now().date()
    dates = []
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT date FROM deleted_days")
    deleted = {row[0] for row in c.fetchall()}
    conn.close()

    for i in range(7):
        d = today + timedelta(days=i)
        date_str = d.strftime("%d.%m")
        if date_str not in deleted:
            dates.append(date_str)

    keyboard = [
        [InlineKeyboardButton(f"📅 Обираю {date} 💋", callback_data=f'date_{date}')] for date in dates
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад до процедур", callback_data='back_to_procedure')])
    await query.edit_message_text(
        "🌸 Який день зробить тебе ще прекраснішою? Обирай сердечко на календарі й лови натхнення! Якщо раптом захочеш змінити процедуру — просто тисни ⬅️ і повертайся до вибору, бо твоя краса важлива! ✨💐",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return

# --- Обробка текстових повідомлень (редагування приміток) ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_step = context.user_data.get('step')
    text = update.message.text

    # --- РЕДАГУВАННЯ ПРИМІТКИ КЛІЄНТА ---
    if user_step == "edit_client_note" and update.effective_user.id == ADMIN_ID:
        phone = context.user_data.get("edit_note_phone")
        if not phone:
            await update.message.reply_text("Помилка! Не знайдено номер телефону для редагування примітки.")
            return

        note = text

        # Оновлюємо примітку в БД
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("UPDATE clients SET notes=? WHERE phone=?", (note, phone))
        conn.commit()
        conn.close()

        await update.message.reply_text("✅ Примітку клієнта оновлено! 📝")
        context.user_data.clear()  # Очистити user_data після операції
        return

    # --- ДОДАВАННЯ ПРИМІТКИ ДО ЗАПИСУ ---
    if user_step == 'add_note' and update.effective_user.id == ADMIN_ID:
        booking_id = context.user_data.get('note_booking_id')
        if not booking_id:
            await update.message.reply_text("Помилка! Не знайдено запис для додавання примітки.")
            return

        note_text = text

        # Оновлюємо примітку для запису в БД
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("UPDATE bookings SET note=? WHERE id=?", (note_text, booking_id))
        conn.commit()
        conn.close()


        # Додаємо кнопки для подальших дій
        keyboard = [
            [InlineKeyboardButton("👁 Переглянути примітку", callback_data=f"view_note_{booking_id}")],
            [InlineKeyboardButton("⬅️ До клієнтської бази", callback_data="client_base")]
        ]
        await update.message.reply_text(
            "Примітку збережено! 📝",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data['step'] = None  # Очистити крок після виконання
        context.user_data['note_booking_id'] = None  # Очистити ID запису
        return



    # --- ЗМІНА ЦІНИ В ПРАЙСІ ---
    if user_step == 'update_price' and update.effective_user.id == ADMIN_ID:
        service_id = context.user_data.get('edit_price_id')
        try:
            new_price = int(text.strip())  # Перетворення на ціле число
            if new_price <= 0:
                raise ValueError("Ціна повинна бути більше нуля")

            # Оновлюємо ціну для послуги в БД
            conn = sqlite3.connect('appointments.db')
            c = conn.cursor()
            c.execute("UPDATE price_list SET price=? WHERE id=?", (new_price, service_id))
            conn.commit()

            # Отримуємо ім'я послуги
            c.execute("SELECT name FROM price_list WHERE id=?", (service_id,))
            name = c.fetchone()[0]
            conn.close()

            await update.message.reply_text(f"Ціну для '{name}' оновлено на {new_price} грн!")
        except ValueError as e:
            await update.message.reply_text(f"❗️Помилка: {e}. Введіть коректну цілу суму (наприклад, 350).")
        except Exception as e:
            await update.message.reply_text(f"❗️Помилка: {e}. Будь ласка, спробуйте ще раз.")

        # Очищаємо стан
        context.user_data['step'] = None
        context.user_data['edit_price_id'] = None
        return

    # --- Додавання/редагування часу для дня (адмін) ---
    if user_step == 'edit_times' and update.effective_user.id == ADMIN_ID:
        day = context.user_data.get('edit_day')
        new_times = text.strip()

        try:
            with sqlite3.connect('appointments.db') as conn:
                c = conn.cursor()
                c.execute("SELECT id FROM schedule WHERE date = ?", (day,))
                # Якщо для цього дня вже існує запис, оновлюємо, інакше додаємо новий
                if c.fetchone():
                    c.execute("UPDATE schedule SET times=? WHERE date=?", (new_times, day))
                else:
                    c.execute("INSERT INTO schedule (date, times) VALUES (?, ?)", (day, new_times))
                conn.commit()

            await update.message.reply_text(f"✅ Для дня {day} оновлено години: {new_times}")
            context.user_data['step'] = None
            context.user_data['edit_day'] = None
        except Exception as e:
            await update.message.reply_text(f"❗️ Сталася помилка при оновленні часу: {str(e)}")
        return

    # --- Обробка запису клієнта ---
    if user_step == 'get_fullinfo':
        context.user_data['fullinfo'] = text
        procedure = context.user_data.get('procedure')
        date = context.user_data.get('date')
        time = context.user_data.get('time')
        fullinfo = context.user_data.get('fullinfo')
        user_id = update.effective_user.id

        # Обробка введеного тексту з ім'ям і телефоном
        try:
            name, phone = [s.strip() for s in fullinfo.split(',', 1)]
        except Exception:
            name, phone = fullinfo.strip(), "N/A"  # Якщо не вдалося розділити, телефон не вказано

        try:
            # Додаємо запис клієнта в базу
            with sqlite3.connect('appointments.db') as conn:
                c = conn.cursor()
                c.execute(
                    "INSERT INTO bookings (user_id, name, phone, procedure, date, time, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, name, phone, procedure, date, time, "Очікує підтвердження")
                )
                booking_id = c.lastrowid

            # Оновлюємо або додаємо клієнта
            update_or_add_client(name, phone)

            # Повідомлення користувачеві про успішне створення запису
            await update.message.reply_text(
                f"✅ Ваш запис на процедуру *{procedure}* на {date} о {time} успішно створено!\n"
                "Очікуйте підтвердження від майстра.",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"❗️ Помилка при збереженні запису: {str(e)}")
        context.user_data['step'] = None
        return
# --- Обробка запису клієнта та нагадування ---
add_to_google_sheet(name, "", phone, procedure, date, time)

keyboard = [
    [InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm_{booking_id}"),
     InlineKeyboardButton("❌ Відмінити", callback_data=f"cancel_{booking_id}")],
    [InlineKeyboardButton("💎 Записатися ще", callback_data='book')],
    [InlineKeyboardButton("📋 Мої записи", callback_data='check_booking')],
    [InlineKeyboardButton("📸 Instagram", url=INSTAGRAM_LINK)],
    [InlineKeyboardButton("📍 Геолокація", url=MASTER_GEO_LINK)],
    [InlineKeyboardButton(f"👩‍🎨 Майстер: {MASTER_NAME}", callback_data='master_phone')],
]

await update.message.reply_text(
    f"🎉 Ти записана на *{procedure}* {date} о {time}! Я вже чекаю зустрічі з тобою, ти надихаєш! 💖\n\n"
    f"👩‍🎨 Майстер: {MASTER_NAME}\n"
    f"☎️ Телефон: {MASTER_PHONE}\n"
    f"📍 Адреса: {MASTER_GEO}\n\n"
    "Якщо хочеш — підтверди чи відміні запис, або запишися ще раз 👑",
    parse_mode="Markdown",
    reply_markup=InlineKeyboardMarkup(keyboard)
)

await context.bot.send_message(
    chat_id=ADMIN_ID,
    text=f"📥 Новий запис:\nПІБ/Телефон: {name} / {phone}\nПроцедура: {procedure}\nДата: {date} о {time}"
)

# Планування нагадувань
event_time = datetime.strptime(f"{date} {time}", "%d.%m %H:%M")
remind_day = event_time - timedelta(days=1)
remind_time = remind_day.replace(hour=10, minute=0, second=0, microsecond=0)
remind_2h = event_time - timedelta(hours=2)
now = datetime.now()

# Нагадування за день
if remind_time > now:
    scheduler.add_job(
        send_reminder,
        'date',
        run_date=remind_time,
        args=[user_id, procedure, date, time, "day"]
    )

# Нагадування за 2 години
if remind_2h > now:
    scheduler.add_job(
        send_reminder,
        'date',
        run_date=remind_2h,
        args=[user_id, procedure, date, time, "2h"]
    )

# --- Обробка статистики для адміністратора ---
async def admin_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("Сьогодні", callback_data='stats_today')],
        [InlineKeyboardButton("Цей тиждень", callback_data='stats_week')],
        [InlineKeyboardButton("Цей місяць", callback_data='stats_month')],
        [InlineKeyboardButton("⬅️ Адмін-сервіс", callback_data="admin_service")],
    ]
    await query.edit_message_text(
        "Оберіть період для статистики:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# --- Показ статистики за період ---
async def show_stats_for_period(update: Update, context: ContextTypes.DEFAULT_TYPE, period):
    query = update.callback_query
    today = datetime.now().date()
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()

    # Визначення періоду для статистики
    if period == 'today':
        date_from = date_to = today
    elif period == 'week':
        date_from = today - timedelta(days=today.weekday())  # Понеділок цього тижня
        date_to = date_from + timedelta(days=6)  # Неділя цього тижня
    elif period == 'month':
        date_from = today.replace(day=1)  # Перший день поточного місяця
        date_to = today  # Сьогодні
    else:
        await query.edit_message_text("❓ Незнайомий період.")
        return

    # Отримуємо всі записи
    c.execute("SELECT name, procedure, date, time FROM bookings")
    rows = c.fetchall()
    conn.close()

    bookings = []
    for name, procedure, date_str, time in rows:
        date_obj = datetime.strptime(date_str + f'.{today.year}', "%d.%m.%Y").date()
        if date_from <= date_obj <= date_to:
            bookings.append((name, procedure, date_obj, time))

    count = len(bookings)
    unique_clients = len(set([b[0] for b in bookings]))
    procedures = [b[1] for b in bookings]

    if procedures:
        top_procs = collections.Counter(procedures).most_common(3)
        procs_str = "\n".join([f"— {p[0]} ({p[1]})" for p in top_procs])
    else:
        procs_str = "—"

    weekdays = [b[2].strftime('%A') for b in bookings]
    hours = [b[3][:2] for b in bookings]

    top_day = collections.Counter(weekdays).most_common(1)[0][0] if weekdays else "-"
    top_hour = collections.Counter(hours).most_common(1)[0][0] + ":00" if hours else "-"

    stats_text = (
        f"📊 *Статистика за обраний період*\n"
        f"Всього записів: *{count}*\n"
        f"Унікальних клієнтів: *{unique_clients}*\n\n"
        f"ТОП-3 процедури:\n{procs_str}\n\n"
        f"Найпопулярніший день тижня: *{top_day}*\n"
        f"Найпопулярніша година: *{top_hour}*"
    )

    await query.edit_message_text(stats_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Адмін-сервіс", callback_data="admin_service")]]
    ))

# --- Встановлення вихідного дня ---
async def set_day_off(update: Update, context: ContextTypes.DEFAULT_TYPE, date):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    # Вставляємо дату як вихідну в базу даних (якщо її ще немає)
    c.execute("INSERT OR IGNORE INTO deleted_days (date) VALUES (?)", (date,))
    conn.commit()
    conn.close()

    # Виводимо підтвердження користувачу
    await update.callback_query.edit_message_text(
        f"✅ День {date} зроблено вихідним! Більше недоступний для запису.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")]]
        )
    )

# --- Основна функція для запуску бота ---
def main():
    # Ініціалізація бази даних
    init_db()

    # Створення додатку
    app = ApplicationBuilder().token(TOKEN).build()

    # Додавання обробників для команд
    app.add_handler(CommandHandler("start", start))  # Стартова команда для користувачів
    app.add_handler(CallbackQueryHandler(button_handler))  # Обробка callback-запитів (кнопок)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))  # Обробка текстових повідомлень

    # Запуск бота
    app.run_polling()

if __name__ == "__main__":
    main()

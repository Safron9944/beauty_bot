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

    # Таблиця клієнтів
    c.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT UNIQUE,
            first_seen TEXT,
            last_seen TEXT,
            total_visits INTEGER DEFAULT 1,
            notes TEXT
        )
    """)

    # Таблиця днів, коли не працюємо
    c.execute("""
        CREATE TABLE IF NOT EXISTS deleted_days (
            date TEXT PRIMARY KEY
        )
    """)

    # Таблиця прайсу
    c.execute("""
        CREATE TABLE IF NOT EXISTS price_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            price INTEGER
        )
    """)


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

    # Збереження змін
    conn.commit()
    conn.close()

# Викликаємо функцію ініціалізації бази даних
init_db()

# Параметри для Instagram і майстра
INSTAGRAM_LINK = "https://www.instagram.com/safroniuk_brows_lashes?utm_source=ig_web_button_share_sheet&igsh=ZDNlZDc0MzIxNw=="
MASTER_PHONE = "+380976853623"
MASTER_NAME = "Марія"
MASTER_GEO = "вул. Київська 41, Могилів-Подільський, 24000, Україна"
MASTER_GEO_LINK = "https://maps.app.goo.gl/n6xvT6bpMcL5QjHP9"

# Старт планувальника для виконання задач
scheduler = BackgroundScheduler()
scheduler.start()

# Функція ініціалізації бази даних
def init_db():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()

    # Таблиця клієнтів
    c.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT UNIQUE,
            first_seen TEXT,
            last_seen TEXT,
            total_visits INTEGER DEFAULT 1,
            notes TEXT
        )
    """)

    # Таблиця днів, коли не працюємо
    c.execute("""
        CREATE TABLE IF NOT EXISTS deleted_days (
            date TEXT PRIMARY KEY
        )
    """)

    # Таблиця прайсу
    c.execute("""
        CREATE TABLE IF NOT EXISTS price_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            price INTEGER
        )
    """)

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
def update_or_add_client(user_name, user_phone=None):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")

    # Якщо переданий номер телефону
    if user_phone:
        # Перевірка чи є клієнт за номером телефону
        c.execute("SELECT id, total_visits FROM clients WHERE phone=?", (user_phone,))
        existing = c.fetchone()

    # Якщо номер телефону не передано, шукаємо за іменем та прізвищем
    if not existing:
        c.execute("SELECT id, total_visits FROM clients WHERE name=?", (user_name,))
        existing = c.fetchone()

    if existing:
        client_id, total_visits = existing
        # Якщо клієнт існує, оновлюємо його дані
        c.execute("""
                  UPDATE clients
                  SET last_seen=?,
                      total_visits=?
                  WHERE id = ?
                  """, (today, total_visits + 1, client_id))
    else:
        # Якщо клієнт новий, додаємо його
        c.execute("""
                  INSERT INTO clients (name, phone, first_seen, last_seen, total_visits)
                  VALUES (?, ?, ?, ?, 1)
                  """, (user_name, user_phone, today, today))

    conn.commit()
    conn.close()
## Функція для отримання та форматування прайсу
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
        if "брів" in name.lower() or "Бров" in name:
            cats["Брови"]["items"].append((decorated_name, price))
        elif "вій" in name.lower() or "Ві" in name:
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
    keyboard = [
        [InlineKeyboardButton("💎 Записатися на процедуру", callback_data='book')],
        [InlineKeyboardButton("📋 Мої записи", callback_data='check_booking')],
        [InlineKeyboardButton("📋 Прайс", callback_data='show_price')],
        [InlineKeyboardButton("📸 Instagram", url=INSTAGRAM_LINK)],
        [InlineKeyboardButton("📍 Геолокація", url=MASTER_GEO_LINK)],
        [InlineKeyboardButton(f"👩‍🎨 Ваш майстер: {MASTER_NAME}", callback_data='master_phone')]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Адмін-сервіс", callback_data='admin_service')])
    welcome = (
        "✨ *Beauty-бот* зустрічає тебе з посмішкою! Тут кожна красуня знаходить свій стиль і настрій 💖\n\n"
        "Обирай, що хочеш:\n"
        "— записатися на процедуру\n"
        "— подивитися свої записи\n"
        "— знайти салон на мапі\n"
        "— глянути Instagram або написати майстру\n\n"
        "🌸 Краса починається тут!"
    )
    if hasattr(update, "message") and update.message:
        await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- АДМІН СЕРВІС ---
# --- АДМІН СЕРВІС ---
async def manage_schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("📆 Редагувати по днях", callback_data='edit_schedule')],
        [InlineKeyboardButton("💤 Виставити вихідний", callback_data='delete_day')],
        [InlineKeyboardButton("📅 Календар на сьогодні", callback_data='calendar')],
        [InlineKeyboardButton("📆 Календар на тиждень", callback_data='weekcalendar')],
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_service")]
    ]
    text = (
        "🗓️ *Керування графіком*\n\n"
        "Оберіть дію:\n"
        "— Редагувати години роботи\n"
        "— Виставити вихідний\n"
        "— Переглянути записи на сьогодні або на тиждень"
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- ГОЛОВНЕ МЕНЮ ДЛЯ АДМІНА ---
async def admin_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🗓️ Керування графіком", callback_data="manage_schedule")],
        [InlineKeyboardButton("💸 Редагувати прайс", callback_data="edit_price")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Клієнтська база", callback_data="client_base")],
        [InlineKeyboardButton("⬅️ Головне меню", callback_data="back_to_menu")]
    ]
    text = (
        "🌟 *Адмін-сервіс*\n\n"
        "Керуйте розкладом, дивіться всі записи і тримайте красу під контролем 👑\n"
        "Оберіть дію:"
    )
    await update.callback_query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )


# --- РЕДАГУВАННЯ ГРАФІКУ (АДМІН) ---
async def edit_schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Показуємо кнопки днів на 10 днів вперед (які є у графіку або яких немає)
    today = datetime.now().date()
    dates = []

    # Підключення до БД для отримання запланованих днів
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT date FROM schedule")  # Отримуємо всі заплановані дати
    scheduled_dates = {row[0] for row in c.fetchall()}  # Формуємо множину з запланованих дат
    conn.close()

    # Генерація наступних 10 днів
    for i in range(10):
        d = today + timedelta(days=i)
        date_str = d.strftime("%d.%m")  # Форматування дати
        dates.append(date_str)

    # Створення кнопок для кожного дня
    keyboard = [
        [InlineKeyboardButton(f"🗓️ {date} {'✅' if date in scheduled_dates else '➕'}", callback_data=f'edit_day_{date}')]
        for date in dates
    ]

    # Додаємо кнопку для повернення
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")])

    # Виводимо повідомлення з кнопками
    await query.edit_message_text(
        "🌈 Обери день для редагування або додавання часу:\n"
        "— Натисни на потрібний день\n"
        "— Дні з ✅ — вже мають графік, ➕ — можна додати\n"
        "— Зміни/додай години через коми (після вибору дня)\n",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def edit_day_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    day = query.data.replace('edit_day_', '')  # Отримуємо вибрану дату
    context.user_data['edit_day'] = day  # Зберігаємо вибрану дату у контексті користувача

    # Підключення до БД для отримання існуючого графіка
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT times FROM schedule WHERE date = ?", (day,))
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

    async def edit_day_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        day = query.data.split('_')[1]  # витягуємо день з callback_data

        # 1. Витягуємо години для цього дня з БД
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT times FROM schedule WHERE date = ?", (day,))
        row = c.fetchone()
        conn.close()

        # Якщо години знайдені, перетворюємо їх на список, в іншому випадку створюємо порожній список
        chosen_times = [t.strip() for t in row[0].split(',')] if row and row[0] else []
        context.user_data['chosen_times'] = chosen_times

        # 2. Визначаємо стандартні години для дня
        weekday = datetime.strptime(day + f".{datetime.now().year}", "%d.%m.%Y").weekday()
        if weekday < 5:  # Понеділок - П'ятниця
            standard_times = [f"{h:02d}:00" for h in range(14, 19)]  # З 14:00 до 18:00
        else:  # Субота - Неділя
            standard_times = [f"{h:02d}:00" for h in range(11, 19)]  # З 11:00 до 18:00

        # 3. Створюємо кнопки з галочками
        keyboard = []
        for t in standard_times:
            mark = "✅" if t in chosen_times else "☐"
            keyboard.append([InlineKeyboardButton(f"{mark} {t}", callback_data=f"settime_{t}")])

        # Кнопка для додавання часу вручну
        keyboard.append([InlineKeyboardButton("Додати вручну", callback_data="custom_time")])

        # Кнопка для збереження змін
        keyboard.append([InlineKeyboardButton("Зберегти", callback_data="save_times")])

        # Кнопка для повернення до редагування графіка
        keyboard.append([InlineKeyboardButton("⬅️ Дні", callback_data="edit_schedule")])

        # Формуємо повідомлення для користувача
        selected = ', '.join(chosen_times) if chosen_times else "нічого не вибрано"
        await query.edit_message_text(
            f"Вибрані години: {selected}\nНатискай на час, щоб додати або прибрати його зі списку, або введи свій.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# --- ІНШІ АДМІН ФУНКЦІЇ ---

async def delete_day_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if hasattr(update, "effective_user") else update.callback_query.from_user.id
    query = update.callback_query
    if user_id != ADMIN_ID:
        await query.answer("Доступно тільки адміну", show_alert=True)
        return

    today = datetime.now().date()
    # Вибираємо найближчі 10 днів
    all_dates = [(today + timedelta(days=i)).strftime("%d.%m") for i in range(10)]

    # Беремо дати, які вже видалені
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT date FROM deleted_days")
    deleted = {row[0] for row in c.fetchall()}
    conn.close()

    # Залишаємо лише ті, що ще не вихідні
    available_dates = [d for d in all_dates if d not in deleted]

    if not available_dates:
        await query.edit_message_text(
            "🌺 Немає доступних днів для вихідного (усі вже вихідні або дати закінчились).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")]]),
        )
        return

    keyboard = [
        [InlineKeyboardButton(f"❌ {date}", callback_data=f"delday_{date}")] for date in available_dates
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")])

    await query.edit_message_text(
        "💤 Обери день для вихідного (цей день стане недоступним для запису):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступно тільки адміну.")
        return
    today = datetime.now().date()
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute(
        "SELECT date, time, procedure, name, phone, status FROM bookings "
        "WHERE date=? ORDER BY date, time", (today.strftime("%d.%m"),)
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.callback_query.edit_message_text(
            "Сьогодні записів немає 💤.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")]]),
        )
        return
    text = f"📅 Записи на {today.strftime('%d.%m.%Y')}:\n\n"
    for rec in rows:
        date, time, procedure, name, phone, status = rec
        text += (
            f"🕒 {time} — {procedure}\n"
            f"👤 {name}, 📱 {phone}\n"
            f"Статус: {status}\n\n"
        )
    await update.callback_query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")]]),
    )

async def week_calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступно тільки адміну.")
        return
    today = datetime.now().date()
    week_dates = [(today + timedelta(days=i)).strftime("%d.%m") for i in range(7)]
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute(
        f"SELECT date, time, procedure, name, phone, status FROM bookings "
        f"WHERE date IN ({','.join(['?']*len(week_dates))}) ORDER BY date, time", week_dates
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.callback_query.edit_message_text(
            "На цей тиждень записів немає 💤.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")]]),
        )
        return
    text = "📆 Записи на цей тиждень:\n\n"
    for rec in rows:
        date, time, procedure, name, phone, status = rec
        text += (
            f"📅 {date} 🕒 {time} — {procedure}\n"
            f"👤 {name}, 📱 {phone}\n"
            f"Статус: {status}\n\n"
        )
    await update.callback_query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")]]),
    )


# --- CALLBACK HANDLER ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Підтвердження для callback
    user_id = query.from_user.id

    # --- Редагування примітки клієнта ---
    if query.data.startswith("edit_client_note_"):
        phone = query.data.replace("edit_client_note_", "")
        context.user_data["edit_note_phone"] = phone
        context.user_data["step"] = "edit_client_note"
        await query.message.reply_text("✍️ Введіть нову примітку для клієнта:")
        return

    # --- Перегляд примітки ---
    if query.data.startswith("view_note_"):
        booking_id = int(query.data.split("_")[-1])

        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("""
                  SELECT name, phone, date, procedure, time, status, note
                  FROM bookings
                  WHERE id=?
                  """, (booking_id,))
        row = c.fetchone()
        conn.close()

        if row:
            name, phone, date, procedure, time, status, note = row
            msg = (
                f"👤 *{name}*\n"
                f"📱 `{phone}`\n"
                f"Дата: {date}\n"
                f"Процедура: {procedure}\n"
                f"Час: {time}\n"
                f"Статус: {status}\n"
            )
            if note:
                msg += f"\n📝 Примітка: _{note}_"
            else:
                msg += "\n📝 Примітка: _немає_"

            # Кнопка для повернення до клієнтської бази
            buttons = [[InlineKeyboardButton("⬅️ До клієнтської бази", callback_data="client_base")]]
            await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        else:
            await query.message.reply_text("Запис не знайдено. Можливо, він був видалений.")
        return

    # --- ОБРОБНИК: Редагування примітки клієнта ---

    if query.data.startswith("edit_client_note_"):
        phone = query.data.replace("edit_client_note_", "")
        context.user_data["edit_note_phone"] = phone
        context.user_data["step"] = "edit_client_note"
        await query.message.reply_text("✍️ Введіть нову примітку для клієнта:")
        return

    # --- Відкриття картки клієнта ---
    if query.data.startswith("client_card_"):
        phone = query.data.replace("client_card_", "")

        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT name, first_seen, last_seen, total_visits, notes FROM clients WHERE phone=?", (phone,))
        row = c.fetchone()
        conn.close()

        if row:
            name, first_seen, last_seen, visits, notes = row
            msg = (
                f"👤 *{name}*\n"
                f"📱 `{phone}`\n"
                f"📆 Перший візит: {first_seen}\n"
                f"🔁 Візитів: {visits}\n"
                f"🗓 Останній візит: {last_seen}\n"
            )
            if notes:
                msg += f"\n📝 Примітка: _{notes}_"

            # Кнопки для редагування примітки та перегляду історії
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

        conn = sqlite3.connect("appointments.db")
        c = conn.cursor()
        c.execute("""
                  SELECT date, time, procedure, status
                  FROM bookings
                  WHERE phone = ?
                  ORDER BY date DESC
                  """, (phone,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            await query.message.reply_text("📭 Історія записів порожня.")
            return

        # Формуємо повідомлення з історією
        msg = f"📖 *Історія записів* для `{phone}`:\n\n"
        for date, time, procedure, status in rows:
            msg += f"📅 {date} о {time} — *{procedure}* (_{status}_)\n"

        # Кнопка для повернення до картки клієнта
        buttons = [[InlineKeyboardButton("⬅️ Назад до картки", callback_data=f"client_card_{phone}")]]
        await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # --- Повернення у клієнтську базу (повний список клієнтів) ---
    if query.data == "client_base":
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("""
                  SELECT name, phone, total_visits, last_seen
                  FROM clients
                  ORDER BY total_visits DESC
                  """)
        rows = c.fetchall()
        conn.close()

        if not rows:
            await query.message.reply_text("Клієнтська база порожня.")
            return

        # Виводимо інформацію по кожному клієнту
        for name, phone, visits, last_seen in rows:
            msg = (
                f"👤 *{name}*\n"
                f"📱 `{phone}`\n"
                f"🔁 Візитів: *{visits}*\n"
                f"🕓 Останній візит: {last_seen}"
            )
            buttons = [
                [InlineKeyboardButton("👁 Картка клієнта", callback_data=f"client_card_{phone}")],
                [InlineKeyboardButton("📝 Редагувати примітку", callback_data=f"edit_client_note_{phone}")],
                [InlineKeyboardButton("⬅️ До адмін-сервісу", callback_data="admin_service")]  # Кнопка для повернення
            ]
            await query.message.reply_text(
                msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown"
            )
        return

    # --- Обробка інших запитів ---
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
        price_text = get_price_text()  # Функція для отримання тексту цін
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

    # --- Перевірка записів користувача ---
    if query.data == 'check_booking':
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
    if query.data.startswith('note_'):
        booking_id = int(query.data.replace('note_', ''))
        context.user_data['note_booking_id'] = booking_id
        await query.message.reply_text("Введіть примітку для цього запису:")
        context.user_data['step'] = 'add_note'
        return

    # --- Інші callback-обробники ---
    if query.data.startswith('edit_day_'):
        await edit_day_handler(update, context)
        return

    if query.data == 'admin_stats':
        await admin_stats_handler(update, context)
        return

    if query.data == 'delete_day':
        await delete_day_handler(update, context)
        return

    if query.data == 'stats_today':
        await show_stats_for_period(update, context, 'today')
        return

    if query.data == 'stats_week':
        await show_stats_for_period(update, context, 'week')
        return

    if query.data == 'stats_month':
        await show_stats_for_period(update, context, 'month')
        return

    # --- Обробка вибору години для дня (settime_) ---
    if query.data.startswith("settime_"):
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
    if query.data == "save_times":
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
    if query.data == "custom_time":
        await query.edit_message_text(
            "Введіть свої години для цього дня через кому (наприклад: 10:00,11:30,12:00):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Дні", callback_data="edit_schedule")]])
        )
        context.user_data['step'] = 'edit_times'
        return

    # --- Далі всі інші гілки button_handler ---
    if query.data == 'edit_schedule':
        await edit_schedule_handler(update, context)
        return

    if query.data.startswith('edit_day_'):
        await edit_day_handler(update, context)
        return

    if query.data == "back_to_menu":
        await start(update, context)
        return

    if query.data == "edit_schedule":
        await edit_schedule_handler(update, context)
        return

    if query.data.startswith('set_dayoff_'):
        date = query.data.replace('set_dayoff_', '')
        await set_day_off(update, context, date)
        return

    if query.data == "calendar":
        await calendar_handler(update, context)
        return

    if query.data == "weekcalendar":
        await week_calendar_handler(update, context)
        return

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

    async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()  # Відповідаємо на callback

        # --- Перегляд примітки ---
        if query.data.startswith("view_note_"):
            # Витягуємо ID запису з callback_data
            booking_id = int(query.data.split("_")[-1])

            # Підключаємося до БД для отримання детальної інформації про запис
            conn = sqlite3.connect('appointments.db')
            c = conn.cursor()
            c.execute("""
                      SELECT name, phone, date, procedure, time, status, note
                      FROM bookings
                      WHERE id=?
                      """, (booking_id,))
            row = c.fetchone()
            conn.close()

            if row:
                # Якщо запис знайдено, формуємо повідомлення
                name, phone, date, procedure, time, status, note = row
                msg = (
                    f"👤 *{name}*\n"
                    f"📱 `{phone}`\n"
                    f"Дата: {date}\n"
                    f"Процедура: {procedure}\n"
                    f"Час: {time}\n"
                    f"Статус: {status}\n"
                )
                if note:
                    msg += f"\n📝 Примітка: _{note}_"
                else:
                    msg += "\n📝 Примітка: _немає_"

                # Кнопки для навігації назад до картки клієнта та перегляду історії записів
                buttons = [
                    [InlineKeyboardButton("⬅️ Назад до картки клієнта", callback_data=f"client_card_{phone}")],
                    [InlineKeyboardButton("📖 Переглянути історію записів", callback_data=f"client_history_{phone}")]
                ]
                # Відправляємо повідомлення з деталями запису та кнопками
                await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
            else:
                # Якщо запис не знайдено
                await query.message.reply_text("Запис не знайдено. Можливо, він був видалений.")
            return

        # ...інші твої кнопки...

    # --- ДЛЯ КЛІЄНТА ---
    if query.data == 'book' or query.data == 'back_to_procedure':
        # Кнопки для вибору процедури
        keyboard = [
            [InlineKeyboardButton("✨ Корекція брів (ідеальна форма)", callback_data='proc_brows')],
            [InlineKeyboardButton("🎨 Фарбування + корекція брів", callback_data='proc_tint_brows')],
            [InlineKeyboardButton("🌟 Ламінування брів (WOW-ефект)", callback_data='proc_lam_brows')],
            [InlineKeyboardButton("👁️ Ламінування вій (виразний погляд)", callback_data='proc_lam_lashes')],
            [InlineKeyboardButton("⬅️ Головне меню", callback_data='back_to_menu')]
        ]
        await query.edit_message_text(
            "✨ Обери свою *бʼюті-процедуру*!\n"
            "Познач ту, яка надихає найбільше — або натискай ⬅️ щоб повернутись до головного меню 🌈💖\n\n"
            "Обіцяю, твоя краса засяє ще яскравіше! 🫶",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        context.user_data.clear()
        return

    # --- Обробка вибору процедури ---
    if query.data.startswith('proc_'):
        proc_map = {
            'proc_brows': 'Корекція брів (ідеальна форма)',
            'proc_tint_brows': 'Фарбування + корекція брів',
            'proc_lam_brows': 'Ламінування брів (WOW-ефект)',
            'proc_lam_lashes': 'Ламінування вій (виразний погляд)'
        }
        context.user_data['procedure'] = proc_map[query.data]

        # Отримуємо доступні дати
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

        if not dates:
            await query.edit_message_text("⛔ Немає доступних днів для запису. Зверніться до майстра!")
            return

        keyboard = [
            [InlineKeyboardButton(f"📅 Обираю {date} 💋", callback_data=f'date_{date}')] for date in dates
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Назад до процедур", callback_data='back_to_procedure')])
        await query.edit_message_text(
            "🌸 Який день зробить тебе ще прекраснішою? Обирай сердечко на календарі!\n"
            "Передумала? Натискай ⬅️, і обери іншу процедуру! ✨💐",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data['step'] = None
        return

    # --- Обробка вибору дати ---
    if query.data.startswith('date_'):
        date = query.data.replace('date_', '')
        context.user_data['date'] = date
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT times FROM schedule WHERE date = ?", (date,))
        row = c.fetchone()
        conn.close()

        if row:
            times = [t.strip() for t in row[0].split(',')]
        else:
            # Визначення стандартних годин
            day = datetime.strptime(date + f".{datetime.now().year}", "%d.%m.%Y").weekday()
            if day < 5:
                times = [f"{h:02d}:00" for h in range(14, 19)]
            else:
                times = [f"{h:02d}:00" for h in range(11, 19)]

        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT time FROM bookings WHERE date = ?", (date,))
        booked_times = [row[0] for row in c.fetchall()]
        conn.close()

        free_times = [t for t in times if t not in booked_times]

        if not free_times:
            await query.edit_message_text("😔 Всі години на цей день вже зайняті. Спробуй обрати інший день!")
            return

        keyboard = [
            [InlineKeyboardButton(f"🕒 {time} | Моє ідеальне віконце 💖", callback_data=f'time_{time}')]
            for time in free_times
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Назад до календаря", callback_data='back_to_date')])
        await query.edit_message_text(
            "👑 Час бути зіркою! Обирай ідеальний час ❤️\n"
            "Хочеш змінити дату? Натискай ⬅️",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
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


# --- ВВЕДЕННЯ ТЕКСТУ ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_step = context.user_data.get('step')
    text = update.message.text

    # --- РЕДАГУВАННЯ ПРИМІТКИ КЛІЄНТА ---
    if user_step == "edit_client_note" and update.effective_user.id == ADMIN_ID:
        phone = context.user_data["edit_note_phone"]
        note = update.message.text

        # Оновлюємо примітку в БД
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("UPDATE clients SET notes=? WHERE phone=?", (note, phone))
        conn.commit()
        conn.close()

        await update.message.reply_text("✅ Примітку клієнта оновлено! 📝")
        context.user_data.clear()
        return

    # --- ДОДАВАННЯ ПРИМІТКИ ДО ЗАПИСУ ---
    if user_step == 'add_note' and update.effective_user.id == ADMIN_ID:
        booking_id = context.user_data['note_booking_id']
        note_text = update.message.text

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
        context.user_data['step'] = None
        context.user_data['note_booking_id'] = None
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

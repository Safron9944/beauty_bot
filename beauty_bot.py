from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes,
    MessageHandler, filters, ConversationHandler
)
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import collections
try:
    from google_sheets import add_to_google_sheet
except ImportError:
    def add_to_google_sheet(*args, **kwargs):
        pass
# --- СТАНИ ДЛЯ ConversationHandler ---
ADDING_CONDITION, EDITING_CONDITION, EDITING_NOTE = range(3)

INSTAGRAM_LINK = "https://www.instagram.com/safroniuk_brows_lashes?utm_source=ig_web_button_share_sheet&igsh=ZDNlZDc0MzIxNw=="
MASTER_PHONE = "+380976853623"
MASTER_NAME = "Марія"
MASTER_GEO = "вул. Київська 41, Могилів-Подільський, 24000, Україна"
MASTER_GEO_LINK = "https://maps.app.goo.gl/n6xvT6bpMcL5QjHP9"

scheduler = BackgroundScheduler()
scheduler.start()

def init_db():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()

    # --- Таблиця клієнтів ---
    c.execute("""
              CREATE TABLE IF NOT EXISTS clients
              (
                  id
                  INTEGER
                  PRIMARY
                  KEY
                  AUTOINCREMENT,
                  name
                  TEXT,
                  phone
                  TEXT
                  UNIQUE,
                  user_id
                  INTEGER,
                  note
                  TEXT,
                  created_at
                  TEXT,
                  updated_at
                  TEXT
              )
              """)

    # --- Таблиця розкладу ---
    c.execute("""
              CREATE TABLE IF NOT EXISTS schedule
              (
                  id
                  INTEGER
                  PRIMARY
                  KEY
                  AUTOINCREMENT,
                  date
                  TEXT,
                  times
                  TEXT
              )
              """)

    # --- Таблиця вихідних днів ---
    c.execute("""
              CREATE TABLE IF NOT EXISTS deleted_days
              (
                  date
                  TEXT
                  PRIMARY
                  KEY
              )
              """)

    # --- Таблиця прайсу ---
    c.execute("""
              CREATE TABLE IF NOT EXISTS price_list
              (
                  id
                  INTEGER
                  PRIMARY
                  KEY
                  AUTOINCREMENT,
                  name
                  TEXT
                  UNIQUE,
                  price
                  INTEGER
              )
              """)

    # --- Таблиця записів (bookings) ---
    # --- Таблиця записів (bookings) ---
    c.execute("""
              CREATE TABLE IF NOT EXISTS bookings
              (
                  id
                  INTEGER
                  PRIMARY
                  KEY
                  AUTOINCREMENT,
                  user_id
                  INTEGER,
                  client_id
                  INTEGER,
                  name
                  TEXT,
                  phone
                  TEXT,
                  procedure
                  TEXT,
                  date
                  TEXT,
                  time
                  TEXT,
                  status
                  TEXT,
                  note
                  TEXT
              )
              """)

    # --- Таблиця особливих умов клієнта ---
    c.execute("""
              CREATE TABLE IF NOT EXISTS client_conditions
              (
                  id
                  INTEGER
                  PRIMARY
                  KEY
                  AUTOINCREMENT,
                  client_id
                  INTEGER
                  NOT
                  NULL,
                  condition_text
                  TEXT
                  NOT
                  NULL,
                  created_at
                  TIMESTAMP
                  DEFAULT
                  CURRENT_TIMESTAMP
              )
              """)

    # --- Додаємо дефолтні послуги, якщо таблиця price_list порожня ---
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

    # --- Додаємо поле note до bookings, якщо його немає (на випадок міграцій старої БД) ---
    try:
        c.execute("ALTER TABLE bookings ADD COLUMN note TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


# --- 2. Ось тут вставляєш функцію для виводу прайсу ---
def get_price_text():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT name, price FROM price_list")
    rows = c.fetchall()
    conn.close()

    emoji_map = {
        "Корекція брів": "✏️",
        "Фарбування брів": "🎨",
        "Ламінування брів": "💎",
        "фарбування": "🎨",
        "Ламінування вій": "🌟",
        "Ботокс": "💧",
        "Ваксинг": "🧊",
        "Фарбування вій": "👁️"
    }

    cats = {
        "Брови": {"emoji": "👁️", "items": []},
        "Вії": {"emoji": "🌸", "items": []},
        "Інше": {"emoji": "💫", "items": []}
    }

    for name, price in rows:
        decorated = name
        for key in emoji_map:
            if key.lower() in name.lower():
                decorated = f"{emoji_map[key]} {decorated}"
        if "брів" in name or "Бров" in name:
            cats["Брови"]["items"].append((decorated, price))
        elif "Ві" in name or "вій" in name:
            cats["Вії"]["items"].append((decorated, price))
        else:
            cats["Інше"]["items"].append((decorated, price))

    txt = "💎 *Прайс-лист Safroniuk Brows & Lashes*\n\n"
    for k in cats:
        if cats[k]["items"]:
            txt += f"{cats[k]['emoji']} *{k}:*\n"
            for n, p in cats[k]["items"]:
                txt += f"   └─ {n} — *{p} грн*\n"
            txt += "\n"
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
        [InlineKeyboardButton("🗓️ Мої записи", callback_data='check_booking')],
        [InlineKeyboardButton("💰 Прайс", callback_data='show_price')],
        [InlineKeyboardButton(f"👩‍🎨 Ваш майстер: {MASTER_NAME}", callback_data='master_phone')]
    ]
    if update.effective_user.id in ADMIN_IDS:
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
    [InlineKeyboardButton("👥 Клієнти", callback_data="clients_service")],
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
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT date FROM schedule")
    scheduled_dates = {row[0] for row in c.fetchall()}
    conn.close()
    for i in range(10):
        d = today + timedelta(days=i)
        date_str = d.strftime("%d.%m")
        dates.append(date_str)
    keyboard = [
        [InlineKeyboardButton(f"🗓️ {date} {'✅' if date in scheduled_dates else '➕'}", callback_data=f'edit_day_{date}')]
        for date in dates
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")])
    await query.edit_message_text(
        "🌈 Обери день для редагування або додавання часу:\n"
        "— Натисни на потрібний день\n"
        "— Дні з ✅ — вже мають графік, ➕ — можна додати\n"
        "— Зміни/додай години через коми (після вибору дня)\n",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def edit_day_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    day = query.data.replace('edit_day_', '')
    context.user_data['edit_day'] = day

    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT times FROM schedule WHERE date = ?", (day,))
    row = c.fetchone()
    conn.close()
    chosen_times = [t.strip() for t in row[0].split(',')] if row and row[0] else []
    context.user_data['chosen_times'] = chosen_times

    # Визначаємо стандартні години для дня
    weekday = datetime.strptime(day + f".{datetime.now().year}", "%d.%m.%Y").weekday()
    if weekday < 5:
        standard_times = [f"{h:02d}:00" for h in range(14, 19)]
    else:
        standard_times = [f"{h:02d}:00" for h in range(11, 19)]

    # Оригінальний список доступних годин, без зайнятих
    available_times = [t for t in standard_times if t not in chosen_times]

    # --- Додаємо фільтр, якщо дата = сьогодні ---
    from datetime import datetime, timedelta
    now = datetime.now()
    day_str = day.strip().replace(" ", "")
    today_str = now.strftime("%d.%m").replace(" ", "")

    print(f"DEBUG: day_str = '{day_str}', today_str = '{today_str}'")

    if day_str == today_str:
        min_time = (now + timedelta(hours=3)).time()
        filtered_times = []
        for t in available_times:
            slot_time = datetime.strptime(t, "%H:%M").time()
            print(f"DEBUG: t = {t}, slot_time = {slot_time}, min_time = {min_time}")
            if slot_time >= min_time:
                filtered_times.append(t)
        available_times = filtered_times
        print(f"DEBUG: available_times після фільтрації: {available_times}")

    # --- Формуємо клавіатуру тільки з доступних годин ---
    if available_times:
        keyboard = [
            [InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in available_times
        ]
        await query.edit_message_text(
            "Оберіть час для запису:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.edit_message_text("На обраний день немає доступних вільних годин. Спробуйте іншу дату.")

    # 3. Створюємо кнопки з галочками
    keyboard = []
    for t in standard_times:
        mark = "✅" if t in chosen_times else "☐"
        keyboard.append([InlineKeyboardButton(f"{mark} {t}", callback_data=f"settime_{t}")])
    keyboard.append([InlineKeyboardButton("Додати вручну", callback_data="custom_time")])
    keyboard.append([InlineKeyboardButton("Зберегти", callback_data="save_times")])
    keyboard.append([InlineKeyboardButton("⬅️ Дні", callback_data="edit_schedule")])

    selected = ', '.join(chosen_times) if chosen_times else "нічого не вибрано"
    await query.edit_message_text(
        f"Вибрані години: {selected}\nНатискай на час, щоб додати або прибрати його зі списку, або введи свій.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
# --- ДОДАТИ УМОВУ ---
# --- ДОДАВАННЯ УМОВИ ---
async def add_condition_start(update, context):
    query = update.callback_query
    await query.answer()

    client_id = int(query.data.split("_")[-1])
    context.user_data["condition_client_id"] = client_id

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"client_{client_id}")]
    ]

    await query.edit_message_text(
        "➕ Введіть текст нової умови:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADDING_CONDITION

async def save_condition(update, context):
    text = update.message.text.strip()
    client_id = context.user_data.get("condition_client_id")

    if not text:
        await update.message.reply_text("⚠️ Текст не може бути порожнім.")
        return ADDING_CONDITION

    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("INSERT INTO client_conditions (client_id, condition_text) VALUES (?, ?)", (client_id, text))
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Умову додано.")
    await show_client_card(update, context, client_id)
    return ConversationHandler.END

# --- РЕДАГУВАННЯ УМОВИ ---
async def edit_condition_start(update, context):
    query = update.callback_query
    await query.answer()

    condition_id = int(query.data.split("_")[-1])
    context.user_data["edit_condition_id"] = condition_id

    await query.edit_message_text("✏️ Введіть новий текст для цієї умови:")
    return EDITING_CONDITION


async def save_edited_condition(update, context):
    condition_id = context.user_data.get("edit_condition_id")
    new_text = update.message.text.strip()

    if not new_text:
        await update.message.reply_text("⚠️ Текст не може бути порожнім. Спробуйте ще раз.")
        return EDITING_CONDITION

    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("UPDATE client_conditions SET condition_text=? WHERE id=?", (new_text, condition_id))
    conn.commit()

    c.execute("SELECT client_id FROM client_conditions WHERE id=?", (condition_id,))
    row = c.fetchone()
    conn.close()

    if row:
        client_id = row[0]
        await update.message.reply_text("✅ Умову оновлено!")
        await show_client_card(update, context, client_id)
    else:
        await update.message.reply_text("⚠️ Помилка: клієнта не знайдено.")
    return ConversationHandler.END

# --- РЕДАГУВАННЯ НОТАТКИ ---
async def edit_note_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    client_id = int(query.data.split("_")[-1])
    context.user_data['step'] = 'edit_note'
    context.user_data['edit_note_client_id'] = client_id

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"client_{client_id}")]
    ]

    await query.edit_message_text(
        "📝 Введіть нову нотатку для клієнта:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def save_edited_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text.strip()
    client_id = context.user_data.get("edit_note_client_id")

    if not note:
        await update.message.reply_text("⚠️ Нотатка не може бути порожньою.")
        return EDITING_NOTE

    conn = sqlite3.connect("appointments.db")
    c = conn.cursor()
    c.execute("UPDATE clients SET note=? WHERE id=?", (note, client_id))
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Нотатку оновлено.")
    await show_client_card(update, context, client_id)
    return ConversationHandler.END

# --- ПІДТВЕРДЖЕННЯ ТА ВИДАЛЕННЯ ---
async def delete_condition(update, context):
    query = update.callback_query
    await query.answer()

    cond_id = int(query.data.split("_")[-1])
    context.user_data["pending_delete_condition_id"] = cond_id

    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT condition_text FROM client_conditions WHERE id=?", (cond_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        await query.edit_message_text("⚠️ Умову не знайдено.")
        return

    text = row[0]
    keyboard = [
        [
            InlineKeyboardButton("✅ Так, видалити", callback_data="confirm_delete"),
            InlineKeyboardButton("❌ Скасувати", callback_data="cancel_delete")
        ]
    ]

    await query.edit_message_text(
        f"❗ Ви справді хочете видалити умову:\n\n“{text}”",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def confirm_delete(update, context):
    query = update.callback_query
    await query.answer()

    cond_id = context.user_data.get("pending_delete_condition_id")
    if not cond_id:
        await query.edit_message_text("⚠️ Немає умови для видалення.")
        return

    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT client_id FROM client_conditions WHERE id=?", (cond_id,))
    row = c.fetchone()

    if not row:
        await query.edit_message_text("⚠️ Умову вже видалено.")
        return

    client_id = row[0]
    c.execute("DELETE FROM client_conditions WHERE id=?", (cond_id,))
    conn.commit()
    conn.close()

    await query.edit_message_text("🗑️ Умову видалено.")
    await show_client_card(update, context, client_id)

async def cancel_delete(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❎ Видалення скасовано.")

async def clients_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Очищуємо всі стани для уникнення конфліктів
    context.user_data.pop('client_add', None)
    context.user_data.pop('client_search', None)
    keyboard = [
        [InlineKeyboardButton("🏆 Топ-10 клієнтів", callback_data="clients_top")],
        [InlineKeyboardButton("➕ Додати нового клієнта", callback_data="client_add")],
        [InlineKeyboardButton("🔍 Знайти клієнта", callback_data="client_search_start")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_service")]
    ]
    text = "👥 *Клієнти — меню адміністратора*\nОберіть дію:"
    await update.callback_query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )

async def clients_top_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("""
        SELECT clients.id, clients.name, clients.phone, COUNT(bookings.id) as num, 
            COALESCE(SUM(price_list.price), 0)
        FROM clients
        LEFT JOIN bookings ON bookings.client_id = clients.id
        LEFT JOIN price_list ON bookings.procedure = price_list.name
        GROUP BY clients.id
        ORDER BY num DESC, clients.name
        LIMIT 10
    """)
    rows = c.fetchall()
    conn.close()
    text = "🏆 *Топ-10 клієнтів:*\n"
    buttons = []
    for idx, (client_id, name, phone, num, total) in enumerate(rows, 1):
        text += f"{idx}. {name} — {num} записів, {total} грн\n"
        buttons.append([InlineKeyboardButton(f"{name}", callback_data=f"client_{client_id}")])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="clients_service")])
    await update.callback_query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown"
    )

async def client_add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('client_search', None)  # Важливо!
    context.user_data['client_add'] = {'step': 'name'}
    await update.callback_query.edit_message_text(
        "Введіть ім'я та прізвище нового клієнта:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад", callback_data="clients_service")]
        ])
    )

async def client_add_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get('client_add')
    if not data:
        return
    if data['step'] == 'name':
        context.user_data['client_add']['name'] = update.message.text.strip()
        context.user_data['client_add']['step'] = 'phone'
        await update.message.reply_text("Введіть телефон клієнта (наприклад: +380...):")
        return
    if data['step'] == 'phone':
        context.user_data['client_add']['phone'] = update.message.text.strip()
        context.user_data['client_add']['step'] = 'note'
        await update.message.reply_text("Додайте примітку (або напишіть 'пропустити'):")
        return
    if data['step'] == 'note':
        note = update.message.text.strip()
        if note.lower() == 'пропустити':
            note = ""
        context.user_data['client_add']['note'] = note
        # ---- Ось тут перевірка на дублі ----
        name = context.user_data['client_add']['name']
        phone = context.user_data['client_add']['phone']
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT id FROM clients WHERE phone = ? OR name = ?", (phone, name))
        duplicate = c.fetchone()
        if duplicate:
            await update.message.reply_text("Клієнт з таким телефоном або ПІБ вже існує! Ось його картка:")
            await show_client_card(update, context, duplicate[0])
            conn.close()
            context.user_data.pop('client_add', None)
            return
        # ------------------------------------
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            c.execute(
                "INSERT INTO clients (name, phone, note, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (name, phone, note, now, now)
            )
            conn.commit()
            client_id = c.lastrowid
            await update.message.reply_text("Клієнта додано! Ось його картка:")
            await show_client_card(update, context, client_id)
        except sqlite3.IntegrityError:
            await update.message.reply_text("Клієнт із цим телефоном вже існує!")
        conn.close()
        context.user_data.pop('client_add', None)
        return


async def client_search_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('client_add', None)   # Важливо!
    context.user_data['client_search'] = True
    await update.callback_query.edit_message_text("Введіть ім'я/прізвище або телефон клієнта:")

async def client_search_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('client_search'):
        return
    search = update.message.text.strip().lower()
    import re
    def clean_phone(phone):
        return re.sub(r"\D", "", phone)
    search_clean = clean_phone(search)
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("""
        SELECT id, name, phone FROM clients 
        WHERE LOWER(name) LIKE ? OR REPLACE(REPLACE(REPLACE(REPLACE(phone, '+', ''), ' ', ''), '-', ''), '(', '') LIKE ?
        LIMIT 10
    """, (f"%{search}%", f"%{search_clean}%"))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("Клієнта не знайдено.")
    else:
        buttons = [
            [InlineKeyboardButton(f"{name} ({phone})", callback_data=f"client_{client_id}")]
            for client_id, name, phone in rows
        ]
        buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="clients_service")])
        await update.message.reply_text("Оберіть клієнта:", reply_markup=InlineKeyboardMarkup(buttons))
    context.user_data.pop('client_search', None)


async def show_client_card(update, context):
    import sqlite3
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    query = update.callback_query
    await query.answer()
    client_id = int(query.data.replace("client_", ""))  # <-- ОТРИМУЄМО client_id З callback_data

    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()

    # --- Отримуємо інформацію про клієнта ---
    c.execute("SELECT name, phone, note FROM clients WHERE id=?", (client_id,))
    result = c.fetchone()
    if not result:
        await context.bot.send_message(chat_id=update.effective_user.id, text="❌ Клієнта не знайдено.")
        conn.close()
        return

    name, phone, note = result

    # --- Дата останнього запису ---
    c.execute("SELECT MAX(date) FROM bookings WHERE client_id=?", (client_id,))
    last_visit = c.fetchone()[0] or "—"

    # --- Особливі умови ---
    c.execute("SELECT condition_text FROM client_conditions WHERE client_id=?", (client_id,))
    conditions = [row[0] for row in c.fetchall()]
    special_conditions = '\n'.join(f"— {c}" for c in conditions) if conditions else "—"

    conn.close()

    # --- Текст повідомлення ---
    text = (
        f"👤 *{name}*\n"
        f"📞 {phone}\n"
        f"📅 Останній візит: {last_visit}\n"
        f"⚠️ Умови:\n{special_conditions}\n\n"
        f"📝 Примітка:\n{note or '—'}"
    )

    # --- Кнопки ---
    keyboard = [
        [InlineKeyboardButton("📅 Записати на процедуру", callback_data=f"client_book_{client_id}")],
        [InlineKeyboardButton("➕ Додати умову", callback_data=f"addcond_{client_id}")],
        [InlineKeyboardButton("📋 Всі умови", callback_data=f"listcond_{client_id}")],
        [InlineKeyboardButton("✏️ Змінити нотатку", callback_data=f"editnote_{client_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_clients")]
    ]

    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )




async def show_client_card_by_phone(update, context, phone):
    import re
    import sqlite3

    # Нормалізуємо номер (залишаємо тільки цифри)
    clean = lambda x: re.sub(r"\D", "", x)
    phone_clean = clean(phone)

    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    # Знаходимо клієнта по номеру (у БД теж чистимо телефон)
    c.execute("""
        SELECT id FROM clients 
        WHERE REPLACE(REPLACE(REPLACE(REPLACE(phone, '+', ''), ' ', ''), '-', ''), '(', '') = ?
        LIMIT 1
    """, (phone_clean,))
    row = c.fetchone()
    conn.close()

    if row:
        client_id = row[0]
        await show_client_card(update, context, client_id)
    else:
        if hasattr(update, "callback_query") and update.callback_query:
            await update.callback_query.edit_message_text("Клієнта з цим номером не знайдено.")
        else:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text="Клієнта з цим номером не знайдено."
            )

    # --- Додавання примітки до запису (старий сценарій) ---
    if user_step == 'add_note' and update.effective_user.id in ADMIN_IDS:
        booking_id = context.user_data['note_booking_id']
        note_text = update.message.text
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("UPDATE bookings SET note=? WHERE id=?", (note_text, booking_id))
        conn.commit()
        conn.close()
        await update.message.reply_text("Примітку збережено! 📝")
        context.user_data['step'] = None
        context.user_data['note_booking_id'] = None
        return

    # --- Можеш додати інші сценарії user_step нижче, якщо потрібно ---

    # --- Якщо нічого не підійшло ---
    await update.message.reply_text("Оберіть дію за допомогою кнопок нижче та подаруйте собі красу! 💖")
# --- ІНШІ АДМІН ФУНКЦІЇ ---
async def delete_day_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if hasattr(update, "effective_user") else update.callback_query.from_user.id
    query = update.callback_query
    if user_id not in ADMIN_IDS:
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")]])
        )
        return

    keyboard = [
        [InlineKeyboardButton(f"❌ {date}", callback_data=f"delday_{date}")] for date in available_dates
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")])

    await query.edit_message_text(
        "💤 Обери день для вихідного (цей день стане недоступним для запису):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
# --- ВИВОДИТЬ УМОВИ КЛІЄНТА ---
async def list_conditions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import sqlite3
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    query = update.callback_query
    await query.answer()

    client_id = int(query.data.split("_")[-1])

    conn = sqlite3.connect("appointments.db")
    c = conn.cursor()
    c.execute("SELECT id, condition_text FROM client_conditions WHERE client_id=?", (client_id,))
    conditions = c.fetchall()
    conn.close()

    if not conditions:
        await query.edit_message_text(
            "🔍 У цього клієнта ще немає жодної умови.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Додати умову", callback_data=f"addcond_{client_id}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data=f"client_{client_id}")]
            ])
        )
        return

    text = "🧾 *Умови клієнта:*\n\n"
    keyboard = []

    for condition_id, condition_text in conditions:
        text += f"• {condition_text}\n"
        keyboard.append([
            InlineKeyboardButton("📝 Змінити", callback_data=f"editcond_{condition_id}"),
            InlineKeyboardButton("❌ Видалити", callback_data=f"delcond_{condition_id}")
        ])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"client_{client_id}")])

    await query.edit_message_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
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
        await update.callback_query.edit_message_text("Сьогодні записів немає 💤.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")]])
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
    await update.callback_query.edit_message_text(text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")]])
    )

async def week_calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
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
        await update.callback_query.edit_message_text("На цей тиждень записів немає 💤.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")]])
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
    await update.callback_query.edit_message_text(text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")]])
    )

# --- CALLBACK HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    print("=== [CALLBACK TRIGGERED] ===")
    print(f"User ID: {user_id}")
    print(f"Callback Data: {query.data}")

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
        price_text = get_price_text()
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад до меню", callback_data="back_to_menu")]
        ]
        await query.edit_message_text(price_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

        # ...інші if...

    # Ось тут додаєш блоки для редагування прайсу
    if query.data == 'edit_price':
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT id, name, price FROM price_list")
        services = c.fetchall()
        conn.close()
        keyboard = [
            [InlineKeyboardButton(f"{name}: {price} грн", callback_data=f'edit_price_{id}')]
            for id, name, price in services
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Адмін-сервіс", callback_data="admin_service")])
        await query.edit_message_text("Оберіть послугу для зміни ціни:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if query.data.startswith('edit_price_'):
        service_id = int(query.data.replace('edit_price_', ''))
        context.user_data['edit_price_id'] = service_id
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT name, price FROM price_list WHERE id=?", (service_id,))
        name, old_price = c.fetchone()
        conn.close()
        await query.edit_message_text(
            f"Введіть нову ціну для:\n*{name}* (зараз: {old_price} грн)", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="edit_price")]])
        )
        context.user_data['step'] = 'update_price'
        return

    if query.data == 'check_booking':
        user_id = query.from_user.id
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT id, procedure, date, time, status, note FROM bookings WHERE user_id=?", (user_id,))
        rows = c.fetchall()
        conn.close()
        if rows:
            for rec in rows:
                booking_id, procedure, date, time, status, note = rec
                msg = f"✨ {procedure}\n🗓️ {date} о {time}\nСтатус: *{status}*"
                # Додаємо примітку тільки якщо вона є
                if note:
                    msg += f"\n📝 Примітка: _{note}_"
                buttons = []
                if status == "Очікує підтвердження":
                    buttons.append(InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm_{booking_id}"))
                    buttons.append(InlineKeyboardButton("❌ Відмінити", callback_data=f"cancel_{booking_id}"))
                # Додаємо кнопку примітки тільки для адміна
                if user_id == ADMIN_IDS:
                    buttons.append(InlineKeyboardButton("📝 Примітка", callback_data=f"note_{booking_id}"))
                reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None
                await query.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await query.message.reply_text("Записів не знайдено. Час оновити свій образ! 💄")
        return

    if query.data.startswith('note_'):
        booking_id = int(query.data.replace('note_', ''))
        context.user_data['note_booking_id'] = booking_id
        await query.message.reply_text("Введіть примітку для цього запису:")
        context.user_data['step'] = 'add_note'
        return

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
    if query.data == "clients_service":
        await clients_service_handler(update, context)
        return
    if query.data == "clients_top":
        await clients_top_handler(update, context)
        return
    if query.data.startswith("clientphone_"):
        phone = query.data.replace("clientphone_", "")
        await show_client_card_by_phone(update, context, phone)
        return
    if query.data == "client_add":
        await client_add_handler(update, context)
        return
    if query.data == "client_search_start":
        await client_search_start_handler(update, context)
        return


    # Далі всі інші гілки button_handler...
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

    if query.data.startswith("delday_") and user_id == ADMIN_IDS:
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

    if query.data.startswith("client_note_"):
        client_id = int(query.data.replace("client_note_", ""))
        # Вибираємо ім’я клієнта
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT name FROM clients WHERE id=?", (client_id,))
        row = c.fetchone()
        conn.close()
        name = row[0] if row else "Невідомий"
        await query.message.reply_text(
            f"Введіть нову примітку для {name}:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data=f"client_{client_id}")]
            ])
        )
        context.user_data['edit_note_client_id'] = client_id
        context.user_data['step'] = 'edit_note'
        return

    if query.data.startswith("client_history_"):
        client_id = int(query.data.replace("client_history_", ""))
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        # Вибираємо ім'я клієнта
        c.execute("SELECT name FROM clients WHERE id=?", (client_id,))
        row = c.fetchone()
        name = row[0] if row else "Невідомий"
        # Вибираємо всі записи цього клієнта
        c.execute("SELECT procedure, date, time, status FROM bookings WHERE client_id=? ORDER BY date DESC, time DESC",
                  (client_id,))
        visits = c.fetchall()
        conn.close()
        if visits:
            msg = f"📋 *Історія записів для* _{name}_:\n\n"
            for proc, date, time, status in visits:
                msg += f"• *{date}* о *{time}* — {proc} (_{status}_)\n"
        else:
            msg = f"У клієнта {name} ще не було записів."
        keyboard = [
            [InlineKeyboardButton("⬅️ До картки клієнта", callback_data=f"client_{client_id}")]
        ]
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    if query.data == 'back_to_procedure':
        # Для адміна — повернення до вибору процедур клієнта
        client_id = context.user_data.get('booking_client_id')
        if not client_id:
            # На випадок, якщо контекст не збережено — можна вивести помилку або повернутись до головного меню
            await query.edit_message_text(
                "Помилка: Клієнт не знайдений. Спробуйте ще раз або поверніться до головного меню.")
            return
        with sqlite3.connect('appointments.db') as conn:
            c = conn.cursor()
            c.execute("SELECT name FROM clients WHERE id=?", (client_id,))
            row = c.fetchone()
        name = row[0] if row else "Невідомий"
        keyboard = [
            [InlineKeyboardButton("✨ Корекція брів (ідеальна форма)", callback_data='proc_brows')],
            [InlineKeyboardButton("🎨 Фарбування + корекція брів", callback_data='proc_tint_brows')],
            [InlineKeyboardButton("🌟 Ламінування брів (WOW-ефект)", callback_data='proc_lam_brows')],
            [InlineKeyboardButton("👁️ Ламінування вій (виразний погляд)", callback_data='proc_lam_lashes')],
            [InlineKeyboardButton("⬅️ Назад до картки клієнта", callback_data=f'client_{client_id}')]
        ]
        await query.edit_message_text(
            f"Оберіть процедуру для запису клієнта {name}:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    if query.data.startswith("client_book_"):
        try:
            print("==> [client_book_] step before:", context.user_data.get('step'))
            client_id = int(query.data.replace("client_book_", ""))
            with sqlite3.connect('appointments.db') as conn:
                c = conn.cursor()
                c.execute("SELECT name FROM clients WHERE id=?", (client_id,))
                row = c.fetchone()
            print("==> [client_book_] client row:", row)
            name = row[0] if row else "Невідомий"
            context.user_data['booking_client_id'] = client_id
            context.user_data['step'] = 'book_procedure'
            print("==> [client_book_] step after:", context.user_data.get('step'))
            print("==> [client_book_] booking_client_id:", context.user_data.get('booking_client_id'))
            keyboard = [
                [InlineKeyboardButton("✨ Корекція брів (ідеальна форма)", callback_data='proc_brows')],
                [InlineKeyboardButton("🎨 Фарбування + корекція брів", callback_data='proc_tint_brows')],
                [InlineKeyboardButton("🌟 Ламінування брів (WOW-ефект)", callback_data='proc_lam_brows')],
                [InlineKeyboardButton("👁️ Ламінування вій (виразний погляд)", callback_data='proc_lam_lashes')],
                [InlineKeyboardButton("⬅️ Назад до картки клієнта", callback_data=f'client_{client_id}')]
            ]
            # ось тут ти відправляєш повідомлення, і тільки тут створюй result:
            result = await context.bot.send_message(
                chat_id=query.message.chat.id,
                text=f"Оберіть процедуру для запису клієнта {name}:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            print("==> [client_book_] send_message sent, result:", result)
        except Exception as e:
            import traceback
            print("==> [client_book_] ERROR:", e)
            print(traceback.format_exc())
        return

    if query.data.startswith('client_'):
        client_id = int(query.data.replace("client_", ""))
        await show_client_card(update, context, client_id)
        return
    # --- І далі інші клієнтські функції... ---
    # --- ДЛЯ КЛІЄНТА ---
    if query.data == 'book' or query.data == 'back_to_procedure':
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

    if query.data.startswith('proc_'):
        print("==> [proc_] step before:", context.user_data.get('step'))
        print("==> [proc_] booking_client_id:", context.user_data.get('booking_client_id'))
        proc_map = {
            'proc_brows': 'Корекція брів (ідеальна форма)',
            'proc_tint_brows': 'Фарбування + корекція брів',
            'proc_lam_brows': 'Ламінування брів (WOW-ефект)',
            'proc_lam_lashes': 'Ламінування вій (виразний погляд)'
        }
        context.user_data['procedure'] = proc_map[query.data]
        if context.user_data.get('step') == 'book_procedure':
            context.user_data['step'] = 'book_date'
        else:
            context.user_data['step'] = None
        print("==> [proc_] step after:", context.user_data.get('step'))
        print("==> [proc_] procedure:", context.user_data.get('procedure'))
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
        if context.user_data.get('booking_client_id'):
            keyboard.append([InlineKeyboardButton("⬅️ Назад до картки клієнта",
                                                  callback_data=f'client_{context.user_data["booking_client_id"]}')])
        else:
            keyboard.append([InlineKeyboardButton("⬅️ Назад до процедур", callback_data='back_to_procedure')])
        await query.edit_message_text(
            "🌸 Який день підходить для запису? Обирай дату!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if query.data.startswith('date_'):
        print("==> [date_] step before:", context.user_data.get('step'))
        print("==> [date_] booking_client_id:", context.user_data.get('booking_client_id'))
        print("==> [date_] procedure:", context.user_data.get('procedure'))
        date = query.data.replace('date_', '')
        context.user_data['date'] = date
        if context.user_data.get('step') == 'book_date':
            context.user_data['step'] = 'book_time'
        else:
            context.user_data['step'] = None
        print("==> [date_] step after:", context.user_data.get('step'))
        print("==> [date_] date:", context.user_data.get('date'))
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT times FROM schedule WHERE date = ?", (date,))
        row = c.fetchone()
        conn.close()
        if row:
            times = [t.strip() for t in row[0].split(',')]
        else:
            day = datetime.strptime(date + f".{datetime.now().year}", "%d.%m.%Y").weekday()
            if day < 5:
                times = [f"{h:02d}:00" for h in range(14, 19)]
            else:
                times = [f"{h:02d}:00" for h in range(11, 19)]

        # ---- ФІЛЬТРУЄМО години для сьогодні ----
        from datetime import datetime, timedelta
        today_str = datetime.now().strftime("%d.%m")
        if date == today_str:
            now = datetime.now()
            min_time = (now + timedelta(hours=3)).time()
            filtered_times = []
            for t in times:
                slot_time = datetime.strptime(t, "%H:%M").time()
                if slot_time >= min_time:
                    filtered_times.append(t)
            times = filtered_times
        # ---- /ФІЛЬТР ----

        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT time FROM bookings WHERE date = ?", (date,))
        booked_times = [row[0] for row in c.fetchall()]
        conn.close()
        free_times = [t for t in times if t not in booked_times]
        if not free_times:
            await query.edit_message_text(
                "😔 Всі години на цей день вже зайняті або недоступні за часом. Спробуй обрати інший день!")
            return
        keyboard = [
            [InlineKeyboardButton(f"🕒 {time} | Моє ідеальне віконце 💖", callback_data=f'time_{time}')]
            for time in free_times
        ]
        if context.user_data.get('booking_client_id'):
            keyboard.append([InlineKeyboardButton("⬅️ Назад до вибору дати", callback_data='back_to_procedure')])
        else:
            keyboard.append([InlineKeyboardButton("⬅️ Назад до календаря", callback_data='back_to_date')])
        await query.edit_message_text(
            "👑 Час бути зіркою! Обирай ідеальний час ❤️\n"
            "Хочеш змінити дату? Натискай ⬅️",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

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

    # --- ВИБІР ЧАСУ ДЛЯ ЗАПИСУ (АДМІН або ЗВИЧАЙНИЙ КЛІЄНТ) ---
    if query.data.startswith('time_'):
        time = query.data.replace('time_', '')
        procedure = context.user_data.get('procedure')
        date = context.user_data.get('date')

        if context.user_data.get('booking_client_id'):
            # Адмін: записуємо клієнта напряму
            print("==> [time_] step before:", context.user_data.get('step'))
            print("==> [time_] booking_client_id:", context.user_data.get('booking_client_id'))
            print("==> [time_] procedure:", procedure)
            print("==> [time_] date:", date)
            print("==> [time_] time:", time)
            client_id = context.user_data.get('booking_client_id')
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status = "Запис підтверджено"
            conn = sqlite3.connect('appointments.db')
            c = conn.cursor()
            c.execute("""
                      INSERT INTO bookings (user_id, client_id, procedure, date, time, status, note)
                      VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      (None, client_id, procedure, date, time, status, ""))
            conn.commit()
            conn.close()
            print("==> [time_] booking DONE!")
            keyboard = [
                [InlineKeyboardButton("⬅️ До картки клієнта", callback_data=f"client_{client_id}")]
            ]
            await query.edit_message_text(
                "✅ Клієнта записано на процедуру!\n\n"
                "Можна повернутись до картки клієнта для наступних дій.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            context.user_data.clear()
            return
        else:
            # Користувач: просимо ввести ПІБ і телефон
            if not procedure or not date:
                await query.edit_message_text("⚠️ Сталася помилка. Будь ласка, почніть запис спочатку.")
                context.user_data.clear()
                return

            context.user_data['time'] = time
            context.user_data['step'] = 'get_fullinfo'
            await query.edit_message_text(
                f"📋 Введіть *ПІБ та номер телефону* через пробіл, наприклад:\n\n"
                f"`Ольга Чарівна +380961234567`",
                parse_mode="Markdown"
            )

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

    if query.data == "master_phone":
        text = (
            f"👩‍🎨 *Ваш майстер: {MASTER_NAME}*\n"
            f"☎️ Телефон: `{MASTER_PHONE}`\n"
            "Завжди рада допомогти — телефонуйте або пишіть у Viber/Telegram! 💬"
        )
        await query.edit_message_text(text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("📸 Instagram", url=INSTAGRAM_LINK)],
                    [InlineKeyboardButton("📍 Геолокація", url=MASTER_GEO_LINK)],
                    [InlineKeyboardButton("⬅️ Головне меню", callback_data="back_to_menu")]
                ]
            )
        )
        return

    if query.data.startswith('confirm_'):
        booking_id = int(query.data.replace('confirm_', ''))
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("UPDATE bookings SET status=? WHERE id=?", ("Підтверджено", booking_id))
        conn.commit()
        c.execute("SELECT procedure, date, time FROM bookings WHERE id=?", (booking_id,))
        row = c.fetchone()
        conn.close()
        if row:
            procedure, date, time = row
            keyboard = [
                [InlineKeyboardButton("⬅️ Головне меню", callback_data="back_to_menu")]
            ]
            await query.message.reply_text(
                f"✅ Ваш запис на {procedure} {date} о {time} підтверджено! Я з нетерпінням чекаю на тебе! 💖",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return

    if query.data.startswith('cancel_'):
        booking_id = int(query.data.replace('cancel_', ''))
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT name, procedure, date, time FROM bookings WHERE id=?", (booking_id,))
        row = c.fetchone()
        c.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
        conn.commit()
        conn.close()
        if row:
            name, procedure, date, time = row
            # Відправляємо повідомлення клієнту
            await query.message.reply_text(
                f"❌ Твій запис на *{procedure}* {date} о {time} успішно скасовано. Якщо хочеш, ти можеш записатися знову або повернутися до головного меню 👑",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💎 Записатися ще раз", callback_data='book')],
                    [InlineKeyboardButton("⬅️ Повернутися до головного меню", callback_data="back_to_menu")]
                ])
            )
            # ТІЛЬКИ якщо row знайдено — надсилаємо адміну!
            await context.bot.send_message(
                chat_id=ADMIN_IDS,
                text=f"❗️Клієнт {name} скасував запис: {procedure} {date} о {time}"
            )
        return

# --- ВВЕДЕННЯ ТЕКСТУ ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_step = context.user_data.get('step')
    text = update.message.text

    # --- Додавання нового клієнта ---
    if context.user_data.get('client_add'):
        await client_add_text_handler(update, context)
        return

    # --- Пошук клієнта ---
    if context.user_data.get('client_search'):
        await client_search_text_handler(update, context)
        return

    if context.user_data.get('step') == 'edit_note':
        note = update.message.text.strip()
        client_id = context.user_data.get('edit_note_client_id')
        if client_id:
            conn = sqlite3.connect('appointments.db')
            c = conn.cursor()
            c.execute("UPDATE clients SET note=? WHERE id=?", (note, client_id))
            conn.commit()
            conn.close()
            await update.message.reply_text("Примітку оновлено!")
        else:
            await update.message.reply_text("Клієнта не знайдено.")
        context.user_data['step'] = None
        context.user_data['edit_note_client_id'] = None
        return

    # --- СТАРТ РЕДАГУВАННЯ НОТАТКИ ---
    # --- СТАРТ РЕДАГУВАННЯ НОТАТКИ ---


    # --- ЗБЕРЕЖЕННЯ ОНОВЛЕНОЇ НОТАТКИ ---


    # --- Додавання примітки до запису (залишаємо як було) ---
    if user_step == 'add_note' and update.effective_user.id == ADMIN_IDS:
        booking_id = context.user_data['note_booking_id']
        note_text = update.message.text
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("UPDATE bookings SET note=? WHERE id=?", (note_text, booking_id))
        conn.commit()
        conn.close()
        await update.message.reply_text("Примітку збережено! 📝")
        context.user_data['step'] = None
        context.user_data['note_booking_id'] = None
        return

    # --- Інші обробки user_step... ---
    # ... (залишаєш свої обробники далі) ...



    # --- ЗМІНА ЦІНИ В ПРАЙСІ ---
    if user_step == 'update_price' and update.effective_user.id in ADMIN_IDS:
        service_id = context.user_data.get('edit_price_id')
        try:
            new_price = int(text.strip())
            conn = sqlite3.connect('appointments.db')
            c = conn.cursor()
            c.execute("UPDATE price_list SET price=? WHERE id=?", (new_price, service_id))
            conn.commit()
            c.execute("SELECT name FROM price_list WHERE id=?", (service_id,))
            name = c.fetchone()[0]
            conn.close()

            # ⬅️ Додаємо кнопку назад
            keyboard = [
                [InlineKeyboardButton("⬅️ Назад до послуг", callback_data="edit_price")]
            ]
            await update.message.reply_text(
                f"✅ Ціну для *{name}* оновлено на *{new_price} грн*!",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            await update.message.reply_text("❗️Помилка. Введіть цілу суму (наприклад, 350)")
        context.user_data['step'] = None
        context.user_data['edit_price_id'] = None
        return

    # --- Додавання/редагування часу для дня (адмін) ---
    if user_step == 'edit_times' and update.effective_user.id in ADMIN_IDS:
        day = context.user_data.get('edit_day')
        new_times = text.strip()
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT id FROM schedule WHERE date = ?", (day,))
        exists = c.fetchone()
        if exists:
            c.execute("UPDATE schedule SET times=? WHERE date=?", (new_times, day))
        else:
            c.execute("INSERT INTO schedule (date, times) VALUES (?, ?)", (day, new_times))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Для дня {day} оновлено години: {new_times}")
        context.user_data['step'] = None
        context.user_data['edit_day'] = None
        return

    # --- Обробка введення ПІБ та телефону для запису ---
    if user_step == 'get_fullinfo':
        print("==> [get_fullinfo] Вхід")
        print("==> [get_fullinfo] text:", text)

        procedure = context.user_data.get('procedure')
        date = context.user_data.get('date')
        time = context.user_data.get('time')
        user_id = update.effective_user.id

        # Перевірка: мінімум три частини — ім'я, прізвище, телефон
        parts = text.strip().split()
        if len(parts) < 3:
            await update.message.reply_text("⚠️ Введіть як у прикладі: *Ольга Чарівна +380680566881*",
                                            parse_mode="Markdown")
            return

        phone = parts[-1]
        name = " ".join(parts[:-1])

        import re
        if not re.match(r'^\+380\d{9}$', phone):
            await update.message.reply_text("⚠️ Телефон має бути у форматі +380XXXXXXXXX", parse_mode="Markdown")
            return

        if len(name.split()) < 2:
            await update.message.reply_text("⚠️ Вкажіть, будь ласка, і *ім'я*, і *прізвище*!", parse_mode="Markdown")
            return

        try:
            conn = sqlite3.connect('appointments.db')
            c = conn.cursor()
            # Шукаємо клієнта по телефону
            c.execute("SELECT id FROM clients WHERE phone = ?", (phone,))
            result = c.fetchone()

            if result:
                client_id = result[0]
            else:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute(
                    "INSERT INTO clients (name, phone, user_id, note, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (name, phone, user_id, "", now, now))
                client_id = c.lastrowid

            # Додаємо новий запис для клієнта (завжди — і якщо новий, і якщо існує)
            c.execute(
                "INSERT INTO bookings (user_id, client_id, procedure, date, time, status, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, client_id, procedure, date, time, "Очікує підтвердження", ""))
            booking_id = c.lastrowid
            conn.commit()
            conn.close()

            # --- Повідомлення користувачу ---
            keyboard = [
                [InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm_{booking_id}"),
                 InlineKeyboardButton("❌ Відмінити", callback_data=f"cancel_{booking_id}")]
            ]
            await update.message.reply_text(
                f"🎉 Ти записана на *{procedure}* {date} о {time}! Я вже чекаю зустрічі з тобою, ти надихаєш! 💖\n\n"
                "Якщо хочеш — підтверди чи відміні запис, або запишися ще раз 👑",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            print("❌ [SQL ERROR]:", e)
            await update.message.reply_text("⚠️ Виникла помилка при збереженні запису. Спробуйте ще раз.")
            return

        # --- Повідомлення адміну ---
        try:
            msg = (
                f"📥 Новий запис:\n"
                f"ПІБ/Телефон: {name} / {phone}\n"
                f"Процедура: {procedure}\n"
                f"Дата: {date} о {time}"
            )
            if isinstance(ADMIN_IDS, list):
                for admin_id in ADMIN_IDS:
                    await context.bot.send_message(chat_id=admin_id, text=msg)
            else:
                await context.bot.send_message(chat_id=ADMIN_IDS, text=msg)
        except Exception as e:
            print("❌ [ADMIN MSG ERROR]:", e)

        context.user_data.clear()
        return


# --- Нагадування ---
async def send_reminder(user_id, procedure, date, time, mode="day"):
    from telegram import Bot
    bot = Bot(token=TOKEN)
    try:
        if mode == "day":
            text = f"⏰ Красива, нагадую: вже завтра твій бʼюті-запис на {procedure} {date} о {time}! Я чекаю тебе з гарним настроєм і натхненням ✨ До зустрічі, сонечко! 💞"
        elif mode == "2h":
            text = f"💬 Твій бʼюті-час вже зовсім скоро — через 2 годинки! {procedure} {date} о {time} 🌷 Я вже готую найкращі фарби, пензлі та гарячий чай! До зустрічі, зіронько! 👑"
        else:
            text = f"Нагадування про запис: {procedure} {date} о {time}."
        await bot.send_message(
            chat_id=user_id,
            text=text
        )
    except Exception as e:
        print(f"Не вдалося надіслати нагадування: {e}")
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

async def show_stats_for_period(update: Update, context: ContextTypes.DEFAULT_TYPE, period):
    query = update.callback_query
    today = datetime.now().date()
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    if period == 'today':
        date_from = date_to = today
    elif period == 'week':
        date_from = today - timedelta(days=today.weekday())
        date_to = date_from + timedelta(days=6)
    elif period == 'month':
        date_from = today.replace(day=1)
        date_to = today
    else:
        await query.edit_message_text("❓ Незнайомий період.")
        return
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
    if weekdays:
        top_day = collections.Counter(weekdays).most_common(1)[0][0]
    else:
        top_day = "-"
    if hours:
        top_hour = collections.Counter(hours).most_common(1)[0][0] + ":00"
    else:
        top_hour = "-"
    stats_text = (
        f"📊 *Статистика за обраний період*\n"
        f"Всього записів: *{count}*\n"
        f"Унікальних клієнтів: *{unique_clients}*\n\n"
        f"ТОП-3 процедури:\n{procs_str}\n\n"
        f"Найпопулярніший день тижня: *{top_day}*\n"
        f"Найпопулярніша година: *{top_hour}*"
    )
    await query.edit_message_text(stats_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Адмін-сервіс", callback_data="admin_service")]]))
# ======= ДО main() =======

# --- Всі твої async def ... ---

async def set_day_off(update: Update, context: ContextTypes.DEFAULT_TYPE, date):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO deleted_days (date) VALUES (?)", (date,))
    conn.commit()
    conn.close()
    await update.callback_query.edit_message_text(
        "Сьогодні записів немає 💤.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data="manage_schedule")]]
        )
    )

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # --- Хендлери картки клієнта ---
    app.add_handler(CallbackQueryHandler(show_client_card, pattern=r'^client_\d+$'))
    app.add_handler(CallbackQueryHandler(add_condition_start, pattern=r'^addcond_\d+$'))
    app.add_handler(CallbackQueryHandler(list_conditions_handler, pattern=r'^listcond_\d+$'))
    app.add_handler(CallbackQueryHandler(edit_note_start, pattern=r'^editnote_\d+$'))

    # --- Хендлери видалення умов ---
    app.add_handler(CallbackQueryHandler(delete_condition, pattern=r'^delcond_\d+$'))
    app.add_handler(CallbackQueryHandler(confirm_delete, pattern='^confirm_delete$'))
    app.add_handler(CallbackQueryHandler(cancel_delete, pattern='^cancel_delete$'))

    # --- ConversationHandler для умов та нотаток ---
    app.add_handler(ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_condition_start, pattern=r'^addcond_\d+$'),
            CallbackQueryHandler(edit_condition_start, pattern=r'^editcond_\d+$'),
            CallbackQueryHandler(edit_note_start, pattern=r'^editnote_\d+$')
        ],
        states={
            ADDING_CONDITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_condition)],
            EDITING_CONDITION: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edited_condition)],
            EDITING_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edited_note)]
        },
        fallbacks=[],
        per_message=False
    ))

    # --- Універсальний хендлер (завжди останнім!) ---
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling()


if __name__ == "__main__":
    main()


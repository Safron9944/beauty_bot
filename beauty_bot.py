from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.environ["ADMIN_ID"])

import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes,
    MessageHandler, filters
)
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import collections
try:
    from google_sheets import add_to_google_sheet
except ImportError:
    def add_to_google_sheet(*args, **kwargs):
        pass

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
    # Твої інші таблиці:
    c.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            procedure TEXT,
            date TEXT,
            time TEXT,
            user_id INTEGER,
            status TEXT DEFAULT 'Очікує підтвердження'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            times TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS deleted_days (
            date TEXT PRIMARY KEY
        )
    """)
    # Додаємо нову таблицю прайсу:
    c.execute("""
        CREATE TABLE IF NOT EXISTS price_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            price INTEGER
        )
    """)
    # Якщо таблиця порожня — наповнюємо дефолтними послугами:
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
    conn.commit()
    conn.close()

# --- 2. Ось тут вставляєш функцію для виводу прайсу ---
def get_price_text():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT name, price FROM price_list")
    rows = c.fetchall()
    conn.close()

    # Групуємо по категоріях
    cats = {
        "Брови": [],
        "Вії": [],
        "Інше": []
    }
    for name, price in rows:
        if "брів" in name or "Бров" in name:
            cats["Брови"].append((name, price))
        elif "Ві" in name or "вій" in name:
            cats["Вії"].append((name, price))
        else:
            cats["Інше"].append((name, price))

    txt = "💎 *Прайс-лист Safroniuk Brows & Lashes*\n\n"
    for k in cats:
        if cats[k]:
            txt += f"*{k}:*\n"
            for n, p in cats[k]:
                txt += f"• {n} — {p} грн\n"
            txt += "\n"
    txt += "☎️ *Телефон для запису:* +380976853623\nInstagram: @safroniuk.brows.lashes"
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
async def admin_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query
    if user_id != ADMIN_ID:
        await query.answer("Доступно тільки адміну", show_alert=True)
        return
    keyboard = [
        [InlineKeyboardButton("🗓️ Редагувати графік по днях", callback_data='edit_schedule')],
        [InlineKeyboardButton("📊 Статистика", callback_data='admin_stats')],
        [InlineKeyboardButton("💤 Вихідний день", callback_data='delete_day')],
        [InlineKeyboardButton("📅 Календар на сьогодні", callback_data='calendar')],
        [InlineKeyboardButton("📆 Календар на тиждень", callback_data='weekcalendar')],
        [InlineKeyboardButton("💰 Редагувати прайс", callback_data='edit_price')],
        [InlineKeyboardButton("⬅️ Головне меню", callback_data='back_to_menu')]
    ]
    text = (
        "⚙️ *Адмін-сервіс*\n\n"
        "Керуйте розкладом, дивіться всі записи і тримайте красу під контролем 👑\n"
        "Обирайте дію:"
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


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
    keyboard.append([InlineKeyboardButton("⬅️ Назад до адмін-сервісу", callback_data="admin_service")])
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

    # 1. Витягуємо години для цього дня з БД
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT times FROM schedule WHERE date = ?", (day,))
    row = c.fetchone()
    conn.close()
    chosen_times = [t.strip() for t in row[0].split(',')] if row and row[0] else []
    context.user_data['chosen_times'] = chosen_times

    # 2. Визначаємо стандартні години для дня
    weekday = datetime.strptime(day + f".{datetime.now().year}", "%d.%m.%Y").weekday()
    if weekday < 5:
        standard_times = [f"{h:02d}:00" for h in range(14, 19)]
    else:
        standard_times = [f"{h:02d}:00" for h in range(11, 19)]

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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад до адмін-сервісу", callback_data="admin_service")]])
        )
        return

    keyboard = [
        [InlineKeyboardButton(f"❌ {date}", callback_data=f"delday_{date}")] for date in available_dates
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад до адмін-сервісу", callback_data="admin_service")])

    await query.edit_message_text(
        "💤 Обери день для вихідного (цей день стане недоступним для запису):",
        reply_markup=InlineKeyboardMarkup(keyboard)
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
        await update.callback_query.edit_message_text("Сьогодні записів немає 💤.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Адмін-сервіс", callback_data="admin_service")]])
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
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Адмін-сервіс", callback_data="admin_service")]])
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
        await update.callback_query.edit_message_text("На цей тиждень записів немає 💤.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Адмін-сервіс", callback_data="admin_service")]])
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
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Адмін-сервіс", callback_data="admin_service")]])
    )

# --- CALLBACK HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "admin_service":
        await admin_service_handler(update, context)
        return

    if query.data == 'edit_schedule':
        await edit_schedule_handler(update, context)
        return

    if query.data == 'show_price':
        price_text = get_price_text()
        await query.edit_message_text(price_text, parse_mode="Markdown")
        return
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

    if query.data.startswith("delday_") and user_id == ADMIN_ID:
        date = query.data.replace('delday_', '')
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO deleted_days (date) VALUES (?)", (date,))
        conn.commit()
        conn.close()
        await query.edit_message_text(
            f"✅ День {date} зроблено вихідним! Більше недоступний для запису.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Адмін-сервіс", callback_data="admin_service")]])
        )
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
        proc_map = {
            'proc_brows': 'Корекція брів (ідеальна форма)',
            'proc_tint_brows': 'Фарбування + корекція брів',
            'proc_lam_brows': 'Ламінування брів (WOW-ефект)',
            'proc_lam_lashes': 'Ламінування вій (виразний погляд)'
        }
        context.user_data['procedure'] = proc_map[query.data]
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
            await query.message.reply_text(
                f"✅ Ваш запис на {procedure} {date} о {time} підтверджено! Я з нетерпінням чекаю на тебе! 💖"
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
            await query.message.reply_text("❌ Твій запис успішно скасовано. Якщо захочеш повернутися — я завжди тут! 💞")
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"❗️Клієнт {name} скасував запис: {procedure} {date} о {time}"
            )
        return

# --- ВВЕДЕННЯ ТЕКСТУ ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_step = context.user_data.get('step')
    text = update.message.text

    # --- ЗМІНА ЦІНИ В ПРАЙСІ ---
    if user_step == 'update_price' and update.effective_user.id == ADMIN_ID:
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
            await update.message.reply_text(f"Ціну для '{name}' оновлено на {new_price} грн!")
        except Exception as e:
            await update.message.reply_text("❗️Помилка. Введіть цілу суму (наприклад, 350)")
        context.user_data['step'] = None
        context.user_data['edit_price_id'] = None
        return

    # --- Додавання/редагування часу для дня (адмін) ---
    if user_step == 'edit_times' and update.effective_user.id == ADMIN_ID:
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

    if user_step == 'get_fullinfo':
        context.user_data['fullinfo'] = text
        procedure = context.user_data.get('procedure')
        date = context.user_data.get('date')
        time = context.user_data.get('time')
        fullinfo = context.user_data.get('fullinfo')
        user_id = update.effective_user.id
        try:
            name, phone = [s.strip() for s in fullinfo.split(',', 1)]
        except Exception:
            name, phone = fullinfo.strip(), "N/A"
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("INSERT INTO bookings (user_id, name, phone, procedure, date, time, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (user_id, name, phone, procedure, date, time, "Очікує підтвердження"))
        booking_id = c.lastrowid
        conn.commit()
        conn.close()
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
            text=f"""📥 Новий запис:
ПІБ/Телефон: {name} / {phone}
Процедура: {procedure}
Дата: {date} о {time}"""
        )
        event_time = datetime.strptime(f"{date} {time}", "%d.%m %H:%M")
        remind_day = event_time - timedelta(days=1)
        remind_time = remind_day.replace(hour=10, minute=0, second=0, microsecond=0)
        remind_2h = event_time - timedelta(hours=2)
        now = datetime.now()
        if remind_time > now:
            scheduler.add_job(
                send_reminder,
                'date',
                run_date=remind_time,
                args=[user_id, procedure, date, time, "day"]
            )
        if remind_2h > now:
            scheduler.add_job(
                send_reminder,
                'date',
                run_date=remind_2h,
                args=[user_id, procedure, date, time, "2h"]
            )
        context.user_data.clear()
        return

    else:
        await update.message.reply_text("Оберіть дію за допомогою кнопок нижче та подаруйте собі красу! 💖")

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
        f"✅ День {date} зроблено вихідним! Більше недоступний для запису.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Адмін-сервіс", callback_data="admin_service")]])
    )

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()

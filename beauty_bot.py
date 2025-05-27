from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_IDS = [int(i.strip()) for i in os.environ["ADMIN_IDS"].split(",")]
print("DEBUG: ADMIN_IDS from env =", ADMIN_IDS)

import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes,
    MessageHandler, filters
)
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from google_sheets import add_to_google_sheet

scheduler = BackgroundScheduler()

INSTAGRAM_LINK = "https://www.instagram.com/safroniuk_brows_lashes?utm_source=ig_web_button_share_sheet&igsh=ZDNlZDc0MzIxNw=="

def init_db():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
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
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        keyboard = [
            [InlineKeyboardButton("👑 Записатися на процедуру", callback_data='book')],
            [InlineKeyboardButton("📋 Мої записи", callback_data='check_booking')],
            [InlineKeyboardButton("📸 Instagram", callback_data='instagram')],
            [InlineKeyboardButton("ℹ️ Допомога", callback_data='help')],
            [InlineKeyboardButton("🗓️ Календар (адміну)", callback_data='admin_calendar')],
            [InlineKeyboardButton("🗑️ Видалити день (адміну)", callback_data='admin_delete_day')],
            [InlineKeyboardButton("🛠️ Змінити графік", callback_data='admin_schedule')],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("👑 Записатися на процедуру", callback_data='book')],
            [InlineKeyboardButton("📋 Мої записи", callback_data='check_booking')],
            [InlineKeyboardButton("📸 Instagram", callback_data='instagram')],
            [InlineKeyboardButton("ℹ️ Допомога", callback_data='help')]
        ]
    await update.message.reply_text(
        "✨ Вітаю в beauty-боті! Тут кожна дівчина знаходить час для себе та свого образу 💖\n\n"
        "Обирай дію нижче — і гайда до краси! 🌸",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        text = (
            "👑 *Доступні команди:*\n\n"
            "/start — головне меню\n"
            "/mybookings — подивитись свої записи\n"
            "/help — інструкція та список команд\n"
            "/instagram — Instagram майстра\n"
            "/calendar — календар записів на сьогодні (адміну)\n"
            "/weekcalendar — календар на тиждень (адміну)\n\n"
            "*Адміну доступно:*\n"
            "/schedule — змінити графік\n"
            "/set_schedule — змінити графік (альтернатива)\n"
            "/delete_day — видалити день з графіка"
        )
    else:
        text = (
            "✨ *Доступні команди:*\n\n"
            "/start — головне меню\n"
            "/mybookings — подивитись свої записи\n"
            "/help — інструкція та список команд\n"
            "/instagram — Instagram майстра"
        )
    await update.message.reply_text(text, parse_mode='Markdown')

async def instagram_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🌸 *Підписуйся на мій Instagram!* 🌸\n\n"
        "Тут ти знайдеш мої роботи, корисні поради, актуальні акції і трохи натхнення для себе:\n"
        f"{INSTAGRAM_LINK}\n\n"
        "👑 @safroniuk_brows_lashes — разом до краси!"
    )
    if hasattr(update, "message") and update.message:
        await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=False)
    else:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=False)

async def schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Доступно тільки адміну.")
        return
    await update.message.reply_text(
        "🗓️ Введіть графік у форматі:\n\n28.05: 14:00,15:00,16:00\n29.05: 15:00,16:00"
    )
    context.user_data['step'] = 'set_schedule'

async def delete_day_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Доступно тільки адміну.")
        return
    today = datetime.now().date()
    dates = set()
    for i in range(7):
        d = today + timedelta(days=i)
        dates.add(d.strftime("%d.%m"))
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT date FROM schedule")
    for row in c.fetchall():
        dates.add(row[0])
    conn.close()
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT date FROM deleted_days")
    deleted = {row[0] for row in c.fetchall()}
    conn.close()
    dates = [d for d in dates if d not in deleted]
    dates = sorted(list(dates), key=lambda x: datetime.strptime(x + f".{datetime.now().year}", "%d.%m.%Y"))
    if not dates:
        await update.message.reply_text("Немає днів для видалення.")
        return
    keyboard = [
        [InlineKeyboardButton(f"❌ {date}", callback_data=f"delday_{date}")] for date in dates
    ]
    await update.message.reply_text("🗑️ Обери день для видалення (він зникне для запису):", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data['step'] = None

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
        await update.message.reply_text("Сьогодні записів немає.")
        return

    text = f"📅 Записи на {today.strftime('%d.%m.%Y')}:\n\n"
    for rec in rows:
        date, time, procedure, name, phone, status = rec
        text += (
            f"🕒 {time} — {procedure}\n"
            f"👤 {name}, 📱 {phone}\n"
            f"Статус: {status}\n\n"
        )
    await update.message.reply_text(text)

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
        await update.message.reply_text("На цей тиждень записів немає.")
        return

    text = "📆 Записи на цей тиждень:\n\n"
    for rec in rows:
        date, time, procedure, name, phone, status = rec
        text += (
            f"📅 {date} 🕒 {time} — {procedure}\n"
            f"👤 {name}, 📱 {phone}\n"
            f"Статус: {status}\n\n"
        )
    await update.message.reply_text(text)

async def mybookings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
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
            await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text("Записів не знайдено. Час оновити свій образ! 💄")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # --- Для адміна окремі кнопки ---
    if query.data == "admin_calendar" and user_id in ADMIN_IDS:
        await calendar_handler(update, context)
        return
    if query.data == "admin_delete_day" and user_id in ADMIN_IDS:
        await delete_day_handler(update, context)
        return
    if query.data == "admin_schedule" and user_id in ADMIN_IDS:
        await schedule_handler(update, context)
        return

    # --- Для всіх ---
    if query.data == "help":
        await help_handler(update, context)
        return
    if query.data == "instagram":
        await instagram_handler(update, context)
        return
    if query.data == "check_booking":
        await mybookings_handler(update, context)
        return
    if query.data == "book":
        context.user_data['step'] = 'choose_procedure'
        keyboard = [
            [InlineKeyboardButton("Корекція брів", callback_data='proc_brows_correction')],
            [InlineKeyboardButton("Фарбування брів", callback_data='proc_brows_paint')],
            [InlineKeyboardButton("Ламінування брів", callback_data='proc_brows_lamination')],
            [InlineKeyboardButton("Ламінування вій", callback_data='proc_lashes_lamination')],
            [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')]
        ]
        await query.message.reply_text("✨ Обери свою бʼюті-процедуру! Серденьком обирай те, що подобається найбільше — або натисни ⬅️ щоб повернутись до мрій!", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    if query.data == "main_menu":
        await start(update, context)
        return
    if query.data.startswith("proc_"):
        context.user_data['procedure'] = query.data.replace("proc_", "").replace("_", " ").title()
        context.user_data['step'] = 'choose_date'
        await query.message.reply_text("🌸 Який день зробить тебе ще красивішою? Вибирай і натискай сердечко! Або повернись на крок назад, якщо захочеш змінити процедуру 💖")
        # Тут має бути реалізація вибору дати
        return
    if query.data.startswith("delday_") and user_id in ADMIN_IDS:
        del_day = query.data.replace("delday_", "")
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO deleted_days (date) VALUES (?)", (del_day,))
        conn.commit()
        conn.close()
        await query.message.reply_text(f"День {del_day} прибрано з графіка для запису!")
        return
    # --- Далі кнопки для покрокового запису клієнта та адміну за твоєю логікою ---

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    step = context.user_data.get('step')

    if step == 'set_schedule' and user_id in ADMIN_IDS:
        # Реалізуй збереження графіка в базу
        await update.message.reply_text("Графік змінено!")
        context.user_data['step'] = None
        return
    # ... додай інші кроки для покрокового запису клієнта ...
    await update.message.reply_text("Натисни /start або вибери дію через меню!")

async def send_reminder(user_id, procedure, date, time, mode="day"):
    pass  # якщо використовуєш APScheduler, встав тут логіку нагадувань

set_schedule_handler = schedule_handler

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("instagram", instagram_handler))
    app.add_handler(CommandHandler("calendar", calendar_handler))
    app.add_handler(CommandHandler("weekcalendar", week_calendar_handler))
    app.add_handler(CommandHandler("schedule", schedule_handler))
    app.add_handler(CommandHandler("set_schedule", schedule_handler))
    app.add_handler(CommandHandler("delete_day", delete_day_handler))
    app.add_handler(CommandHandler("mybookings", mybookings_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_polling()

if __name__ == "__main__":
    main()

from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')

# Підтримка кількох адміністраторів через кому (наприклад 1035792183,474236378)
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

# --- Далі йде button_handler, text_handler, send_reminder, mybookings_handler ---
# Просто встав зі свого коду ці функції сюди, замінивши всі ADMIN_ID на ADMIN_IDS

# Не забудь замінити всі порівняння user_id == ADMIN_ID на user_id in ADMIN_IDS і так далі!

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

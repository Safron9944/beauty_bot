from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
MASTER_PHONE = "+380976853623"

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

# --- DATABASE INITIALIZATION ---
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

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_message
    keyboard = [
        [InlineKeyboardButton("👑 Записатися на процедуру", callback_data='book')],
        [InlineKeyboardButton("📋 Мої записи", callback_data='check_booking')],
        [InlineKeyboardButton("📸 Instagram", callback_data='instagram')],
        [InlineKeyboardButton("ℹ️ Допомога", callback_data='help')],
        [InlineKeyboardButton("📞 Контакти майстра", callback_data='contact')]
    ]
    await chat.reply_text(
        "✨ Вітаю в beauty-боті! Тут кожна дівчина знаходить час для себе та свого образу 💖\n\n"
        "Обирай дію нижче — і гайда до краси! 🌸",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text_user = (
        "✨ *Доступні команди:*\n"
        "/start — головне меню\n"
        "/mybookings — подивитись свої записи\n"
        "/help — інструкція та список команд\n"
        "/instagram — Instagram майстра\n"
        "/contact — контакти майстра"
    )
    text_admin = text_user + (
        "\n"
        "/calendar — календар записів на сьогодні (адміну)\n"
        "/weekcalendar — календар на тиждень (адміну)\n"
        "/schedule — змінити графік\n"
        "/delete_day — видалити день з графіка"
    )
    text = text_admin if user_id == ADMIN_ID else text_user
    await update.effective_message.reply_text(text, parse_mode='Markdown')

async def instagram_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🌸 *Підписуйся на мій Instagram!* 🌸\n\n"
        "Тут ти знайдеш мої роботи, корисні поради, актуальні акції і трохи натхнення для себе:\n"
        f"{INSTAGRAM_LINK}\n\n"
        "👑 @safroniuk_brows_lashes — разом до краси!"
    )
    msg = update.effective_message
    await msg.reply_text(text, parse_mode="Markdown", disable_web_page_preview=False)

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(f"📞 Номер майстра: {MASTER_PHONE}")

# --- SCHEDULE EDITING ---
async def schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("⛔ Доступно тільки адміну.")
        return
    today = datetime.now().date()
    keyboard = []
    for i in range(7):
        d = today + timedelta(days=i)
        keyboard.append([InlineKeyboardButton(d.strftime("%d.%m"), callback_data=f"edit_schedule_{d.strftime('%d.%m')}")])
    await update.effective_message.reply_text(
        "🗓️ Оберіть дату для редагування графіку:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data.clear()

async def delete_day_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("⛔ Доступно тільки адміну.")
        return
    # існуюча логіка видалення дня...

async def calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("⛔ Доступно тільки адміну.")
        return
    # існуюча логіка виведення записів на сьогодні...

async def week_calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("⛔ Доступно тільки адміну.")
        return
    # існуюча логіка тижневого календаря...

# --- BUTTON HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'back_to_menu':
        await start(update, context)
        return
    if query.data == 'contact':
        await contact_handler(update, context)
        return

    if query.data.startswith("edit_schedule_"):
        # логіка редагування графіку...
        return
    # інші обробки колбеків для записів...

# --- TEXT HANDLER ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # логіка обробки тексту, зокрема додавання годин
    await update.effective_message.reply_text("Оберіть дію за допомогою кнопок нижче.")

# --- MAIN ---

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("instagram", instagram_handler))
    app.add_handler(CommandHandler("contact", contact_handler))
    app.add_handler(CommandHandler("schedule", schedule_handler))
    app.add_handler(CommandHandler("delete_day", delete_day_handler))
    app.add_handler(CommandHandler("calendar", calendar_handler))
    app.add_handler(CommandHandler("weekcalendar", week_calendar_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()

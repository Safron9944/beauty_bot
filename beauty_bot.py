from dotenv import load_dotenv
import os

load_dotenv()  # Завантажує змінні з .env
TOKEN = os.getenv('TELEGRAM_TOKEN')

import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes,
    MessageHandler, filters
)
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from google_sheets import add_to_google_sheet

ADMIN_ID = int(os.environ["ADMIN_ID"])
scheduler = BackgroundScheduler()

def init_db():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            surname TEXT,
            phone TEXT,
            procedure TEXT,
            date TEXT,
            time TEXT
        )
    """)
    c.execute("PRAGMA table_info(bookings)")
    columns = [col[1] for col in c.fetchall()]
    if 'user_id' not in columns:
        try:
            c.execute("ALTER TABLE bookings ADD COLUMN user_id INTEGER")
        except Exception as e:
            print("❌ Не вдалося додати user_id:", e)
    conn.commit()
    add_to_google_sheet(name, surname, phone, procedure, date, time)
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📝 Записатися на процедури", callback_data='book')],
        [InlineKeyboardButton("📅 Перевірити мій запис", callback_data='check_booking')]
    ]
    await update.message.reply_text("Привіт! Оберіть дію:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'book':
        keyboard = [
            [InlineKeyboardButton("Корекція брів", callback_data='proc_brows')],
            [InlineKeyboardButton("Фарбування та корекція брів", callback_data='proc_tint_brows')],
            [InlineKeyboardButton("Ламінування брів", callback_data='proc_lam_brows')],
            [InlineKeyboardButton("Ламінування вій", callback_data='proc_lam_lashes')]
        ]
        await query.message.reply_text("Оберіть процедуру:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == 'check_booking':
        await query.message.reply_text("Введіть ваш номер телефону для перевірки:")
        context.user_data['step'] = 'check_phone'

    elif query.data.startswith('proc_'):
        proc_map = {
            'proc_brows': 'Корекція брів',
            'proc_tint_brows': 'Фарбування та корекція брів',
            'proc_lam_brows': 'Ламінування брів',
            'proc_lam_lashes': 'Ламінування вій'
        }
        context.user_data['procedure'] = proc_map[query.data]
        await query.message.reply_text("Введіть дату у форматі ДД.ММ:")
        context.user_data['step'] = 'get_date'

    elif query.data.startswith("time_"):
        time = query.data.replace("time_", "")
        name = context.user_data['name']
        surname = context.user_data['surname']
        phone = context.user_data['phone']
        procedure = context.user_data['procedure']
        date = context.user_data['date']
        user_id = query.from_user.id

        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("INSERT INTO bookings (user_id, name, surname, phone, procedure, date, time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (user_id, name, surname, phone, procedure, date, time))
        conn.commit()
        add_to_google_sheet(name, surname, phone, procedure, date, time)
        conn.close()

        add_to_google_sheet(name, surname, phone, procedure, date, time)

        keyboard = [
            [InlineKeyboardButton("📝 Записатися на процедури", callback_data='book')],
            [InlineKeyboardButton("📅 Перевірити мій запис", callback_data='check_booking')]
        ]
        await query.message.reply_text(
            f"✅ Вас записано на {procedure} {date} о {time}. Дякуємо, {name}!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"""📥 Новий запис:
Ім'я: {name} {surname}
Телефон: {phone}
Процедура: {procedure}
Дата: {date} о {time}"""
        )

        context.user_data.clear()

<<<<<<< HEAD
# (решта коду не змінювалася, тому його опускаємо для збереження простору)
=======
# (решта коду не змінювалася, тому його опускаємо для збереження простору)
>>>>>>> d82f3d3 (Initial commit: Telegram beauty bot)

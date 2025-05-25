from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from apscheduler.schedulers.background import BackgroundScheduler
from google_sheets import add_to_google_sheet

# Scheduler for reminders
scheduler = BackgroundScheduler()

# Initialize the SQLite database
def init_db():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("""
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    phone TEXT,
    procedure TEXT,
    date TEXT,
    time TEXT
)
""")
    conn.commit()
    conn.close()

# /start command handler
def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📝 Записатися на процедури", callback_data='book')],
        [InlineKeyboardButton("📅 Перевірити мій запис", callback_data='check_booking')]
    ]
    update.message.reply_text(
        "Привіт! Оберіть дію:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# /admin command for administrator
def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        update.message.reply_text("У вас немає доступу до цієї команди.")
        return

    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute(
        "SELECT name, phone, procedure, date, time FROM bookings ORDER BY id DESC"
    )
    rows = c.fetchall()
    conn.close()

    if rows:
        lines = [
            f"{name}, {phone}, {procedure}, {date} о {time}"
            for name, phone, procedure, date, time in rows
        ]
        reply_text = '📋 Усі записи:
' + '
'.join(lines)
    else:
        reply_text = 'Записів не знайдено.'

    update.message.reply_text(reply_text)

# CallbackQuery handler for button clicks
def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == 'book':
        keyboard = [
            [InlineKeyboardButton("Корекція брів", callback_data='proc_brows')],
            [InlineKeyboardButton("Фарбування та корекція брів", callback_data='proc_tint_brows')],
            [InlineKeyboardButton("Ламінування брів", callback_data='proc_lam_brows')],
            [InlineKeyboardButton("Ламінування вій", callback_data='proc_lam_lashes')]
        ]
        query.message.reply_text(
            "Оберіть процедуру:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == 'check_booking':
        query.message.reply_text("Введіть ваш номер телефону (тільки цифри):")
        context.user_data['step'] = 'check_phone'

    elif data.startswith('proc_'):
        proc_map = {
            'proc_brows': 'Корекція брів',
            'proc_tint_brows': 'Фарбування та корекція брів',
            'proc_lam_brows': 'Ламінування брів',
            'proc_lam_lashes': 'Ламінування вій'
        }
        context.user_data['procedure'] = proc_map[data]
        query.message.reply_text("Введіть дату у форматі ДД.MM:")
        context.user_data['step'] = 'get_date'

    elif data.startswith('time_'):
        time_str = data.split('_', 1)[1]
        fullinfo = context.user_data.get('fullinfo', '')
        procedure = context.user_data.get('procedure', '')
        date = context.user_data.get('date', '')
        user_id = query.from_user.id

        try:
            name, phone = [s.strip() for s in fullinfo.split(',', 1)]
        except ValueError:
            name, phone = fullinfo.strip(), ''

        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute(
            "INSERT INTO bookings (user_id, name, phone, procedure, date, time) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, phone, procedure, date, time_str)
        )
        conn.commit()
        conn.close()

        # Write to Google Sheet
        add_to_google_sheet(name, phone, procedure, date, time_str)

        # Send confirmation
        keyboard = [
            [InlineKeyboardButton("📝 Записатися на процедури", callback_data='book')],
            [InlineKeyboardButton("📅 Перевірити мій запис", callback_data='check_booking')]
        ]
        query.message.reply_text(
            f"✅ Вас записано на {procedure} {date} о {time_str}. Дякуємо, {name}!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # Notify admin
        query.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📥 Новий запис:
ПІБ/Телефон: {name} / {phone}
Процедура: {procedure}
Дата: {date} о {time_str}"
        )

        # Schedule reminder
        dt_event = datetime.strptime(f"{date} {time_str}", "%d.%m %H:%M")
        dt_remind = (dt_event - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        if dt_remind > datetime.now():
            scheduler.add_job(
                send_reminder, 'date', run_date=dt_remind,
                args=[user_id, procedure, date, time_str]
            )
            scheduler.start()

        context.user_data.clear()

# Handler for plain text messages
def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('step')
    text = update.message.text.strip()

    if step == 'get_date':
        context.user_data['date'] = text
        update.message.reply_text(
            "Введіть ПІБ та номер телефону через кому (наприклад: Іваненко Марія, 0931234567):"
        )
        context.user_data['step'] = 'get_fullinfo'

    elif step == 'get_fullinfo':
        context.user_data['fullinfo'] = text
        times = ['14:00', '15:00', '16:00', '17:00', '18:00']
        keyboard = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in times]
        update.message.reply_text("Оберіть час:", reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data['step'] = None

    elif step == 'check_phone':
        phone = text
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute(
            "SELECT name, procedure, date, time FROM bookings WHERE phone LIKE ?",
            (f"%{phone}%",)
        )
        rows = c.fetchall()
        conn.close()
        if rows:
            lines = [f"{n}, {p}, {d} о {t}" for n, p, d, t in rows]
            reply_text = "Ваші записи:
" + "
".join(lines)
        else:
            reply_text = "Записів не знайдено."
        update.message.reply_text(reply_text)
    else:
        update.message.reply_text("Оберіть дію за допомогою кнопок /start")

# Send reminder function
def send_reminder(user_id, procedure, date, time):
    from telegram import Bot
    bot = Bot(token=TOKEN)
    bot.send_message(chat_id=user_id, text=f"⏰ Нагадування! Ваш запис: {procedure} {date} о {time}.")

def main():
    init_db()
    scheduler.start()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == '__main__':
    main()

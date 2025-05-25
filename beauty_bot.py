from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

import sqlite3
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

from apscheduler.schedulers.background import BackgroundScheduler
from google_sheets import add_to_google_sheet

scheduler = BackgroundScheduler()

def init_db():
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        phone TEXT,
        procedure TEXT,
        date TEXT,
        time TEXT
    )""")
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📝 Записатися на процедури", callback_data='book')],
        [InlineKeyboardButton("📅 Перевірити мій запис", callback_data='check_booking')]
    ]
    await update.message.reply_text("Привіт! Оберіть дію:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("У вас немає доступу до цієї команди.")
        return
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT name, phone, procedure, date, time FROM bookings ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    if rows:
        lines = [f"{name}, {phone}, {procedure}, {date} о {time}" for name, phone, procedure, date, time in rows]
        reply_text = "📋 Усі записи:
" + "
".join(lines)
    else:
        reply_text = "Записів не знайдено."
    await update.message.reply_text(reply_text)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'book':
        keyboard = [
            [InlineKeyboardButton("Корекція брів", callback_data='proc_brows')],
            [InlineKeyboardButton("Фарбування та корекція брів", callback_data='proc_tint_brows')],
            [InlineKeyboardButton("Ламінування брів", callback_data='proc_lam_brows')],
            [InlineKeyboardButton("Ламінування вій", callback_data='proc_lam_lashes')]
        ]
        await query.message.reply_text("Оберіть процедуру:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == 'check_booking':
        await query.message.reply_text("Введіть ваш номер телефону (тільки цифри):")
        context.user_data['step'] = 'check_phone'

    elif data.startswith('proc_'):
        proc_map = {
            'proc_brows': 'Корекція брів',
            'proc_tint_brows': 'Фарбування та корекція брів',
            'proc_lam_brows': 'Ламінування брів',
            'proc_lam_lashes': 'Ламінування вій'
        }
        context.user_data['procedure'] = proc_map[data]
        await query.message.reply_text("Введіть дату у форматі ДД.MM:")
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
            "INSERT INTO bookings(user_id, name, phone, procedure, date, time) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, phone, procedure, date, time_str)
        )
        conn.commit()
        conn.close()

        add_to_google_sheet(name, phone, procedure, date, time_str)

        keyboard = [
            [InlineKeyboardButton("📝 Записатися на процедури", callback_data='book')],
            [InlineKeyboardButton("📅 Перевірити мій запис", callback_data='check_booking')]
        ]
        await query.message.reply_text(
            f"✅ Вас записано на {procedure} {date} о {time_str}. Дякуємо, {name}!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📥 Новий запис:
ПІБ/Телефон: {name} / {phone}
Процедура: {procedure}
Дата: {date} о {time_str}"
        )

        event_dt = datetime.strptime(f"{date} {time_str}", "%d.%m %H:%M")
        remind_dt = (event_dt - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        if remind_dt > datetime.now():
            scheduler.add_job(send_reminder, 'date', run_date=remind_dt, args=[user_id, procedure, date, time_str])
            scheduler.start()

        context.user_data.clear()

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get('step')
    text = update.message.text

    if step == 'get_date':
        context.user_data['date'] = text.strip()
        await update.message.reply_text(
            "Введіть ПІБ та номер телефону через кому (наприклад: Іваненко Марія, 0931234567):"
        )
        context.user_data['step'] = 'get_fullinfo'

    elif step == 'get_fullinfo':
        context.user_data['fullinfo'] = text.strip()
        times = ['14:00', '15:00', '16:00', '17:00', '18:00']
        keyboard = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in times]
        await update.message.reply_text("Оберіть час:", reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data['step'] = None

    elif step == 'check_phone':
        phone = text.strip()
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
        await update.message.reply_text(reply_text)
        context.user_data['step'] = None
    else:
        await update.message.reply_text("Оберіть дію за допомогою кнопок /start")

async def send_reminder(user_id, procedure, date, time):
    from telegram import Bot
    bot = Bot(token=TOKEN)
    try:
        await bot.send_message(chat_id=user_id, text=f"⏰ Нагадування! Ваш запис: {procedure} {date} о {time}.")
    except Exception as e:
        print("Не вдалося надіслати нагадування:", e)

def main():
    init_db()
    scheduler.start()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()

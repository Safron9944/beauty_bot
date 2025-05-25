from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')

import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from google_sheets import add_to_google_sheet

ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
scheduler = BackgroundScheduler()

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
            user_id INTEGER
        )
    """)
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📝 Записатися на процедури", callback_data='book')],
        [InlineKeyboardButton("📅 Перевірити мій запис", callback_data='check_booking')]
    ]
    await update.message.reply_text("Привіт! Оберіть дію:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("У вас немає доступу до цієї команди.")
        return
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT name, phone, procedure, date, time FROM bookings ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    if rows:
        entries = [f"{name}, {phone}, {procedure}, {date} о {time}" for name, phone, procedure, date, time in rows]
        reply = "📋 Усі записи:
" + "
".join(entries)
    else:
        reply = "Записів не знайдено."
    await update.message.reply_text(reply)

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
        await query.message.reply_text("Введіть ваш номер телефону (тільки цифри):")
        context.user_data['step'] = 'check_phone'
    elif query.data.startswith('proc_'):
        proc_map = {
            'proc_brows': 'Корекція брів',
            'proc_tint_brows': 'Фарбування та корекція брів',
            'proc_lam_brows': 'Ламінування брів',
            'proc_lam_lashes': 'Ламінування вій'
        }
        context.user_data['procedure'] = proc_map[query.data]
        await query.message.reply_text("Введіть дату у форматі ДД.MM:")
        context.user_data['step'] = 'get_date'
    elif query.data.startswith("time_"):
        time = query.data.replace("time_", "")
        fullinfo = context.user_data.get('fullinfo', '')
        procedure = context.user_data.get('procedure', '')
        date = context.user_data.get('date', '')
        user_id = query.from_user.id
        try:
            name, phone = [s.strip() for s in fullinfo.split(',', 1)]
        except ValueError:
            name, phone = fullinfo.strip(), "N/A"
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute(
            "INSERT INTO bookings (user_id, name, phone, procedure, date, time) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, phone, procedure, date, time)
        )
        conn.commit()
        conn.close()
        add_to_google_sheet(name, phone, procedure, date, time)
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
            text=(
                f"📥 Новий запис:
"
                f"ПІБ/Телефон: {name} / {phone}
"
                f"Процедура: {procedure}
"
                f"Дата: {date} о {time}"
            )
        )
        event_time = datetime.strptime(f"{date} {time}", "%d.%m %H:%M")
        remind_day = event_time - timedelta(days=1)
        remind_time = remind_day.replace(hour=10, minute=0, second=0, microsecond=0)
        now = datetime.now()
        if remind_time > now:
            scheduler.add_job(send_reminder, 'date', run_date=remind_time, args=[user_id, procedure, date, time])
            scheduler.start()
        context.user_data.clear()

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_step = context.user_data.get('step')
    text = update.message.text
    if user_step == 'get_date':
        context.user_data['date'] = text
        await update.message.reply_text(
            "Введіть ПІБ та номер телефону через кому (наприклад: Іваненко Марія, 0931234567):"
        )
        context.user_data['step'] = 'get_fullinfo'
    elif user_step == 'get_fullinfo':
        context.user_data['fullinfo'] = text
        times = ['14:00', '15:00', '16:00', '17:00', '18:00']
        keyboard = [[InlineKeyboardButton(time, callback_data=f"time_{time}")] for time in times]
        await update.message.reply_text("Оберіть час:", reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data['step'] = None
    elif user_step == 'check_phone':
        phone = text.strip()
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT name, procedure, date, time FROM bookings WHERE phone LIKE ?", (f"%{phone}%",))
        rows = c.fetchall()
        conn.close()
        if rows:
            reply = "Ваші записи:
" + "
".join([f"{name}, {procedure}, {date} о {time}" for name, procedure, date, time in rows])
        else:
            reply = "Записів не знайдено."
        await update.message.reply_text(reply)
        context.user_data['step'] = None
    else:
        await update.message.reply_text("Оберіть дію за допомогою кнопок /start")

async def send_reminder(user_id, procedure, date, time):
    from telegram import Bot
    bot = Bot(token=TOKEN)
    try:
        await bot.send_message(chat_id=user_id, text=f"⏰ Нагадування! Ваш запис: {procedure} {date} о {time}.")
    except Exception as e:
        print(f"Не вдалося надіслати нагадування: {e}")

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()

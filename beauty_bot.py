from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')

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
            phone TEXT,
            procedure TEXT,
            date TEXT,
            time TEXT,
            user_id INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            times TEXT
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

async def schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Доступно тільки адміну.")
        return
    await update.message.reply_text(
        "Введіть графік у форматі:\n\n28.05: 14:00,15:00,16:00\n29.05: 15:00,16:00"
    )
    context.user_data['step'] = 'set_schedule'

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
        context.user_data.clear()

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
        # --- Кнопки дат на 14 днів ---
        dates = []
        today = datetime.now().date()
        for i in range(14):
            d = today + timedelta(days=i)
            dates.append(d.strftime("%d.%m"))
        keyboard = [
            [InlineKeyboardButton(date, callback_data=f'date_{date}')] for date in dates
        ]
        await query.message.reply_text("Оберіть дату:", reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data['step'] = None

    elif query.data.startswith('date_'):
        date = query.data.replace('date_', '')
        context.user_data['date'] = date
        # --- Графік з бази або авто ---
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT times FROM schedule WHERE date = ?", (date,))
        row = c.fetchone()
        conn.close()
        if row:
            times = [t.strip() for t in row[0].split(',')]
        else:
            # Автоматично (будні/вихідні)
            day = datetime.strptime(date + f".{datetime.now().year}", "%d.%m.%Y").weekday()
            if day < 5:
                times = [f"{h:02d}:00" for h in range(14, 19)]
            else:
                times = [f"{h:02d}:00" for h in range(11, 19)]
        # Вилучаємо вже зайняті години
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT time FROM bookings WHERE date = ?", (date,))
        booked_times = [row[0] for row in c.fetchall()]
        conn.close()
        free_times = [t for t in times if t not in booked_times]

        if not free_times:
            await query.message.reply_text("На цю дату всі години зайняті. Спробуйте іншу дату.")
            return

        keyboard = [
            [InlineKeyboardButton(time, callback_data=f"time_{time}")]
            for time in free_times
        ]
        await query.message.reply_text(
            "Оберіть час:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data['step'] = None

    elif query.data.startswith("time_"):
        time = query.data.replace("time_", "")
        context.user_data['time'] = time
        await query.message.reply_text("Введіть ПІБ та номер телефону через кому (наприклад: Іваненко Марія, 0931234567):")
        context.user_data['step'] = 'get_fullinfo'

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_step = context.user_data.get('step')
    text = update.message.text

    if user_step == 'set_schedule' and update.effective_user.id == ADMIN_ID:
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("DELETE FROM schedule")
        for line in text.strip().split('\n'):
            if ':' in line:
                date, times = line.split(':', 1)
                c.execute("INSERT INTO schedule (date, times) VALUES (?, ?)", (date.strip(), times.strip()))
        conn.commit()
        conn.close()
        await update.message.reply_text("Графік оновлено!")
        context.user_data['step'] = None
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
        c.execute("INSERT INTO bookings (user_id, name, phone, procedure, date, time) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, name, phone, procedure, date, time))
        conn.commit()
        conn.close()

        add_to_google_sheet(name, "", phone, procedure, date, time)

        keyboard = [
            [InlineKeyboardButton("📝 Записатися на процедури", callback_data='book')],
            [InlineKeyboardButton("📅 Перевірити мій запис", callback_data='check_booking')]
        ]
        await update.message.reply_text(
            f"✅ Вас записано на {procedure} {date} о {time}. Дякуємо, {name}!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # Адміну повідомлення
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"""📥 Новий запис:
ПІБ/Телефон: {name} / {phone}
Процедура: {procedure}
Дата: {date} о {time}"""
        )

        # Нагадування за добу о 10:00
        event_time = datetime.strptime(f"{date} {time}", "%d.%m %H:%M")
        remind_day = event_time - timedelta(days=1)
        remind_time = remind_day.replace(hour=10, minute=0, second=0, microsecond=0)
        now = datetime.now()
        if remind_time > now:
            scheduler.add_job(
                send_reminder,
                'date',
                run_date=remind_time,
                args=[user_id, procedure, date, time]
            )
            scheduler.start()

        context.user_data.clear()

    elif user_step == 'check_phone':
        phone = text.strip()
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT name, procedure, date, time FROM bookings WHERE phone LIKE ?", (f"%{phone}%",))
        rows = c.fetchall()
        conn.close()
        if rows:
            reply = "Ваші записи:\n" + "\n".join(
                [f"{name}, {procedure}, {date} о {time}" for name, procedure, date, time in rows]
            )
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
        await bot.send_message(
            chat_id=user_id,
            text=f"⏰ Нагадування! Ваш запис: {procedure} {date} о {time}."
        )
    except Exception as e:
        print(f"Не вдалося надіслати нагадування: {e}")

# Додатково: команда /mybookings (записи для user_id)
async def mybookings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT procedure, date, time FROM bookings WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    if rows:
        reply = "Ваші записи:\n" + "\n".join([f"{proc}, {date} о {time}" for proc, date, time in rows])
    else:
        reply = "Записів не знайдено."
    await update.message.reply_text(reply)

set_schedule_handler = schedule_handler

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("schedule", schedule_handler))
    app.add_handler(CommandHandler("set_schedule", set_schedule_handler))
    app.add_handler(CommandHandler("mybookings", mybookings_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_polling()

if __name__ == "__main__":
    main()

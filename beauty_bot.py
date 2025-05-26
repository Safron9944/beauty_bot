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

def init_db():
    """Initialize the SQLite database and create the bookings table."""
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

def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    keyboard = [
        [InlineKeyboardButton("📝 Записатися на процедури", callback_data='book')],
        [InlineKeyboardButton("📅 Перевірити мій запис", callback_data='check_booking')]
    ]
    update.message.reply_text(
        "Привіт! Оберіть дію:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /admin command for administrators."""
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("У вас немає доступу до цієї команди.")
        return

    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT id, name, phone, procedure, date, time FROM bookings ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()

    if rows:
        for row in rows:
            booking_id, name, phone, procedure, date, time = row
            msg = (
                f"ID: {booking_id}\n"
                f"ПІБ: {name}\n"
                f"Телефон: {phone}\n"
                f"Процедура: {procedure}\n"
                f"Дата: {date} о {time}"
            )
            keyboard = [
                [InlineKeyboardButton("✏️ Редагувати", callback_data=f'edit_{booking_id}')]
            ]
            update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        update.message.reply_text("Записів не знайдено.")

def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all callback queries from inline buttons."""
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
        query.message.reply_text("Оберіть процедуру:", reply_markup=InlineKeyboardMarkup(keyboard))

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
            text=f"📥 Новий запис:\nПІБ/Телефон: {name} / {phone}\nПроцедура: {procedure}\nДата: {date} о {time_str}"
        )

        # Schedule reminder
        event_dt = datetime.strptime(f"{date} {time_str}", "%d.%m %H:%M")
        remind_dt = (event_dt - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
        if remind_dt > datetime.now():
            scheduler.add_job(send_reminder, 'date', run_date=remind_dt,
                              args=[user_id, procedure, date, time_str])
            scheduler.start()

        context.user_data.clear()

    elif data.startswith('edit_'):
        if update.effective_user.id != ADMIN_ID:
            query.message.reply_text("У вас немає доступу.")
            return

        booking_id = int(data.split('_')[1])
        context.user_data['edit_id'] = booking_id

        # Запитати, що редагувати
        keyboard = [
            [InlineKeyboardButton("ПІБ", callback_data='editfield_name')],
            [InlineKeyboardButton("Телефон", callback_data='editfield_phone')],
            [InlineKeyboardButton("Процедуру", callback_data='editfield_procedure')],
            [InlineKeyboardButton("Дату", callback_data='editfield_date')],
            [InlineKeyboardButton("Час", callback_data='editfield_time')],
        ]
        query.message.reply_text("Що хочете змінити?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith('editfield_'):
        field = data.split('_')[1]
        context.user_data['edit_field'] = field
        query.message.reply_text("Введіть нове значення:")
        context.user_data['step'] = 'edit_value'

def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages for steps."""
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
            reply_text = "Ваші записи:\n" + "\n".join(lines)
        else:
            reply_text = "Записів не знайдено."
        update.message.reply_text(reply_text)

    elif step == 'edit_value':
        booking_id = context.user_data.get('edit_id')
        field = context.user_data.get('edit_field')
        new_value = text

        if field not in ['name', 'phone', 'procedure', 'date', 'time']:
            update.message.reply_text("Невірне поле для редагування.")
            return

        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute(f"UPDATE bookings SET {field}=? WHERE id=?", (new_value, booking_id))
        conn.commit()
        conn.close()

        update.message.reply_text(f"{field} оновлено!")
        context.user_data['step'] = None
        context.user_data['edit_id'] = None
        context.user_data['edit_field'] = None

    else:
        update.message.reply_text("Оберіть дію за допомогою кнопок /start")

def send_reminder(user_id, procedure, date, time):
    """Send reminder message one day before."""
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

from dotenv import load_dotenv
import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes,
    MessageHandler, filters
)
from datetime import datetime
import logging

# Завантаження .env
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)

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
        CREATE TABLE IF NOT EXISTS schedules (
            date TEXT,
            time TEXT,
            booked INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📅 Записатися", callback_data='choose_date')]]
    await update.message.reply_text("Привіт! Оберіть дію:", reply_markup=InlineKeyboardMarkup(keyboard))

async def set_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ У вас немає доступу до цієї команди.")
        return
    await update.message.reply_text("Введіть графік у форматі:
27.05: 14:00, 15:00
28.05: 10:00, 11:00")
    context.user_data['step'] = 'set_schedule'

async def handle_schedule_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('step') != 'set_schedule':
        return
    text = update.message.text.strip()
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("DELETE FROM schedules")
    lines = text.split('\n')
    for line in lines:
        try:
            date_part, times_part = line.split(':')
            date = date_part.strip()
            times = [t.strip() for t in times_part.split(',')]
            for t in times:
                c.execute("INSERT INTO schedules (date, time, booked) VALUES (?, ?, 0)", (date, t))
        except Exception as e:
            await update.message.reply_text(f"⚠️ Помилка в рядку: {line}")
            conn.rollback()
            conn.close()
            return
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ Графік збережено.")
    context.user_data.clear()

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'choose_date':
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT DISTINCT date FROM schedules WHERE booked = 0 ORDER BY date")
        dates = c.fetchall()
        conn.close()
        if not dates:
            await query.message.reply_text("Немає доступних дат.")
            return
        keyboard = [[InlineKeyboardButton(date[0], callback_data=f"date_{date[0]}")] for date in dates]
        await query.message.reply_text("Оберіть дату:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("date_"):
        date = query.data.replace("date_", "")
        context.user_data['selected_date'] = date
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT time FROM schedules WHERE date = ? AND booked = 0 ORDER BY time", (date,))
        times = c.fetchall()
        conn.close()
        if not times:
            await query.message.reply_text("Усі години на цю дату зайняті.")
            return
        keyboard = [[InlineKeyboardButton(t[0], callback_data=f"time_{t[0]}")] for t in times]
        await query.message.reply_text("Оберіть час:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("time_"):
        time = query.data.replace("time_", "")
        date = context.user_data.get('selected_date')
        context.user_data['selected_time'] = time
        context.user_data['step'] = 'get_info'
        await query.message.reply_text("Введіть ПІБ та номер телефону через кому:")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('step') == 'get_info':
        fullinfo = update.message.text
        try:
            name, phone = [s.strip() for s in fullinfo.split(',', 1)]
        except:
            await update.message.reply_text("Невірний формат. Спробуйте ще раз.")
            return
        procedure = "Запис за графіком"
        date = context.user_data.get('selected_date')
        time = context.user_data.get('selected_time')
        user_id = update.effective_user.id

        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("INSERT INTO bookings (user_id, name, phone, procedure, date, time) VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, name, phone, procedure, date, time))
        c.execute("UPDATE schedules SET booked = 1 WHERE date = ? AND time = ?", (date, time))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ Вас записано на {date} о {time}. Дякуємо, {name}!")
        context.user_data.clear()

async def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set_schedule", set_schedule))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_schedule_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
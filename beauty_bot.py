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
        "✨ *Доступні команди:*
/start — головне меню
/mybookings — подивитись свої записи
/help — інструкція та список команд
/instagram — Instagram майстра
/contact — контакти майстра"
    )
    text_admin = text_user + (
        "
/calendar — календар записів на сьогодні (адміну)
/weekcalendar — календар на тиждень (адміну)
/schedule — змінити графік
/delete_day — видалити день з графіка"
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
    text = f"📞 Номер майстра: {MASTER_PHONE}"
    msg = update.effective_message
    await msg.reply_text(text)

# --- SCHEDULE EDITING ---
async def schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("⛔ Доступно тільки адміну.")
        return
    today = datetime.now().date()
    keyboard = []
    for i in range(7):
        d = today + timedelta(days=i)
        date_str = d.strftime("%d.%m")
        keyboard.append([InlineKeyboardButton(date_str, callback_data=f"edit_schedule_{date_str}")])
    await update.effective_message.reply_text(
        "🗓️ Оберіть дату для редагування графіку:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data.clear()

# --- BUTTON HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # BACK TO MENU
    if query.data == 'back_to_menu':
        await start(update, context)
        return
    # CONTACT
    if query.data == 'contact':
        await contact_handler(update, context)
        return

    # SCHEDULE EDIT: choose date
    if query.data.startswith("edit_schedule_") and query.from_user.id == ADMIN_ID:
        date = query.data.replace("edit_schedule_", "")
        context.user_data['edit_date'] = date
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT times FROM schedule WHERE date=?", (date,))
        row = c.fetchone()
        conn.close()
        hours = row[0].split(",") if row else []
        keyboard = [
            [InlineKeyboardButton(f"❌ {h}", callback_data=f"remove_time_{date}_{h}")] for h in hours
        ]
        keyboard.append([InlineKeyboardButton("➕ Додати годину", callback_data=f"add_time_{date}")])
        keyboard.append([InlineKeyboardButton("⬅️ Назад до дат", callback_data="back_to_dates")])
        await query.message.reply_text(
            f"🗓️ Графік для {date} — поточні години: {', '.join(hours) if hours else 'немає'}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # REMOVE TIME
    if query.data.startswith("remove_time_") and query.from_user.id == ADMIN_ID:
        _, date, hour = query.data.split("_", 2)
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT times FROM schedule WHERE date=?", (date,))
        row = c.fetchone()
        if row:
            times = [t for t in row[0].split(",") if t != hour]
            if times:
                c.execute("UPDATE schedule SET times=? WHERE date=?", (",".join(times), date))
            else:
                c.execute("DELETE FROM schedule WHERE date=?", (date,))
            conn.commit()
        conn.close()
        await query.answer("Годину видалено.")
        # refresh menu
        await schedule_handler(update, context)
        return

    # INITIATE ADD TIME
    if query.data.startswith("add_time_") and query.from_user.id == ADMIN_ID:
        date = query.data.replace("add_time_", "")
        context.user_data['step'] = 'add_time'
        context.user_data['edit_date'] = date
        await query.message.reply_text("Введіть годину у форматі HH:MM (наприклад, 14:30):")
        return

    # BACK TO DATES
    if query.data == "back_to_dates" and query.from_user.id == ADMIN_ID:
        await schedule_handler(update, context)
        return

    # --- existing booking logic below (book, proc_, ...)
    # (тут вставити ваші обробки запису, як раніше)
    # ...

# --- TEXT HANDLER ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_step = context.user_data.get('step')
    text = update.message.text.strip()

    # ADD TIME STEP
    if user_step == 'add_time' and update.effective_user.id == ADMIN_ID:
        try:
            datetime.strptime(text, "%H:%M")
        except ValueError:
            await update.message.reply_text("Невірний формат часу. Спробуйте ще раз (HH:MM).")
            return
        date = context.user_data.get('edit_date')
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT times FROM schedule WHERE date=?", (date,))
        row = c.fetchone()
        if row:
            times = set(row[0].split(","))
            times.add(text)
            new_times = ",".join(sorted(times))
            c.execute("UPDATE schedule SET times=? WHERE date=?", (new_times, date))
        else:
            c.execute("INSERT INTO schedule (date, times) VALUES (?, ?)", (date, text))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Додано годину {text} для {date}.")
        context.user_data['step'] = None
        # refresh edit menu
        fake_update = update
        fake_update.callback_query = type("Q", (), {"data": f"edit_schedule_{date}", "from_user": update.effective_user, "message": update.message})
        await button_handler(fake_update, context)
        return

    # ... інша логіка text_handler для записів ...
    context.user_data['step'] = None
    await update.message.reply_text("Оберіть дію за допомогою кнопок нижче.")

# --- REMINDERS ---
async def send_reminder(user_id, procedure, date, time, mode="day"):
    from telegram import Bot
    bot = Bot(token=TOKEN)
    if mode == "day":
        text = f"⏰ Нагадую: завтра твій запис на {procedure} {date} о {time}!"
    elif mode == "2h":
        text = f"💬 Запис на {procedure} {date} о {time} через 2 години."
    else:
        text = f"Нагадування про запис: {procedure} {date} о {time}."
    try:
        await bot.send_message(chat_id=user_id, text=text)
    except Exception:
        pass

async def mybookings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT id, procedure, date, time, status FROM bookings WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    if rows:
        for rec in rows:
            bidding_id, procedure, date, time, status = rec
            msg = f"✨ {procedure}\n🗓️ {date} о {time}\nСтатус: *{status}*"
            buttons = []
            if status == "Очікує підтвердження":
                buttons = [InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm_{bidding_id}"),
                           InlineKeyboardButton("❌ Відмінити", callback_data=f"cancel_{bidding_id}")]
            reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None
            await update.effective_message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.effective_message.reply_text("Записів не знайдено.")

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

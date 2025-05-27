from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.environ["ADMIN_ID"])
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
    # Кнопка для адміна
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🗓️ Редагувати графік", callback_data='edit_schedule')])
    await update.message.reply_text(
        "✨ Вітаю в beauty-боті! Тут кожна дівчина знаходить час для себе та свого образу 💖\n\n"
        "Обирай дію нижче — і гайда до краси! 🌸",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        text = (
            "👑 *Доступні команди:*\n\n"
            "/start — головне меню\n"
            "/mybookings — подивитись свої записи\n"
            "/help — інструкція та список команд\n"
            "/instagram — Instagram майстра\n"
            "/calendar — календар записів на сьогодні (адміну)\n"
            "/weekcalendar — календар на тиждень (адміну)\n\n"
            "*Адміну доступно:*\n"
            "/schedule — змінити графік (текстом)\n"
            "/edit_schedule — редагувати графік через кнопки\n"
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
    text += f"\n\n📞 Майстер: {MASTER_PHONE}"
    await update.message.reply_text(text, parse_mode='Markdown')

async def instagram_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🌸 *Підписуйся на мій Instagram!* 🌸\n\n"
        "Тут ти знайдеш мої роботи, корисні поради, актуальні акції і трохи натхнення для себе:\n"
        f"{INSTAGRAM_LINK}\n\n"
        "👑 @safroniuk_brows_lashes — разом до краси!"
    )
    text += f"\n\n📞 Телефон для запису/звʼязку: {MASTER_PHONE}"
    if hasattr(update, "message") and update.message:
        await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=False)
    else:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=False)

# ---------- НОВИЙ БЛОК: редагування графіка через кнопки ----------

async def edit_schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступно тільки адміну.")
        return
    await show_schedule_days(update, context)

async def show_schedule_days(update_or_query, context):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT date, times FROM schedule ORDER BY date")
    days = c.fetchall()
    conn.close()
    keyboard = []
    for day, times in days:
        keyboard.append([
            InlineKeyboardButton(f"{day}", callback_data=f"edit_day_{day}"),
            InlineKeyboardButton("➖ Видалити", callback_data=f"delday_{day}")
        ])
    keyboard.append([InlineKeyboardButton("➕ Додати день", callback_data="add_day")])
    keyboard.append([InlineKeyboardButton("⬅️ Головне меню", callback_data="back_to_menu")])
    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text("🗓️ Оберіть день для редагування:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update_or_query.edit_message_text("🗓️ Оберіть день для редагування:", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_edit_day(update, context, day):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT times FROM schedule WHERE date=?", (day,))
    row = c.fetchone()
    conn.close()
    times = [t.strip() for t in row[0].split(',')] if row and row[0] else []
    keyboard = []
    for t in times:
        keyboard.append([InlineKeyboardButton(f"{t}", callback_data=f"none"), InlineKeyboardButton("❌", callback_data=f"delhour_{day}_{t}")])
    keyboard.append([InlineKeyboardButton("➕ Додати годину", callback_data=f"addhour_{day}")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад до днів", callback_data="edit_schedule")])
    await update.callback_query.edit_message_text(f"Години для {day}:", reply_markup=InlineKeyboardMarkup(keyboard))

async def add_day_handler(update, context):
    await update.callback_query.edit_message_text("Введіть нову дату у форматі 31.05:")
    context.user_data["step"] = "add_day"

async def process_add_day(update, context):
    day = update.message.text.strip()
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT 1 FROM schedule WHERE date=?", (day,))
    if c.fetchone():
        await update.message.reply_text("Такий день вже є у графіку.")
    else:
        c.execute("INSERT INTO schedule (date, times) VALUES (?, ?)", (day, ""))
        conn.commit()
        await update.message.reply_text(f"День {day} додано до графіка!")
    conn.close()
    context.user_data["step"] = None
    await show_schedule_days(update, context)

async def delday_handler(update, context, day):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("DELETE FROM schedule WHERE date=?", (day,))
    conn.commit()
    conn.close()
    await update.callback_query.edit_message_text(f"День {day} видалено.")
    await show_schedule_days(update, context)

async def delhour_handler(update, context, day, hour):
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT times FROM schedule WHERE date=?", (day,))
    row = c.fetchone()
    times = [t.strip() for t in row[0].split(',')] if row and row[0] else []
    times = [t for t in times if t != hour]
    c.execute("UPDATE schedule SET times=? WHERE date=?", (",".join(times), day))
    conn.commit()
    conn.close()
    await show_edit_day(update, context, day)

async def addhour_start(update, context, day):
    context.user_data["step"] = "add_hour"
    context.user_data["add_hour_day"] = day
    await update.callback_query.edit_message_text("Введіть нову годину для дня " + day + " у форматі 15:00:")

async def process_addhour(update, context):
    day = context.user_data.get("add_hour_day")
    hour = update.message.text.strip()
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT times FROM schedule WHERE date=?", (day,))
    row = c.fetchone()
    times = [t.strip() for t in row[0].split(',')] if row and row[0] else []
    if hour in times:
        await update.message.reply_text("Така година вже є.")
    else:
        times.append(hour)
        times = sorted(times)  # Сортуємо години
        c.execute("UPDATE schedule SET times=? WHERE date=?", (",".join(times), day))
        conn.commit()
        await update.message.reply_text(f"Годину {hour} додано.")
    conn.close()
    context.user_data["step"] = None
    context.user_data["add_hour_day"] = None
    await show_edit_day(update, context, day)

# ----------- /кінець нового блоку ----------

async def schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступно тільки адміну.")
        return
    await update.message.reply_text(
        "🗓️ Введіть графік у форматі:\n\n28.05: 14:00,15:00,16:00\n29.05: 15:00,16:00"
    )
    context.user_data['step'] = 'set_schedule'

async def delete_day_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
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
    if update.effective_user.id != ADMIN_ID:
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

# --- Далі залишаємо твій основний функціонал без змін ---

# Сюди додай всі свої інші функції (button_handler, text_handler, mybookings_handler, send_reminder, week_calendar_handler, і т.д.)
# Ось мінімальний button_handler з підтримкою нових кнопок:

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # --- НОВІ гілки для edit_schedule ---
    if query.data == 'edit_schedule':
        await show_schedule_days(update, context)
        return
    if query.data == 'add_day':
        await add_day_handler(update, context)
        return
    if query.data.startswith('edit_day_'):
        day = query.data.replace('edit_day_', '')
        await show_edit_day(update, context, day)
        return
    if query.data.startswith('delday_'):
        day = query.data.replace('delday_', '')
        await delday_handler(update, context, day)
        return
    if query.data.startswith('delhour_'):
        part = query.data.replace('delhour_', '')
        day, hour = part.split('_')
        await delhour_handler(update, context, day, hour)
        return
    if query.data.startswith('addhour_'):
        day = query.data.replace('addhour_', '')
        await addhour_start(update, context, day)
        return

    # --- Інші callback-и з твого коду, наприклад book, confirm, cancel і т.д. ---
    # ...

# --- Обробка тексту для додавання дня/години (user_data["step"]) ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_step = context.user_data.get('step')
    text = update.message.text

    if user_step == 'set_schedule' and update.effective_user.id == ADMIN_ID:
        # (цей блок залиш як був)
        # ...
        return

    if user_step == "add_day":
        await process_add_day(update, context)
        return

    if user_step == "add_hour":
        await process_addhour(update, context)
        return

    # (далі твій старий text_handler...)

# --- main ---
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("instagram", instagram_handler))
    app.add_handler(CommandHandler("calendar", calendar_handler))
    app.add_handler(CommandHandler("weekcalendar", calendar_handler))
    app.add_handler(CommandHandler("schedule", schedule_handler))
    app.add_handler(CommandHandler("set_schedule", schedule_handler))
    app.add_handler(CommandHandler("edit_schedule", edit_schedule_handler))
    app.add_handler(CommandHandler("delete_day", delete_day_handler))
    # додай свої функції для бронювань, запису, нагадування і т.д.
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_polling()

if __name__ == "__main__":
    main()

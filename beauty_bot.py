from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.environ["ADMIN_ID"])

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
            "/schedule — графік з кнопками"
        )
    else:
        text = (
            "✨ *Доступні команди:*\n\n"
            "/start — головне меню\n"
            "/mybookings — подивитись свої записи\n"
            "/help — інструкція та список команд\n"
            "/instagram — Instagram майстра"
        )
    await update.message.reply_text(text, parse_mode='Markdown')

async def instagram_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🌸 *Підписуйся на мій Instagram!* 🌸\n\n"
        "Тут ти знайдеш мої роботи, корисні поради, актуальні акції і трохи натхнення для себе:\n"
        f"{INSTAGRAM_LINK}\n\n"
        "👑 @safroniuk_brows_lashes — разом до краси!"
    )
    if hasattr(update, "message") and update.message:
        await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=False)
    else:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=False)

async def schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступно тільки адміну.")
        return
    keyboard = [
        [InlineKeyboardButton("Редагувати графік тижня", callback_data='admin_schedule')]
    ]
    await update.message.reply_text("Що хочеш зробити з графіком?", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data['step'] = None

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

async def week_calendar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступно тільки адміну.")
        return
    today = datetime.now().date()
    week_dates = [(today + timedelta(days=i)).strftime("%d.%m") for i in range(7)]
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute(
        f"SELECT date, time, procedure, name, phone, status FROM bookings "
        f"WHERE date IN ({','.join(['?']*len(week_dates))}) ORDER BY date, time", week_dates
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("На цей тиждень записів немає.")
        return
    text = "📆 Записи на цей тиждень:\n\n"
    for rec in rows:
        date, time, procedure, name, phone, status = rec
        text += (
            f"📅 {date} 🕒 {time} — {procedure}\n"
            f"👤 {name}, 📱 {phone}\n"
            f"Статус: {status}\n\n"
        )
    await update.message.reply_text(text)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # === Назад до меню ===
    if query.data == 'back_to_menu':
        if query.message:
            await query.message.delete()
        if update.effective_chat:
            await update.get_bot().send_message(
                chat_id=update.effective_chat.id,
                text="✨ Вітаю в beauty-боті! Тут кожна дівчина знаходить час для себе та свого образу 💖\n\n"
                     "Обирай дію нижче — і гайда до краси! 🌸",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👑 Записатися на процедуру", callback_data='book')],
                    [InlineKeyboardButton("📋 Мої записи", callback_data='check_booking')],
                    [InlineKeyboardButton("📸 Instagram", callback_data='instagram')],
                    [InlineKeyboardButton("ℹ️ Допомога", callback_data='help')]
                ])
            )
        context.user_data.clear()
        return

    # ========== ІНТЕРАКТИВНЕ АДМІН-МЕНЮ ГРАФІКА ===============
    # Показати дати тижня
    if query.data == "admin_schedule":
        if user_id != ADMIN_ID:
            await query.message.reply_text("⛔ Доступно лише адміну.")
            return
        today = datetime.now().date()
        week_dates = [(today + timedelta(days=i)).strftime("%d.%m") for i in range(7)]
        keyboard = [
            [InlineKeyboardButton(date, callback_data=f"admin_schedule_{date}")]
            for date in week_dates
        ]
        await query.message.reply_text("🗓️ Обери день для редагування:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Обрана дата — показати години цієї дати
    if query.data.startswith("admin_schedule_"):
        date = query.data.replace("admin_schedule_", "")
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT times FROM schedule WHERE date = ?", (date,))
        row = c.fetchone()
        conn.close()
        times = []
        if row and row[0]:
            times = [t.strip() for t in row[0].split(',') if t.strip()]
        keyboard = []
        for t in times:
            keyboard.append([InlineKeyboardButton(f"🕒 {t} ❌", callback_data=f"admin_del_time_{date}_{t}")])
        keyboard.append([InlineKeyboardButton("➕ Додати час", callback_data=f"admin_add_time_{date}")])
        keyboard.append([InlineKeyboardButton("❌ Видалити день повністю", callback_data=f"delday_{date}")])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_schedule")])
        await query.message.reply_text(f"⏰ Часи для {date}:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Видалити конкретний час
    if query.data.startswith("admin_del_time_"):
        _, date, time = query.data.split("_", 2)
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT times FROM schedule WHERE date = ?", (date,))
        row = c.fetchone()
        if row and row[0]:
            times = [t.strip() for t in row[0].split(',') if t.strip() and t.strip() != time]
            new_times = ",".join(times)
            if new_times:
                c.execute("UPDATE schedule SET times = ? WHERE date = ?", (new_times, date))
            else:
                c.execute("DELETE FROM schedule WHERE date = ?", (date,))
            conn.commit()
        conn.close()
        await query.message.reply_text(f"⏰ Час {time} видалено для {date}.")
        # Показати знову меню для цієї дати
        await button_handler(update, context)
        return

    # Додати час (введення вручну)
    if query.data.startswith("admin_add_time_"):
        date = query.data.replace("admin_add_time_", "")
        context.user_data["admin_add_time_date"] = date
        await query.message.reply_text("Введи час для додавання у форматі HH:MM (наприклад, 16:00):")
        context.user_data["step"] = "admin_add_time"
        return

    # ...далі залишаєш решту button_handler як було (процедури, календар, підтвердження, скасування, стандартна логіка)...

    # Вибір процедури
    if query.data == 'book' or query.data == 'back_to_procedure':
        keyboard = [
            [InlineKeyboardButton("✨ Корекція брів (ідеальна форма)", callback_data='proc_brows')],
            [InlineKeyboardButton("🎨 Фарбування + корекція брів", callback_data='proc_tint_brows')],
            [InlineKeyboardButton("🌟 Ламінування брів (WOW-ефект)", callback_data='proc_lam_brows')],
            [InlineKeyboardButton("👁️ Ламінування вій (виразний погляд)", callback_data='proc_lam_lashes')],
            [InlineKeyboardButton("⬅️ Назад до меню", callback_data='back_to_menu')]
        ]
        await query.message.reply_text(
            "✨ Обери свою бʼюті-процедуру, красуне! Серденьком познач ту, яка надихає найбільше — або натискай ⬅️ щоб повернутись до мрій 🌈💖\n\nОбіцяю, твоя краса засяє ще яскравіше! 🫶",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data.clear()
        return

    # ...інші callback-и (залишаєш як у тебе)...

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_step = context.user_data.get('step')
    text = update.message.text

    # Додавання часу в графік адміністратором
    if user_step == "admin_add_time":
        date = context.user_data.get("admin_add_time_date")
        new_time = text.strip()
        try:
            datetime.strptime(new_time, "%H:%M")
        except Exception:
            await update.message.reply_text("❗ Некоректний формат. Спробуй ще раз у форматі HH:MM.")
            return
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT times FROM schedule WHERE date = ?", (date,))
        row = c.fetchone()
        if row and row[0]:
            times = [t.strip() for t in row[0].split(',') if t.strip()]
            if new_time in times:
                await update.message.reply_text("Такий час уже є.")
                conn.close()
                return
            times.append(new_time)
            new_times = ",".join(sorted(times))
            c.execute("UPDATE schedule SET times = ? WHERE date = ?", (new_times, date))
        else:
            c.execute("INSERT INTO schedule (date, times) VALUES (?, ?)", (date, new_time))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"🆕 Час {new_time} додано для {date}!")
        await button_handler(update, context)
        context.user_data["step"] = None
        context.user_data.pop("admin_add_time_date", None)
        return

    # ...залиш інші кроки як у тебе...

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("instagram", instagram_handler))
    app.add_handler(CommandHandler("calendar", calendar_handler))
    app.add_handler(CommandHandler("weekcalendar", week_calendar_handler))
    app.add_handler(CommandHandler("schedule", schedule_handler))
    app.add_handler(CommandHandler("delete_day", delete_day_handler))
    # ...інші хендлери...
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_polling()

if __name__ == "__main__":
    main()

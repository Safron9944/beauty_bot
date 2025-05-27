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
        [InlineKeyboardButton("ℹ️ Допомога", callback_data='help')]
    ]
    await update.message.reply_text(
        "👑 Вітаю в beauty-боті! Тут кожна дівчина знаходить час для себе та свого образу ✨\n\n"
        "Оберіть дію нижче:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        text = (
            "👑 *Доступні команди:*\n\n"
            "/start — головне меню\n"
            "/mybookings — подивитись свої записи\n"
            "/help — інструкція та список команд\n\n"
            "*Адміну доступно:*\n"
            "/schedule — змінити графік\n"
            "/set_schedule — змінити графік (альтернатива)\n"
            "/delete_day — видалити день з графіка"
        )
    else:
        text = (
            "✨ *Доступні команди:*\n\n"
            "/start — головне меню\n"
            "/mybookings — подивитись свої записи\n"
            "/help — інструкція та список команд"
        )
    await update.message.reply_text(text, parse_mode='Markdown')

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
    await update.message.reply_text("🗑️ Оберіть день для видалення (він зникне для запису):", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data['step'] = None

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'book':
        keyboard = [
            [InlineKeyboardButton("✨ Корекція брів (ідеальна форма)", callback_data='proc_brows')],
            [InlineKeyboardButton("🎨 Фарбування + корекція брів", callback_data='proc_tint_brows')],
            [InlineKeyboardButton("🌟 Ламінування брів (WOW-ефект)", callback_data='proc_lam_brows')],
            [InlineKeyboardButton("👁️ Ламінування вій (виразний погляд)", callback_data='proc_lam_lashes')]
        ]
        await query.message.reply_text(
            "💖 Обери бʼюті-процедуру, яка змусить сяяти твої очі:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data.clear()

    elif query.data == 'check_booking':
        await query.message.reply_text("📱 Введи свій номер телефону (тільки цифри):")
        context.user_data['step'] = 'check_phone'

    elif query.data == 'help':
        await help_handler(update, context)

    elif query.data.startswith('proc_'):
        proc_map = {
            'proc_brows': 'Корекція брів (ідеальна форма)',
            'proc_tint_brows': 'Фарбування + корекція брів',
            'proc_lam_brows': 'Ламінування брів (WOW-ефект)',
            'proc_lam_lashes': 'Ламінування вій (виразний погляд)'
        }
        context.user_data['procedure'] = proc_map[query.data]
        today = datetime.now().date()
        dates = []
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT date FROM deleted_days")
        deleted = {row[0] for row in c.fetchall()}
        conn.close()
        for i in range(7):
            d = today + timedelta(days=i)
            date_str = d.strftime("%d.%m")
            if date_str not in deleted:
                dates.append(date_str)
        if not dates:
            await query.message.reply_text("⛔ Немає доступних днів для запису. Зверніться до майстра!")
            return
        keyboard = [
            [InlineKeyboardButton(f"📅 Обираю {date} 💋", callback_data=f'date_{date}')] for date in dates
        ]
        await query.message.reply_text(
            "💗 Обери бажану дату для твоєї краси:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data['step'] = None

    elif query.data.startswith('date_'):
        date = query.data.replace('date_', '')
        context.user_data['date'] = date
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT times FROM schedule WHERE date = ?", (date,))
        row = c.fetchone()
        conn.close()
        if row:
            times = [t.strip() for t in row[0].split(',')]
        else:
            day = datetime.strptime(date + f".{datetime.now().year}", "%d.%m.%Y").weekday()
            if day < 5:
                times = [f"{h:02d}:00" for h in range(14, 19)]
            else:
                times = [f"{h:02d}:00" for h in range(11, 19)]
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT time FROM bookings WHERE date = ?", (date,))
        booked_times = [row[0] for row in c.fetchall()]
        conn.close()
        free_times = [t for t in times if t not in booked_times]
        if not free_times:
            await query.message.reply_text("😔 Всі години на цей день вже зайняті. Спробуй обрати інший день!")
            return
        keyboard = [
            [InlineKeyboardButton(f"🕒 {time} | Моє ідеальне віконце 💖", callback_data=f"time_{time}")]
            for time in free_times
        ]
        await query.message.reply_text(
            "⏰ Обери зручний час для своєї бʼюті-процедури:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data['step'] = None

    elif query.data.startswith("time_"):
        time = query.data.replace("time_", "")
        context.user_data['time'] = time
        await query.message.reply_text(
            "👸 Введи *ПІБ* та *номер телефону* через кому:\n\n"
            "_Наприклад: Ярина Квіткова, 0971234567_\n"
            "Твій майстер запише тебе з усмішкою! 😊",
            parse_mode='Markdown'
        )
        context.user_data['step'] = 'get_fullinfo'

    elif query.data.startswith('delday_') and query.from_user.id == ADMIN_ID:
        date = query.data.replace('delday_', '')
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO deleted_days (date) VALUES (?)", (date,))
        conn.commit()
        conn.close()
        await query.message.reply_text(f"✅ День {date} видалено з графіка. Клієнти більше не побачать цей день для запису.")

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
        await update.message.reply_text("✅ Графік оновлено!")
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
            [InlineKeyboardButton("👑 Записатися ще", callback_data='book')],
            [InlineKeyboardButton("📋 Мої записи", callback_data='check_booking')],
            [InlineKeyboardButton("ℹ️ Допомога", callback_data='help')]
        ]
        await update.message.reply_text(
            f"🎉 Ви записані на {procedure} {date} о {time}!\n"
            f"Ваш бʼюті-майстер Марія вже чекає зустрічі з вами 💖\n"
            "До зустрічі у світі краси! 👑✨",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"""📥 Новий запис:
ПІБ/Телефон: {name} / {phone}
Процедура: {procedure}
Дата: {date} о {time}"""
        )
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
            reply = "Записів не знайдено.\n\n💅 Зробіть свій перший запис через кнопку \"Записатися на процедуру\"!"
        await update.message.reply_text(reply)
        context.user_data['step'] = None

    else:
        await update.message.reply_text("Оберіть дію за допомогою кнопок нижче та подаруйте собі красу! 💖")

async def send_reminder(user_id, procedure, date, time):
    from telegram import Bot
    bot = Bot(token=TOKEN)
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"⏰ Нагадування!\nВаш запис: {procedure} {date} о {time}.\nБʼюті-майстер чекає! 🌸"
        )
    except Exception as e:
        print(f"Не вдалося надіслати нагадування: {e}")

async def mybookings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT procedure, date, time FROM bookings WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    if rows:
        reply = "💋 Ваші майбутні записи:\n" + "\n".join([f"— {proc}, {date} о {time}" for proc, date, time in rows])
    else:
        reply = "Записів не знайдено. Час оновити свій образ! 💄"
    await update.message.reply_text(reply)

set_schedule_handler = schedule_handler

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("schedule", schedule_handler))
    app.add_handler(CommandHandler("set_schedule", set_schedule_handler))
    app.add_handler(CommandHandler("delete_day", delete_day_handler))
    app.add_handler(CommandHandler("mybookings", mybookings_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_polling()

if __name__ == "__main__":
    main()

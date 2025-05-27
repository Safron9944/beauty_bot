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

INSTAGRAM_LINK = "https://www.instagram.com/safroniuk_brows_lashes?igsh=YXRkZW90eDEwcXI5"

PROCEDURE_OPTIONS = [
    ("✨ Корекція брів (ідеальна форма)", "proc_brows"),
    ("🎨 Фарбування + корекція брів", "proc_tint_brows"),
    ("🌟 Ламінування брів (WOW-ефект)", "proc_lam_brows"),
    ("👁️ Ламінування вій (виразний погляд)", "proc_lam_lashes"),
]

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
            "/help — інструкція та список команд\n"
            "/instagram — Instagram майстра\n"
            "/calendar — календар записів на сьогодні (адміну)\n"
            "/weekcalendar — календар на тиждень (адміну)\n\n"
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
            "/help — інструкція та список команд\n"
            "/instagram — Instagram майстра"
        )
    await update.message.reply_text(text, parse_mode='Markdown')

async def instagram_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🌸 *Підписуйся на наш Instagram!* 🌸\n\n"
        "Тут ти знайдеш ще більше фото робіт, корисних порад та акцій для своїх клієнток:\n"
        f"{INSTAGRAM_LINK}\n\n"
        "👑 Збережи собі ідеї та ділись із подругами!"
    )
    if hasattr(update, "message") and update.message:
        await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=False)
    else:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=False)

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

async def show_procedure_multi_select(query, context):
    selected = context.user_data.get('procedures', [])
    keyboard = []
    for title, code in PROCEDURE_OPTIONS:
        mark = "✅" if code in selected else "☑️"
        keyboard.append([InlineKeyboardButton(f"{mark} {title}", callback_data=f"multi_proc_{code}")])
    keyboard.append([InlineKeyboardButton("➡️ Далі", callback_data="procedures_next")])
    text = (
        "💅 Оберіть одну або кілька бʼюті-процедур (можна натискати кілька разів):\n"
        "_Після вибору натисніть 'Далі'_"
    )
    if query.message:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Початок мультивибору процедур
    if query.data == 'book':
        context.user_data['procedures'] = []
        await show_procedure_multi_select(query, context)
        return

    # Додавання/зняття процедури
    if query.data.startswith("multi_proc_"):
        code = query.data.replace("multi_proc_", "")
        selected = context.user_data.get('procedures', [])
        if code in selected:
            selected.remove(code)
        else:
            selected.append(code)
        context.user_data['procedures'] = selected
        await show_procedure_multi_select(query, context)
        return

    # Далі — до вибору дати
    if query.data == "procedures_next":
        if not context.user_data.get('procedures'):
            await query.message.reply_text("Оберіть хоча б одну процедуру!")
            return
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
        return

    if query.data == 'check_booking':
        # Користувач побачить свої записи (з кнопками для підтвердження/відміни)
        user_id = query.from_user.id
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT id, procedure, date, time, status FROM bookings WHERE user_id=?", (user_id,))
        rows = c.fetchall()
        conn.close()
        if rows:
            for rec in rows:
                booking_id, procedure, date, time, status = rec
                msg = f"✨ {procedure}\n🗓️ {date} о {time}\nСтатус: *{status}*"
                buttons = []
                if status == "Очікує підтвердження":
                    buttons.append(InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm_{booking_id}"))
                    buttons.append(InlineKeyboardButton("❌ Відмінити", callback_data=f"cancel_{booking_id}"))
                reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None
                await query.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await query.message.reply_text("Записів не знайдено. Час оновити свій образ! 💄")

    elif query.data == 'help':
        await help_handler(update, context)

    elif query.data == 'instagram':
        await instagram_handler(update, context)

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

    # --- Підтвердження запису ---
    elif query.data.startswith('confirm_'):
        booking_id = int(query.data.replace('confirm_', ''))
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("UPDATE bookings SET status=? WHERE id=?", ("Підтверджено", booking_id))
        conn.commit()
        c.execute("SELECT procedure, date, time FROM bookings WHERE id=?", (booking_id,))
        row = c.fetchone()
        conn.close()
        if row:
            procedure, date, time = row
            await query.message.reply_text(
                f"✅ Ваш запис на {procedure} {date} о {time} підтверджено!"
            )

    # --- Відміна запису ---
    elif query.data.startswith('cancel_'):
        booking_id = int(query.data.replace('cancel_', ''))
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT name, procedure, date, time FROM bookings WHERE id=?", (booking_id,))
        row = c.fetchone()
        c.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
        conn.commit()
        conn.close()
        if row:
            name, procedure, date, time = row
            await query.message.reply_text("❌ Ваш запис успішно скасовано.")
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"❗️Клієнт {name} скасував запис: {procedure} {date} о {time}"
            )

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
        procedures = []
        procedure_codes = context.user_data.get('procedures', [])
        for code in procedure_codes:
            for title, code_value in PROCEDURE_OPTIONS:
                if code == code_value:
                    procedures.append(title)
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
        booking_ids = []
        for procedure in procedures:
            c.execute("INSERT INTO bookings (user_id, name, phone, procedure, date, time, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (user_id, name, phone, procedure, date, time, "Очікує підтвердження"))
            booking_ids.append(c.lastrowid)
            add_to_google_sheet(name, "", phone, procedure, date, time)
        conn.commit()
        conn.close()
        if len(procedures) == 1:
            procedures_text = procedures[0]
        else:
            procedures_text = '\n'.join([f"• {p}" for p in procedures])
        keyboard = [
            [InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm_{booking_ids[0]}"),
             InlineKeyboardButton("❌ Відмінити", callback_data=f"cancel_{booking_ids[0]}")],
            [InlineKeyboardButton("👑 Записатися ще", callback_data='book')],
            [InlineKeyboardButton("📋 Мої записи", callback_data='check_booking')],
            [InlineKeyboardButton("📸 Instagram", callback_data='instagram')],
            [InlineKeyboardButton("ℹ️ Допомога", callback_data='help')]
        ]
        await update.message.reply_text(
            f"🎉 Ви записані на:\n{procedures_text}\n{date} о {time}!\n"
            f"Ваш бʼюті-майстер Марія вже чекає зустрічі з вами 💖\n"
            "До зустрічі у світі краси! 👑✨\n\n"
            "Підтвердіть або скасуйте свій запис нижче:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"""📥 Новий запис:
ПІБ/Телефон: {name} / {phone}
Процедури: {', '.join(procedures)}
Дата: {date} о {time}"""
        )
        event_time = datetime.strptime(f"{date} {time}", "%d.%m %H:%M")
        remind_day = event_time - timedelta(days=1)
        remind_time = remind_day.replace(hour=10, minute=0, second=0, microsecond=0)
        remind_2h = event_time - timedelta(hours=2)
        now = datetime.now()
        # Нагадування за 1 день
        if remind_time > now:
            scheduler.add_job(
                send_reminder,
                'date',
                run_date=remind_time,
                args=[user_id, ', '.join(procedures), date, time, "day"]
            )
        # Нагадування за 2 години
        if remind_2h > now:
            scheduler.add_job(
                send_reminder,
                'date',
                run_date=remind_2h,
                args=[user_id, ', '.join(procedures), date, time, "2h"]
            )
        scheduler.start()
        context.user_data.clear()

    elif user_step == 'check_phone':
        phone = text.strip()
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("SELECT id, name, procedure, date, time, status FROM bookings WHERE phone LIKE ?", (f"%{phone}%",))
        rows = c.fetchall()
        conn.close()
        if rows:
            for rec in rows:
                booking_id, name, procedure, date, time, status = rec
                msg = f"{name}, {procedure}, {date} о {time}\nСтатус: *{status}*"
                buttons = []
                if status == "Очікує підтвердження":
                    buttons.append(InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm_{booking_id}"))
                    buttons.append(InlineKeyboardButton("❌ Відмінити", callback_data=f"cancel_{booking_id}"))
                reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None
                await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text("Записів не знайдено.\n\n💅 Зробіть свій перший запис через кнопку \"Записатися на процедуру\"!")
        context.user_data['step'] = None

    else:
        await update.message.reply_text("Оберіть дію за допомогою кнопок нижче та подаруйте собі красу! 💖")

async def send_reminder(user_id, procedures, date, time, mode="day"):
    from telegram import Bot
    bot = Bot(token=TOKEN)
    try:
        if mode == "day":
            text = f"⏰ Нагадування!\nЗавтра Ваш запис: {procedures} {date} о {time}.\nБʼюті-майстер чекає! 🌸"
        elif mode == "2h":
            text = f"💬 Ваш запис вже за 2 години: {procedures} {date} о {time}!\nГотуйтеся до краси! 👑✨"
        else:
            text = f"Нагадування про запис: {procedures} {date} о {time}."
        await bot.send_message(
            chat_id=user_id,
            text=text
        )
    except Exception as e:
        print(f"Не вдалося надіслати нагадування: {e}")

async def mybookings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('appointments.db')
    c = conn.cursor()
    c.execute("SELECT id, procedure, date, time, status FROM bookings WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    if rows:
        for rec in rows:
            booking_id, procedure, date, time, status = rec
            msg = f"✨ {procedure}\n🗓️ {date} о {time}\nСтатус: *{status}*"
            buttons = []
            if status == "Очікує підтвердження":
                buttons.append(InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm_{booking_id}"))
                buttons.append(InlineKeyboardButton("❌ Відмінити", callback_data=f"cancel_{booking_id}"))
            reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None
            await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text("Записів не знайдено. Час оновити свій образ! 💄")

set_schedule_handler = schedule_handler

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("instagram", instagram_handler))
    app.add_handler(CommandHandler("calendar", calendar_handler))
    app.add_handler(CommandHandler("weekcalendar", week_calendar_handler))
    app.add_handler(CommandHandler("schedule", schedule_handler))
    app.add_handler(CommandHandler("set_schedule", set_schedule_handler))
    app.add_handler(CommandHandler("delete_day", delete_day_handler))
    app.add_handler(CommandHandler("mybookings", mybookings_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.run_polling()

if __name__ == "__main__":
    main()

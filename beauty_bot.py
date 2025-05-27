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
from datetime import datetime, timedelta

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

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Головне меню
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
            "✨ Обери свою бʼюті-процедуру! Серденьком обирай те, що подобається найбільше — або натисни ⬅️ щоб повернутись до мрій!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data.clear()
        return

    # --- Обробка вибору процедури ---
    if query.data.startswith('proc_'):
        procedures = {
            'proc_brows': "Корекція брів (ідеальна форма)",
            'proc_tint_brows': "Фарбування + корекція брів",
            'proc_lam_brows': "Ламінування брів (WOW-ефект)",
            'proc_lam_lashes': "Ламінування вій (виразний погляд)",
        }
        procedure = procedures.get(query.data, "Невідома процедура")
        context.user_data['procedure'] = procedure
        # Показати 7 наступних днів (усі дні тижня)
        today = datetime.now().date()
        dates = [(today + timedelta(days=i)).strftime("%d.%m") for i in range(7)]
        keyboard = [
            [InlineKeyboardButton(date, callback_data=f"date_{date}")]
            for date in dates
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_procedure")])
        await query.message.reply_text(
            "🌸 Обери зручний день для запису — працюємо за різним графіком у будні й вихідні!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # --- Вибір часу в залежності від дня тижня ---
    if query.data.startswith("date_"):
        date = query.data.replace("date_", "")
        context.user_data["date"] = date

        # Визначаємо тип дня
        year = datetime.now().year
        dt = datetime.strptime(f"{date}.{year}", "%d.%m.%Y")
        weekday = dt.weekday()  # 0 = Пн ... 6 = Нд

        if weekday < 5:  # Пн–Пт
            times = [f"{h}:00" for h in range(14, 19)]  # 14:00–18:00
        else:  # Сб–Нд
            times = [f"{h}:00" for h in range(11, 17)]  # 11:00–16:00

        keyboard = [
            [InlineKeyboardButton(time, callback_data=f"time_{time}")]
            for time in times
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_procedure")])
        await query.message.reply_text(
            "👑 Обери свій зірковий час! Графік залежить від дня тижня 💖",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # --- Вибір часу ---
    if query.data.startswith("time_"):
        time = query.data.replace("time_", "")
        context.user_data["time"] = time
        context.user_data["step"] = "input_name_phone"
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data=f"date_{context.user_data['date']}")]
        ]
        await query.message.reply_text(
            "✨ Ще крок до краси! Введи ім’я та телефон, наприклад: Марія, 0930001122",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_step = context.user_data.get('step')
    text = update.message.text

    # Введення ПІБ і телефону
    if user_step == "input_name_phone":
        try:
            name, phone = [x.strip() for x in text.split(',', 1)]
        except Exception:
            await update.message.reply_text("Будь ласка, введи дані у форматі: Ім'я, телефон (наприклад, Марія, 0930001122)")
            return
        procedure = context.user_data.get("procedure")
        date = context.user_data.get("date")
        time = context.user_data.get("time")
        user_id = update.effective_user.id
        # Записуємо в базу
        conn = sqlite3.connect('appointments.db')
        c = conn.cursor()
        c.execute("INSERT INTO bookings (name, phone, procedure, date, time, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                  (name, phone, procedure, date, time, user_id))
        conn.commit()
        conn.close()
        await update.message.reply_text(
            f"💖 Дякую, {name}! Твій запис на “{procedure}” {date} о {time} збережено!\n"
            "Я з тобою зв’яжусь для підтвердження.\n\n"
            "✨ Якщо хочеш записатись ще — просто натисни /start"
        )
        context.user_data.clear()
        return

def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("instagram", instagram_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()

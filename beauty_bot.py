import os
from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
)
from google_sheets import add_to_google_sheet
import re

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = 1035792183  # ← твій ID

(
    MENU, CHOOSE_PROCEDURE, INPUT_DATE, INPUT_CONTACT, CHOOSE_TIME,
    CHECK_MY_BOOKINGS
) = range(6)

PROCEDURES = [
    "Корекція брів",
    "Фарбування та корекція брів",
    "Ламінування брів",
    "Ламінування вій"
]

TIME_OPTIONS = ["14:00", "15:00", "16:00", "17:00"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [
        ["📋 Записатися на процедуру"],
        ["📅 Перевірити мій запис"]
    ]
    await update.message.reply_text(
        "Привіт! Оберіть дію:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    )
    return MENU

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📋 Записатися на процедуру":
        reply_keyboard = [[p] for p in PROCEDURES]
        await update.message.reply_text(
            "Оберіть процедуру:",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
        )
        return CHOOSE_PROCEDURE
    elif text == "📅 Перевірити мій запис":
        await update.message.reply_text(
            "Введіть номер телефону, який ви залишали при записі (наприклад: 0931234567):",
            reply_markup=ReplyKeyboardRemove()
        )
        return CHECK_MY_BOOKINGS
    else:
        await update.message.reply_text("Оберіть дію із меню.")
        return MENU

async def choose_procedure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    procedure = update.message.text
    if procedure not in PROCEDURES:
        await update.message.reply_text("Оберіть процедуру із списку.")
        return CHOOSE_PROCEDURE
    context.user_data["procedure"] = procedure
    await update.message.reply_text(
        "Введіть дату у форматі ДД.ММ (наприклад: 28.05):",
        reply_markup=ReplyKeyboardRemove()
    )
    return INPUT_DATE

async def input_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date = update.message.text.strip()
    if not re.match(r"\d{2}\.\d{2}", date):
        await update.message.reply_text("Неправильний формат дати. Введіть у форматі ДД.ММ (наприклад: 28.05):")
        return INPUT_DATE
    context.user_data["date"] = date
    await update.message.reply_text(
        "Введіть ПІБ та номер телефону через кому (наприклад: Іваненко Марія, 0931234567):"
    )
    return INPUT_CONTACT

async def input_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.message.text.strip()
    match = re.match(r"(.+),\s*([\d\+\-\(\) ]{10,})", data)
    if not match:
        await update.message.reply_text("Будь ласка, введіть ПІБ та телефон у форматі: Іваненко Марія, 0931234567")
        return INPUT_CONTACT
    name, phone = match.groups()
    context.user_data["name"] = name.strip()
    context.user_data["phone"] = phone.strip()
    reply_keyboard = [[t] for t in TIME_OPTIONS]
    await update.message.reply_text(
        "Оберіть час:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    )
    return CHOOSE_TIME

async def choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time = update.message.text
    if time not in TIME_OPTIONS:
        await update.message.reply_text("Оберіть час із кнопок:")
        return CHOOSE_TIME
    context.user_data["time"] = time
    # Запис у Google Sheets
    add_to_google_sheet(
        name=context.user_data["name"],
        surname="",  # Можеш виділити прізвище, якщо треба
        phone=context.user_data["phone"],
        procedure=context.user_data["procedure"],
        date=context.user_data["date"],
        time=context.user_data["time"],
    )
    # Надсилання сповіщення адміну
    admin_message = (
        "Новий запис!\n"
        f"Процедура: {context.user_data['procedure']}\n"
        f"Дата: {context.user_data['date']}\n"
        f"Час: {context.user_data['time']}\n"
        f"Клієнт: {context.user_data['name']}\n"
        f"Телефон: {context.user_data['phone']}"
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_message)
    except Exception as e:
        print(f"Помилка надсилання адміну: {e}")

    await update.message.reply_text(
        f"Вас записано на {context.user_data['procedure']} ({context.user_data['date']} о {context.user_data['time']}). Дякуємо!",
        reply_markup=ReplyKeyboardMarkup([
            ["📋 Записатися на процедуру", "📅 Перевірити мій запис"]
        ], resize_keyboard=True)
    )
    return MENU

# Заглушка — перевірка записів
async def check_my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    bookings = []  # Реалізуй цю функцію в google_sheets.py
    if bookings:
        text = "\n".join([
            f"{b['procedure']} {b['date']} {b['time']}"
            for b in bookings
        ])
    else:
        text = "Записів не знайдено."
    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup([
            ["📋 Записатися на процедуру", "📅 Перевірити мій запис"]
        ], resize_keyboard=True)
    )
    return MENU

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu)],
            CHOOSE_PROCEDURE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_procedure)],
            INPUT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_date)],
            INPUT_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_contact)],
            CHOOSE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_time)],
            CHECK_MY_BOOKINGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_my_bookings)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    main()

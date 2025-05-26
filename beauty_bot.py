import os
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
)
from google_sheets import add_to_google_sheet
import re

TOKEN = os.getenv("TELEGRAM_TOKEN")

# Стадії діалогу
(
    MENU, CHOOSE_PROCEDURE, INPUT_DATE, INPUT_CONTACT, CONFIRM_BOOKING,
    CHECK_MY_BOOKINGS, DONE
) = range(7)

PROCEDURES = [
    "Корекція брів",
    "Фарбування та корекція брів",
    "Ламінування брів",
    "Ламінування вій"
]

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
        "Введіть дату у форматі ДД.MM (наприклад: 28.05):",
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
    # Запис у Google Sheets
    add_to_google_sheet(
        name=context.user_data["name"],
        surname="", # якщо треба виділити, можу розбити name
        phone=context.user_data["phone"],
        procedure=context.user_data["procedure"],
        date=context.user_data["date"],
        time="", # якщо хочеш ще й час, треба додати окреме питання
    )
    await update.message.reply_text(
        f"Вас записано на {context.user_data['procedure']} ({context.user_data['date']}). Дякуємо!",
        reply_markup=ReplyKeyboardMarkup([
            ["📋 Записатися на процедуру", "📅 Перевірити мій запис"]
        ], resize_keyboard=True)
    )
    return MENU

# Заглушка — приклад для "перевірити мій запис"
async def check_my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    # Тут треба реалізувати отримання із Google Sheets за номером телефону
    # Напишу псевдо, бо немає функції у твоєму google_sheets.py
    # bookings = get_bookings_by_phone(phone)
    bookings = []  # <-- реалізуй цю функцію сам або дай доступ до таблиці — напишу!
    if bookings:
        text = "\n".join([
            f"{b['procedure']} ({b['date']})"
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
            CHECK_MY_BOOKINGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_my_bookings)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    main()

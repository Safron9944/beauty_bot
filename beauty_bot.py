import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from google_sheets import add_to_google_sheet

TOKEN = os.getenv("TELEGRAM_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Вітаю! Я бот для запису клієнтів. Введіть: /book Ім'я Прізвище Телефон Процедура Дата Час")

async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = context.args
        if len(data) != 6:
            await update.message.reply_text("Формат: /book Ім'я Прізвище Телефон Процедура Дата Час")
            return
        name, surname, phone, procedure, date, time = data
        add_to_google_sheet(name, surname, phone, procedure, date, time)
        await update.message.reply_text(f"Дякую! Вас записано на {date} о {time} на процедуру {procedure}.")
    except Exception as e:
        await update.message.reply_text(f"Сталася помилка: {e}")

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("book", book))

    application.run_polling()

if __name__ == "__main__":
    main()

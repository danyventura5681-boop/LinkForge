import os
from telegram.ext import ApplicationBuilder, CommandHandler
from handlers.start import start

BOT_TOKEN = os.getenv("BOT_TOKEN")


def main():

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN no encontrado")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    print("✅ Bot iniciado correctamente")

    app.run_polling()


if __name__ == "__main__":
    main()

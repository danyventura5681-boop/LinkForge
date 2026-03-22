import os
from telegram.ext import ApplicationBuilder, CommandHandler
from keep_alive import keep_alive

# importar handler
from handlers.start import start


BOT_TOKEN = os.getenv("BOT_TOKEN")


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN no encontrado")

    # Crear aplicación
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Registrar handlers
    app.add_handler(CommandHandler("start", start))

    print("✅ Bot iniciado correctamente...")

    # Iniciar bot
    app.run_polling()


if __name__ == "__main__":
    keep_alive()
    main()

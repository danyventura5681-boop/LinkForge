import os
from telegram.ext import ApplicationBuilder, CommandHandler
from keep_alive import keep_alive

BOT_TOKEN = os.getenv("BOT_TOKEN")


async def start(update, context):
    await update.message.reply_text(
        "🚀 LinkForge está activo."
    )


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN no encontrado")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    print("✅ Bot iniciado...")
    app.run_polling()


if __name__ == "__main__":
    keep_alive()
    main()

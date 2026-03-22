import os
import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler
from keep_alive import keep_alive

BOT_TOKEN = os.getenv("BOT_TOKEN")


async def start(update, context):
    await update.message.reply_text("🚀 LinkForge está activo.")


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN no encontrado")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    print("✅ Bot iniciado correctamente...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Mantener vivo
    await asyncio.Event().wait()


if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())

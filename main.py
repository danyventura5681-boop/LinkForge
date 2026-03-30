import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN no configurado")

logger.info(f"✅ Token cargado correctamente")

from handlers.start import start, button_handler, back_to_start
from handlers.link import (
    register_start, process_link_message, confirm_replace_link, 
    confirm_add_link, cancel_register_callback
)

telegram_app = Application.builder().token(TOKEN).build()

# ===========================================
# HANDLER DE COMANDOS
# ===========================================
telegram_app.add_handler(CommandHandler("start", start))

# ===========================================
# HANDLER GENÉRICO TEMPORAL (captura TODOS los callbacks)
# ===========================================
async def catch_all_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info(f"📣📣📣 TODOS LOS CALLBACKS: {query.data} 📣📣📣")
    await query.answer()
    
    # Si es volver_menu, ejecutar back_to_start
    if query.data == "volver_menu":
        logger.info("🎯 Ejecutando back_to_start manualmente")
        await back_to_start(update, context)
    else:
        # Para otros botones, pasar al button_handler
        await button_handler(update, context)

telegram_app.add_handler(CallbackQueryHandler(catch_all_callbacks))

# ===========================================
# HANDLERS DE MENSAJES
# ===========================================
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_link_message))

# ===========================================
# INICIAR BOT CON POLLING
# ===========================================
async def main():
    await telegram_app.initialize()
    await telegram_app.bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Webhook eliminado")
    logger.info("🚀 LinkForge iniciando con POLLING...")
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

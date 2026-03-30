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
# HANDLERS DE COMANDOS
# ===========================================
telegram_app.add_handler(CommandHandler("start", start))

# ===========================================
# HANDLERS DE CALLBACKS
# ===========================================
# Handler para volver (patrón flexible)
telegram_app.add_handler(CallbackQueryHandler(back_to_start, pattern="volver_menu"))

# Handlers específicos de links
telegram_app.add_handler(CallbackQueryHandler(confirm_replace_link, pattern="^confirm_replace$"))
telegram_app.add_handler(CallbackQueryHandler(confirm_add_link, pattern="^confirm_add_link$"))
telegram_app.add_handler(CallbackQueryHandler(cancel_register_callback, pattern="^cancel_register$"))

# Handler general de botones
telegram_app.add_handler(CallbackQueryHandler(button_handler, pattern="^(register_link|show_ranking|earn_reputation|referral|vip_info|admin_panel)$"))

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

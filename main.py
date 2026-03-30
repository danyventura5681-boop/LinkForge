import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===========================================
# DEPURACIÓN: VER VARIABLES DE ENTORNO
# ===========================================
logger.info("=== VARIABLES DE ENTORNO DISPONIBLES ===")
for key in os.environ.keys():
    # No mostramos valores completos por seguridad, solo nombres
    logger.info(f"  {key}")

# Leer token
TOKEN = os.environ.get("BOT_TOKEN")
logger.info(f"BOT_TOKEN encontrado: {'SI' if TOKEN else 'NO'}")

if not TOKEN:
    logger.error("❌ BOT_TOKEN no configurado")
    logger.error("Lista de variables disponibles (primeros 10):")
    for key in list(os.environ.keys())[:10]:
        logger.error(f"  {key}")
    raise ValueError("❌ BOT_TOKEN no configurado")

logger.info(f"✅ Token cargado (primeros 10 chars: {TOKEN[:10]}...)")

# ===========================================
# IMPORTAR HANDLERS
# ===========================================
try:
    from handlers.start import start, button_handler, back_to_start
    logger.info("✅ handlers.start importado correctamente")
except Exception as e:
    logger.error(f"❌ Error importando handlers.start: {e}")
    raise

try:
    from handlers.link import (
        register_start, process_link_message, confirm_replace_link, 
        confirm_add_link, cancel_register_callback
    )
    logger.info("✅ handlers.link importado correctamente")
except Exception as e:
    logger.error(f"❌ Error importando handlers.link: {e}")
    raise

# ===========================================
# CREAR APP DE TELEGRAM
# ===========================================
telegram_app = Application.builder().token(TOKEN).build()

# ===========================================
# HANDLERS DE COMANDOS
# ===========================================
telegram_app.add_handler(CommandHandler("start", start))

# ===========================================
# HANDLERS DE CALLBACKS
# ===========================================
telegram_app.add_handler(CallbackQueryHandler(button_handler, pattern="^(register_link|show_ranking|earn_reputation|referral|vip_info|admin_panel)$"))
telegram_app.add_handler(CallbackQueryHandler(confirm_replace_link, pattern="^confirm_replace$"))
telegram_app.add_handler(CallbackQueryHandler(confirm_add_link, pattern="^confirm_add_link$"))
telegram_app.add_handler(CallbackQueryHandler(cancel_register_callback, pattern="^cancel_register$"))
telegram_app.add_handler(CallbackQueryHandler(back_to_start, pattern="^volver_menu$"))

# ===========================================
# HANDLERS DE MENSAJES
# ===========================================
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_link_message))

# ===========================================
# INICIAR BOT CON POLLING
# ===========================================
async def main():
    logger.info("🔧 Inicializando bot...")
    await telegram_app.initialize()
    
    logger.info("🗑️ Eliminando webhook existente...")
    await telegram_app.bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Webhook eliminado")

    logger.info("🚀 LinkForge iniciando con POLLING...")
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    logger.info("✅ Bot iniciado correctamente, esperando mensajes...")

    # Mantener el bot corriendo
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot detenido por el usuario")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        raise

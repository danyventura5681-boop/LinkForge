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

# ===========================================
# IMPORTAR HANDLERS
# ===========================================
from handlers.start import start, button_handler, back_to_start
from handlers.link import (
    register_start, process_link_message, confirm_replace_link, 
    confirm_add_link, cancel_register_callback
)
from handlers.ranking import ranking, ranking_button_handler
from handlers.reputation import earn_reputation, visit_link, more_links
from handlers.referral import referral, process_referral
from handlers.admin import (
    admin_panel, add_reputation_start, add_reputation_get_user, 
    add_reputation_amount, cancel_admin, make_admin_action, make_admin_process,
    ban_user_action, ban_user_process, unban_user_action, unban_user_process, list_users
)
from handlers.vip import (
    vip_menu, buy_vip, check_payment, check_payment_retry, confirm_payment_command
)

# Estados para conversación (admin)
WAITING_USER_ID, WAITING_REPUTATION = range(2)

# ===========================================
# CREAR APP DE TELEGRAM
# ===========================================
telegram_app = Application.builder().token(TOKEN).build()

# ===========================================
# HANDLERS DE COMANDOS
# ===========================================
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("confirmar", confirm_payment_command))

# Handler para referidos (sin comando, desde el enlace)
telegram_app.add_handler(CommandHandler("start", process_referral))

# ===========================================
# HANDLERS DE MENSAJES (MODO CONVERSACIÓN)
# ===========================================
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_link_message))

# ===========================================
# HANDLERS DE CALLBACKS
# ===========================================

# 1. Handler para volver al menú (prioridad alta)
telegram_app.add_handler(CallbackQueryHandler(back_to_start, pattern="^volver_menu$"))

# 2. Handler para ranking
telegram_app.add_handler(CallbackQueryHandler(ranking_button_handler, pattern="^refresh_ranking$"))

# 3. Handler para reputación
telegram_app.add_handler(CallbackQueryHandler(visit_link, pattern="^visit_link_"))
telegram_app.add_handler(CallbackQueryHandler(more_links, pattern="^more_links$"))

# 4. Handler para links
telegram_app.add_handler(CallbackQueryHandler(confirm_replace_link, pattern="^confirm_replace$"))
telegram_app.add_handler(CallbackQueryHandler(confirm_add_link, pattern="^confirm_add_link$"))
telegram_app.add_handler(CallbackQueryHandler(cancel_register_callback, pattern="^cancel_register$"))

# 5. Handler para VIP
telegram_app.add_handler(CallbackQueryHandler(vip_menu, pattern="^vip_menu$"))
telegram_app.add_handler(CallbackQueryHandler(buy_vip, pattern="^buy_vip_"))
telegram_app.add_handler(CallbackQueryHandler(check_payment, pattern="^check_payment$"))
telegram_app.add_handler(CallbackQueryHandler(check_payment_retry, pattern="^check_payment_retry$"))

# 6. Handler para admin - acciones directas
telegram_app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
telegram_app.add_handler(CallbackQueryHandler(list_users, pattern="^admin_list_users$"))

# 7. Handler general de botones principales
telegram_app.add_handler(CallbackQueryHandler(button_handler, pattern="^(register_link|show_ranking|earn_reputation|referral|vip_info|admin_panel)$"))

# ===========================================
# CONVERSATION HANDLERS PARA ADMIN
# ===========================================
admin_add_reputation_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_reputation_start, pattern="^admin_add_reputation$")],
    states={
        WAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_reputation_get_user)],
        WAITING_REPUTATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_reputation_amount)],
    },
    fallbacks=[CallbackQueryHandler(cancel_admin, pattern="^admin_panel$")],
)
telegram_app.add_handler(admin_add_reputation_conv)

admin_make_admin_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(make_admin_action, pattern="^admin_make_admin$")],
    states={
        WAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, make_admin_process)],
    },
    fallbacks=[CallbackQueryHandler(cancel_admin, pattern="^admin_panel$")],
)
telegram_app.add_handler(admin_make_admin_conv)

admin_ban_user_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(ban_user_action, pattern="^admin_ban_user$")],
    states={
        WAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_user_process)],
    },
    fallbacks=[CallbackQueryHandler(cancel_admin, pattern="^admin_panel$")],
)
telegram_app.add_handler(admin_ban_user_conv)

admin_unban_user_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(unban_user_action, pattern="^admin_unban_user$")],
    states={
        WAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, unban_user_process)],
    },
    fallbacks=[CallbackQueryHandler(cancel_admin, pattern="^admin_panel$")],
)
telegram_app.add_handler(admin_unban_user_conv)

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

import os
import logging
import asyncio
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from fastapi import FastAPI
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN no configurado")

logger.info(f"✅ Token cargado correctamente")

# ===========================================
# IMPORTAR HANDLERS (TODOS)
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
    add_reputation_amount, reduce_reputation_start, reduce_reputation_get_user,
    reduce_reputation_amount, cancel_admin, make_admin_action, make_admin_process,
    ban_user_action, ban_user_process, unban_user_action, unban_user_process, list_users
)
from handlers.vip import (
    vip_menu, buy_vip, check_payment, check_payment_retry, confirm_payment_command,
    manual_payment_start, manual_payment_get_amount, manual_payment_get_address, manual_payment_get_tx,
    WAITING_PAYMENT_AMOUNT, WAITING_PAYMENT_ADDRESS, WAITING_PAYMENT_TX
)

# Estados para conversación (admin)
WAITING_USER_ID = 1
WAITING_REPUTATION = 2
WAITING_REDUCE_REPUTATION = 3

# ===========================================
# FUNCIONES PARA NOTIFICACIONES (cron-job)
# ===========================================
async def check_expiring_links():
    """Revisa links que expiran pronto y envía notificaciones"""
    try:
        from database.database import get_expiring_links, get_user
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        checkpoints = [48, 24, 15, 10, 5, 2, 1]

        for hours in checkpoints:
            expiring_links = get_expiring_links(hours)

            for link in expiring_links:
                user_id = link.user_id
                user = get_user(user_id)

                if not user:
                    continue

                if hours == 48:
                    message = (
                        f"⏰ **Tu link expira en 48 horas.**\n\n"
                        f"🔗 `{link.url}`\n\n"
                        f"Actualiza a VIP para extender la promoción a 30 días sin perder reputación.\n\n"
                        f"⭐ Usa el botón VIP para más información."
                    )
                elif hours <= 24:
                    message = (
                        f"⚠️ **¡Tu link expira en {hours} horas!**\n\n"
                        f"🔗 `{link.url}`\n\n"
                        f"Renueva con VIP para mantener tu reputación y extender la promoción.\n\n"
                        f"⭐ Usa el botón VIP para más información."
                    )
                else:
                    message = (
                        f"🔔 **Recordatorio:** Tu link expira en {hours} horas.\n\n"
                        f"🔗 `{link.url}`\n\n"
                        f"¡Asegura tu reputación con VIP!"
                    )

                try:
                    await telegram_app.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⭐ VIP", callback_data="vip_info")]]),
                        parse_mode='Markdown'
                    )
                    logger.info(f"✅ Notificación enviada a {user_id}: expira en {hours}h")
                except Exception as e:
                    logger.error(f"❌ Error enviando notificación a {user_id}: {e}")

    except Exception as e:
        logger.error(f"❌ Error en check_expiring_links: {e}")

# ===========================================
# SERVIDOR WEB PARA CRON-JOB Y UPTIMEROBOT
# ===========================================
app = FastAPI()

@app.get("/")
@app.get("/healthcheck")
async def health():
    """Endpoint para UptimeRobot - mantiene el bot vivo"""
    return {"status": "ok", "service": "LinkForge"}

@app.get("/check_expiring")
async def trigger_expiring_check():
    """Endpoint para cron-job.org - envía notificaciones de expiración"""
    try:
        await check_expiring_links()
        return {"status": "ok", "message": "Notificaciones de expiración procesadas"}
    except Exception as e:
        logger.error(f"❌ Error en /check_expiring: {e}")
        return {"status": "error", "message": str(e)}

def run_web_server():
    """Ejecuta el servidor web en un hilo separado"""
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
    logger.info(f"🌐 Servidor web iniciado en puerto {port}")

# ===========================================
# CREAR APP DE TELEGRAM
# ===========================================
telegram_app = Application.builder().token(TOKEN).build()

# ===========================================
# 1. PRIMERO: COMMAND HANDLERS (máxima prioridad)
# ===========================================
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("start", process_referral))
telegram_app.add_handler(CommandHandler("confirmar", confirm_payment_command))

# ===========================================
# 2. SEGUNDO: CONVERSATION HANDLERS (ANTES DE CALLBACK)
# ===========================================

# ✅ HANDLER PARA AÑADIR REPUTACIÓN
add_reputation_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_reputation_start, pattern="^admin_add_reputation$")],
    states={
        WAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_reputation_get_user)],
        WAITING_REPUTATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_reputation_amount)],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_admin, pattern="^admin_panel$"),
        CommandHandler("cancel", cancel_admin),
    ],
)
telegram_app.add_handler(add_reputation_conv)

# ✅ HANDLER PARA REDUCIR REPUTACIÓN
reduce_reputation_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(reduce_reputation_start, pattern="^admin_reduce_reputation$")],
    states={
        WAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, reduce_reputation_get_user)],
        WAITING_REDUCE_REPUTATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, reduce_reputation_amount)],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_admin, pattern="^admin_panel$"),
        CommandHandler("cancel", cancel_admin),
    ],
)
telegram_app.add_handler(reduce_reputation_conv)

# ✅ HANDLER PARA HACER ADMIN
make_admin_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(make_admin_action, pattern="^admin_make_admin$")],
    states={
        WAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, make_admin_process)],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_admin, pattern="^admin_panel$"),
        CommandHandler("cancel", cancel_admin),
    ],
)
telegram_app.add_handler(make_admin_conv)

# ✅ HANDLER PARA BANEAR USUARIO
ban_user_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(ban_user_action, pattern="^admin_ban_user$")],
    states={
        WAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_user_process)],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_admin, pattern="^admin_panel$"),
        CommandHandler("cancel", cancel_admin),
    ],
)
telegram_app.add_handler(ban_user_conv)

# ✅ HANDLER PARA DESBANEAR USUARIO
unban_user_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(unban_user_action, pattern="^admin_unban_user$")],
    states={
        WAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, unban_user_process)],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_admin, pattern="^admin_panel$"),
        CommandHandler("cancel", cancel_admin),
    ],
)
telegram_app.add_handler(unban_user_conv)

# ✅ HANDLER PARA PAGO MANUAL
manual_payment_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(manual_payment_start, pattern="^manual_payment$")],
    states={
        WAITING_PAYMENT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_payment_get_amount)],
        WAITING_PAYMENT_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_payment_get_address)],
        WAITING_PAYMENT_TX: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_payment_get_tx)],
    },
    fallbacks=[CommandHandler("cancel", cancel_admin)],
)
telegram_app.add_handler(manual_payment_conv)

# ===========================================
# 3. TERCERO: CALLBACK QUERY HANDLERS
# ===========================================
telegram_app.add_handler(CallbackQueryHandler(back_to_start, pattern="^volver_menu$"))
telegram_app.add_handler(CallbackQueryHandler(ranking_button_handler, pattern="^refresh_ranking$"))
telegram_app.add_handler(CallbackQueryHandler(visit_link, pattern="^link_"))  # ✅ CORREGIDO: link_1, link_2, etc.
telegram_app.add_handler(CallbackQueryHandler(more_links, pattern="^more_links$"))
telegram_app.add_handler(CallbackQueryHandler(confirm_replace_link, pattern="^confirm_replace$"))
telegram_app.add_handler(CallbackQueryHandler(confirm_add_link, pattern="^confirm_add_link$"))
telegram_app.add_handler(CallbackQueryHandler(cancel_register_callback, pattern="^cancel_register$"))
telegram_app.add_handler(CallbackQueryHandler(vip_menu, pattern="^vip_menu$"))
telegram_app.add_handler(CallbackQueryHandler(buy_vip, pattern="^buy_vip_"))
telegram_app.add_handler(CallbackQueryHandler(check_payment, pattern="^check_payment$"))
telegram_app.add_handler(CallbackQueryHandler(check_payment_retry, pattern="^check_payment_retry$"))
telegram_app.add_handler(CallbackQueryHandler(manual_payment_start, pattern="^manual_payment$"))
telegram_app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
telegram_app.add_handler(CallbackQueryHandler(list_users, pattern="^admin_list_users$"))
telegram_app.add_handler(CallbackQueryHandler(button_handler, pattern="^(register_link|show_ranking|earn_reputation|referral|vip_info|admin_panel)$"))

# ===========================================
# 4. CUARTO: MESSAGE HANDLER (mínima prioridad - AL FINAL)
# ===========================================
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_link_message))

# ===========================================
# INICIAR BOT CON POLLING + SERVIDOR WEB
# ===========================================
async def main():
    # Iniciar servidor web en hilo separado
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("🌐 Servidor web iniciado")

    await telegram_app.initialize()
    await telegram_app.bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Webhook eliminado")
    logger.info("🚀 LinkForge iniciando con POLLING...")
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

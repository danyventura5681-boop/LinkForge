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
from handlers.reputation import earn_reputation, visit_link, more_links, confirm_link_callback, cancel_verification, visit_links
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
from handlers.reputation import instagram_task, WAITING_INSTAGRAM_USERNAME, instagram_reward, confirm_instagram_process, confirm_instagram_start
from handlers.link import change_link_start, process_change_link, WAITING_NEW_LINK

# ===========================================
# NUEVOS IMPORTS PARA LinkForge 1.1
# ===========================================
from handlers.daily_reward import daily_reward
from handlers.video import (
    top_videos, watch_video, confirm_video_callback, 
    cancel_video_verification, refresh_videos
)
from handlers.promote import (
    promote_menu, add_video_start, process_video_url, process_video_title,
    my_uploaded_videos, delete_video_callback, cancel_promote,
    WAITING_VIDEO_URL, WAITING_VIDEO_TITLE
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
        from database import get_expiring_links, get_user
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

@app.get("/verify_payments")
async def verify_payments_endpoint():
    """
    Endpoint para verificar pagos pendientes.
    Puede ser llamado por cron-job cada 5-10 minutos.
    
    Ejemplo: https://tu-bot.railway.app/verify_payments
    """
    try:
        logger.info("🔍 Iniciando verificación de pagos pendientes...")

        from services.blockchain import scan_pending_payments
        results = scan_pending_payments()

        logger.info(f"✅ Verificación completada: {results}")

        return {
            "status": "ok",
            "message": "Pagos verificados",
            "verified": results.get("verified", 0),
            "failed": results.get("failed", 0),
            "errors": results.get("errors", [])
        }
    except Exception as e:
        logger.error(f"❌ Error en /verify_payments: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/check_all")
async def check_all():
    """
    Ejecuta TODAS las verificaciones (expiring + payments).
    Útil para un único cron-job que lo haga todo.
    """
    try:
        logger.info("🔄 Ejecutando verificaciones completas...")

        # 1. Verificar links que expiran
        await check_expiring_links()
        logger.info("✅ Verificación de links completada")

        # 2. Verificar pagos pendientes
        from services.blockchain import scan_pending_payments
        payment_results = scan_pending_payments()
        logger.info(f"✅ Verificación de pagos completada: {payment_results}")

        return {
            "status": "ok",
            "message": "Todas las verificaciones completadas",
            "payments": payment_results
        }
    except Exception as e:
        logger.error(f"❌ Error en /check_all: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

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

# ✅ HANDLER PARA TAREA DE INSTAGRAM (CORREGIDO)
instagram_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(instagram_task, pattern="^instagram_task$")],
    states={
        WAITING_INSTAGRAM_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_instagram_process)],
    },
    fallbacks=[
        CallbackQueryHandler(earn_reputation, pattern="^earn_reputation$"),
        CommandHandler("cancel", earn_reputation),
    ],
)
telegram_app.add_handler(instagram_conv)

# ✅ HANDLER PARA CAMBIAR LINK
change_link_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(change_link_start, pattern="^change_link$")],
    states={
        WAITING_NEW_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_change_link)],
    },
    fallbacks=[
        CallbackQueryHandler(back_to_start, pattern="^volver_menu$"),
        CommandHandler("cancel", back_to_start),
    ],
)
telegram_app.add_handler(change_link_conv)

# ✅ NUEVO HANDLER PARA AGREGAR VIDEOS (PROMOCIONAR CONTENIDO)
add_video_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_video_start, pattern="^add_video$")],
    states={
        WAITING_VIDEO_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_video_url)],
        WAITING_VIDEO_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_video_title)],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_promote, pattern="^promote_menu$"),
        CommandHandler("cancel", cancel_promote),
    ],
)
telegram_app.add_handler(add_video_conv)

# ===========================================
# 3. TERCERO: CALLBACK QUERY HANDLERS
# ===========================================
telegram_app.add_handler(CallbackQueryHandler(back_to_start, pattern="^volver_menu$"))
telegram_app.add_handler(CallbackQueryHandler(ranking_button_handler, pattern="^refresh_ranking$"))
telegram_app.add_handler(CallbackQueryHandler(visit_link, pattern="^link_"))
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
telegram_app.add_handler(CallbackQueryHandler(button_handler, pattern="^(register_link|show_ranking|earn_reputation|referral|vip_info|admin_panel|daily_reward|top_videos|promote_menu)$"))
telegram_app.add_handler(CallbackQueryHandler(instagram_task, pattern="^instagram_task$"))
telegram_app.add_handler(CallbackQueryHandler(change_link_start, pattern="^change_link$"))

# ✅ NUEVOS CALLBACKS PARA EL SISTEMA DE VERIFICACIÓN DE VISITAS
telegram_app.add_handler(CallbackQueryHandler(confirm_link_callback, pattern="^confirm_link_"))
telegram_app.add_handler(CallbackQueryHandler(cancel_verification, pattern="^cancel_verification$"))

# ✅ NUEVOS CALLBACKS PARA VISITAR LINKS
telegram_app.add_handler(CallbackQueryHandler(visit_links, pattern="^visit_links$"))

# ✅ NUEVOS CALLBACKS PARA EL SISTEMA DE VIDEOS
telegram_app.add_handler(CallbackQueryHandler(top_videos, pattern="^top_videos$"))
telegram_app.add_handler(CallbackQueryHandler(watch_video, pattern="^video_"))
telegram_app.add_handler(CallbackQueryHandler(confirm_video_callback, pattern="^confirm_video_"))
telegram_app.add_handler(CallbackQueryHandler(cancel_video_verification, pattern="^cancel_video_verification$"))
telegram_app.add_handler(CallbackQueryHandler(refresh_videos, pattern="^refresh_videos$"))

# ✅ NUEVOS CALLBACKS PARA PROMOCIONAR CONTENIDO (VIP)
telegram_app.add_handler(CallbackQueryHandler(promote_menu, pattern="^promote_menu$"))
telegram_app.add_handler(CallbackQueryHandler(my_uploaded_videos, pattern="^my_uploaded_videos$"))
telegram_app.add_handler(CallbackQueryHandler(delete_video_callback, pattern="^delete_video_"))
telegram_app.add_handler(CallbackQueryHandler(daily_reward, pattern="^daily_reward$"))

# ✅ NUEVO CALLBACK PARA TAREA INSTAGRAM
telegram_app.add_handler(CallbackQueryHandler(instagram_reward, pattern="^instagram_reward$"))
telegram_app.add_handler(CallbackQueryHandler(confirm_instagram_start, pattern="^confirm_instagram$"))

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
    logger.info("🚀 LinkForge 1.1 iniciando con POLLING...")
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
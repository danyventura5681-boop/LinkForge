import os
import logging
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
import uvicorn
import asyncio

# Configuración
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN no configurado")

PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", f"https://localhost:{PORT}")

# ===========================================
# IMPORTAR HANDLERS
# ===========================================
from handlers.start import start, button_handler
from handlers.link import (
    register, confirm_replace_link, cancel_register_callback, 
    confirm_add_link, register_start, process_link_message, cancel_register
)
from handlers.ranking import ranking, ranking_button_handler
from handlers.reputation import earn_reputation, visit_link, more_links
from handlers.referral import referral, process_referral
from handlers.admin import admin_panel, add_reputation_start, add_reputation_get_user, add_reputation_amount, cancel
from handlers.vip import (
    vip_menu, buy_vip, check_payment, check_payment_retry, confirm_payment_command
)

# Estados para conversación
WAITING_USER_ID, WAITING_REPUTATION = range(2)

# ===========================================
# CREAR APP DE TELEGRAM
# ===========================================
telegram_app = Application.builder().token(TOKEN).build()

# ===========================================
# HANDLERS DE COMANDOS
# ===========================================
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("register", register_start))
telegram_app.add_handler(CommandHandler("ranking", ranking))
telegram_app.add_handler(CommandHandler("reputation", earn_reputation))
telegram_app.add_handler(CommandHandler("referral", referral))
telegram_app.add_handler(CommandHandler("vip", vip_menu))
telegram_app.add_handler(CommandHandler("confirmar", confirm_payment_command))
telegram_app.add_handler(CommandHandler("cancelar", cancel_register))

# Handler para referidos (sin comando, desde el enlace)
telegram_app.add_handler(CommandHandler("start", process_referral))

# ===========================================
# HANDLERS DE MENSAJES (MODO CONVERSACIÓN)
# ===========================================
# Este handler procesa los mensajes de texto cuando el bot está esperando un link
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_link_message))

# ===========================================
# HANDLERS DE CALLBACKS
# ===========================================
# Botones principales
telegram_app.add_handler(CallbackQueryHandler(button_handler, pattern="^(register_link|show_ranking|earn_reputation|referral|vip_menu|admin_panel|back_to_start|my_link|change_link|renew_link|add_link_vip)$"))

# Ranking
telegram_app.add_handler(CallbackQueryHandler(ranking_button_handler, pattern="^(refresh_ranking|back_to_start)$"))

# Reputación
telegram_app.add_handler(CallbackQueryHandler(visit_link, pattern="^visit_link_"))
telegram_app.add_handler(CallbackQueryHandler(more_links, pattern="^more_links$"))

# Links
telegram_app.add_handler(CallbackQueryHandler(confirm_replace_link, pattern="^confirm_replace$"))
telegram_app.add_handler(CallbackQueryHandler(confirm_add_link, pattern="^confirm_add_link$"))
telegram_app.add_handler(CallbackQueryHandler(cancel_register_callback, pattern="^cancel_register$"))

# VIP
telegram_app.add_handler(CallbackQueryHandler(vip_menu, pattern="^vip_menu$"))
telegram_app.add_handler(CallbackQueryHandler(buy_vip, pattern="^buy_vip_"))
telegram_app.add_handler(CallbackQueryHandler(check_payment, pattern="^check_payment$"))
telegram_app.add_handler(CallbackQueryHandler(check_payment_retry, pattern="^check_payment_retry$"))

# ===========================================
# CONVERSATION HANDLERS PARA ADMIN
# ===========================================
admin_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_reputation_start, pattern="^admin_add_reputation$")],
    states={
        WAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_reputation_get_user)],
        WAITING_REPUTATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_reputation_amount)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
telegram_app.add_handler(admin_conv)

# ===========================================
# WEBHOOK Y SERVIDOR
# ===========================================
async def setup_webhook():
    await telegram_app.initialize()
    webhook_url = f"{WEBHOOK_URL}/webhook/{TOKEN}"
    await telegram_app.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    logger.info(f"✅ Webhook configurado en {webhook_url}")

# ===========================================
# FUNCIONES PARA NOTIFICACIONES
# ===========================================
async def check_expiring_links():
    """Revisa links que expiran pronto y envía notificaciones"""
    try:
        from database.database import get_expiring_links, get_user

        # Horas antes de expirar para notificar
        checkpoints = [48, 24, 15, 10, 5, 2, 1]

        for hours in checkpoints:
            expiring_links = get_expiring_links(hours)

            for link in expiring_links:
                user_id = link["user_id"]
                user = get_user(user_id)

                if not user:
                    continue

                # Mensaje según horas restantes
                if hours == 48:
                    message = (
                        f"⏰ **Tu link expira en 48 horas.**\n\n"
                        f"🔗 `{link['url']}`\n\n"
                        f"Actualiza a VIP para extender la promoción a 30 días sin perder reputación.\n\n"
                        f"👉 /vip"
                    )
                elif hours <= 24:
                    message = (
                        f"⚠️ **¡Tu link expira en {hours} horas!**\n\n"
                        f"🔗 `{link['url']}`\n\n"
                        f"Renueva con VIP para mantener tu reputación y extender la promoción.\n\n"
                        f"👉 /vip"
                    )
                else:
                    message = (
                        f"🔔 **Recordatorio:** Tu link expira en {hours} horas.\n\n"
                        f"🔗 `{link['url']}`\n\n"
                        f"¡Asegura tu reputación con VIP!"
                    )

                try:
                    await telegram_app.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode='Markdown'
                    )
                    logger.info(f"✅ Notificación enviada a {user_id}: expira en {hours}h")
                except Exception as e:
                    logger.error(f"❌ Error enviando notificación a {user_id}: {e}")

    except Exception as e:
        logger.error(f"❌ Error en check_expiring_links: {e}")

# ===========================================
# FUNCIONES PARA PAGOS AUTOMÁTICOS
# ===========================================
async def check_pending_payments():
    """Revisa pagos pendientes y verifica si fueron completados"""
    try:
        from database.database import get_pending_payments
        pending_payments = get_pending_payments()
        results = []

        for payment in pending_payments:
            tx_hash = payment["tx_hash"]
            # Por ahora, la verificación automática requiere integración con TronGrid
            # Para el MVP, se confirma manualmente por admin
            # En producción, aquí iría la llamada a TronGrid API
            pass

        return results
    except Exception as e:
        logger.error(f"❌ Error en check_pending_payments: {e}")
        return []

# ===========================================
# ENDPOINTS DE API
# ===========================================
app = FastAPI()

@app.post(f"/webhook/{TOKEN}")
async def webhook(request: Request):
    try:
        data = await request.json()
        logger.info(f"📨 Webhook: {data.get('message', {}).get('text', 'sin texto')}")
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.process_update(update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return Response(status_code=500)

@app.get("/")
@app.get("/healthcheck")
async def health():
    return {"status": "ok", "service": "LinkForge"}

@app.get("/check_expiring")
async def trigger_expiring_check():
    """Endpoint para que cron-job.org active las notificaciones de expiración"""
    try:
        await check_expiring_links()
        return {"status": "ok", "message": "Notificaciones de expiración procesadas"}
    except Exception as e:
        logger.error(f"❌ Error en /check_expiring: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/check_payments")
async def trigger_payment_check():
    """Endpoint para que cron-job.org verifique pagos pendientes"""
    try:
        results = await check_pending_payments()
        return {"status": "ok", "message": f"Pagos verificados: {len(results)}", "results": results}
    except Exception as e:
        logger.error(f"❌ Error en /check_payments: {e}")
        return {"status": "error", "message": str(e)}

# ===========================================
# INICIO Y APAGADO
# ===========================================
@app.on_event("startup")
async def on_startup():
    await setup_webhook()
    logger.info("🚀 LinkForge iniciado correctamente")

@app.on_event("shutdown")
async def on_shutdown():
    await telegram_app.bot.delete_webhook()
    await telegram_app.shutdown()
    logger.info("🛑 LinkForge apagado")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)

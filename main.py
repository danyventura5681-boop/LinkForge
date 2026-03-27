import os
import logging
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler
import uvicorn

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
from handlers.link import register, confirm_replace_link, cancel_register
from handlers.ranking import ranking, ranking_button_handler
from handlers.reputation import earn_reputation, visit_link, more_links
from handlers.referral import referral, process_referral
from handlers.admin import admin_panel, add_reputation_start, add_reputation_get_user, add_reputation_amount, cancel
from handlers.vip import vip_menu, buy_vip

# Estados para conversación
WAITING_USER_ID, WAITING_REPUTATION = range(2)

# ===========================================
# CREAR APP DE TELEGRAM
# ===========================================
telegram_app = Application.builder().token(TOKEN).build()

# Handlers de comandos
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("register", register))
telegram_app.add_handler(CommandHandler("ranking", ranking))
telegram_app.add_handler(CommandHandler("reputation", earn_reputation))
telegram_app.add_handler(CommandHandler("referral", referral))
telegram_app.add_handler(CommandHandler("vip", vip_menu))

# Handler para referidos (sin comando, desde el enlace)
telegram_app.add_handler(CommandHandler("start", process_referral))

# Handlers de callbacks
telegram_app.add_handler(CallbackQueryHandler(button_handler, pattern="^(register_link|show_ranking|earn_reputation|referral|vip_menu|admin_panel|back_to_start)$"))
telegram_app.add_handler(CallbackQueryHandler(ranking_button_handler, pattern="^(refresh_ranking|back_to_start)$"))
telegram_app.add_handler(CallbackQueryHandler(visit_link, pattern="^visit_link_"))
telegram_app.add_handler(CallbackQueryHandler(more_links, pattern="^more_links$"))
telegram_app.add_handler(CallbackQueryHandler(confirm_replace_link, pattern="^confirm_replace$"))
telegram_app.add_handler(CallbackQueryHandler(cancel_register, pattern="^cancel_register$"))
telegram_app.add_handler(CallbackQueryHandler(vip_menu, pattern="^vip_menu$"))
telegram_app.add_handler(CallbackQueryHandler(buy_vip, pattern="^buy_vip_"))

# Conversation handlers para admin
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

@app.on_event("startup")
async def on_startup():
    await setup_webhook()

@app.on_event("shutdown")
async def on_shutdown():
    await telegram_app.bot.delete_webhook()
    await telegram_app.shutdown()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)

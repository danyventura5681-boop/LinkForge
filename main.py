import os
import logging
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
import uvicorn

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
from handlers.start import start, button_handler, back_to_start

# ===========================================
# CREAR APP DE TELEGRAM
# ===========================================
telegram_app = Application.builder().token(TOKEN).build()

# Handlers
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(button_handler, pattern="^(register_link|show_ranking|earn_reputation|referral|vip_info|admin_panel)$"))
telegram_app.add_handler(CallbackQueryHandler(back_to_start, pattern="^volver_menu$"))

# ===========================================
# WEBHOOK
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
    logger.info("🚀 LinkForge iniciado correctamente")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)

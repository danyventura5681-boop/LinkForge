import os
import logging
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
import uvicorn

# Configuración
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN no configurado")

PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", f"https://localhost:{PORT}")

# Importar handlers
from handlers.start import start, button_handler

# ===========================================
# CREAR APP DE TELEGRAM
# ===========================================
telegram_app = Application.builder().token(TOKEN).build()

# Registrar handlers
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(button_handler))

# ===========================================
# CONFIGURAR WEBHOOK
# ===========================================
async def setup_webhook():
    await telegram_app.initialize()
    webhook_url = f"{WEBHOOK_URL}/webhook/{TOKEN}"
    await telegram_app.bot.set_webhook(
        url=webhook_url,
        drop_pending_updates=True
    )
    logger.info(f"✅ Webhook configurado en {webhook_url}")

# ===========================================
# APP FASTAPI PARA RENDER
# ===========================================
app = FastAPI()

@app.post(f"/webhook/{TOKEN}")
async def webhook(request: Request):
    """Recibe actualizaciones de Telegram"""
    try:
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)
        await telegram_app.update_queue.put(update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Error en webhook: {e}")
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

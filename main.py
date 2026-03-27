import os
import logging
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
import uvicorn
from dotenv import load_dotenv

# ===========================================
# CARGAR VARIABLES DE ENTORNO
# ===========================================
load_dotenv()

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Leer token desde variables de entorno
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    logger.error("❌ BOT_TOKEN no configurado en variables de entorno")
    raise ValueError("BOT_TOKEN no configurado")

logger.info(f"✅ Token cargado correctamente (primeros 10 chars: {TOKEN[:10]}...)")

PORT = int(os.environ.get("PORT", 8080))

# ===========================================
# CONSTRUIR WEBHOOK_URL DE FORMA ROBUSTA
# ===========================================
# En Render, el dominio es: https://<nombre-servicio>.onrender.com
# Si no está disponible, intentamos con localhost para pruebas
RENDER_SERVICE_NAME = os.environ.get("RENDER_SERVICE_NAME", "linkforge-17kt")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

if RENDER_EXTERNAL_URL:
    WEBHOOK_URL = RENDER_EXTERNAL_URL
else:
    # Construir manualmente (funciona en Render)
    WEBHOOK_URL = f"https://{RENDER_SERVICE_NAME}.onrender.com"

logger.info(f"📡 Webhook base URL: {WEBHOOK_URL}")

# Importar handlers
from handlers.start import start, button_handler

# ===========================================
# CREAR APP DE TELEGRAM
# ===========================================
telegram_app = Application.builder().token(TOKEN).build()

# Registrar handlers
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CallbackQueryHandler(button_handler))

logger.info("✅ Handlers registrados")

# ===========================================
# CONFIGURAR WEBHOOK
# ===========================================
async def setup_webhook():
    await telegram_app.initialize()
    webhook_url = f"{WEBHOOK_URL}/webhook/{TOKEN}"
    logger.info(f"🔧 Configurando webhook en: {webhook_url}")
    
    result = await telegram_app.bot.set_webhook(
        url=webhook_url,
        drop_pending_updates=True
    )
    if result:
        logger.info(f"✅ Webhook configurado en {webhook_url}")
    else:
        logger.error(f"❌ Falló configuración de webhook en {webhook_url}")

# ===========================================
# APP FASTAPI PARA RENDER
# ===========================================
app = FastAPI()

@app.post(f"/webhook/{TOKEN}")
async def webhook(request: Request):
    """Recibe actualizaciones de Telegram y las procesa"""
    try:
        data = await request.json()
        message_text = data.get('message', {}).get('text', 'sin texto')
        logger.info(f"📨 Webhook recibido: {message_text}")

        update = Update.de_json(data, telegram_app.bot)

        # Procesar el update de forma asíncrona
        await telegram_app.process_update(update)

        return Response(status_code=200)
    except Exception as e:
        logger.error(f"❌ Error en webhook: {e}")
        return Response(status_code=500)

@app.get("/")
@app.get("/healthcheck")
async def health():
    return {"status": "ok", "service": "LinkForge", "webhook_url": f"{WEBHOOK_URL}/webhook/{TOKEN[:5]}..."}

@app.on_event("startup")
async def on_startup():
    logger.info("🚀 Iniciando servidor...")
    await setup_webhook()

@app.on_event("shutdown")
async def on_shutdown():
    logger.info("🛑 Apagando servidor...")
    await telegram_app.bot.delete_webhook()
    await telegram_app.shutdown()

if __name__ == "__main__":
    logger.info(f"🚀 Iniciando servidor en puerto {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)

import logging
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_user, register_link, get_user_links

logger = logging.getLogger(__name__)

# Expresión regular para validar URLs
URL_PATTERN = re.compile(
    r'^https?://'
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
    r'localhost|'
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
    r'(?::\d+)?'
    r'(?:/?|[/?]\S+)$', re.IGNORECASE)

def is_valid_url(url: str) -> bool:
    return re.match(URL_PATTERN, url) is not None

def get_promotion_days(user):
    if user and user.get("vip_level", 0) > 0:
        return 30
    return 10

def format_expiration_date(expires_at):
    if not expires_at:
        return "No disponible"
    try:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        now = datetime.utcnow()
        remaining = expires_at - now
        days = remaining.days
        hours = remaining.seconds // 3600
        if days > 0:
            return f"{days} días, {hours} horas"
        else:
            return f"{hours} horas"
    except Exception:
        return "No disponible"

# ===========================================
# REGISTRO CONVERSACIONAL
# ===========================================

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de registro de link (modo conversación)."""
    logger.info("🔵🔵🔵 register_start EJECUTADO 🔵🔵🔵")
    
    text = (
        "📝 **Envíame el link que quieres promocionar**\n\n"
        "Ejemplo: `https://tusitio.com`\n\n"
        "Recuerda incluir `http://` o `https://`"
    )

    keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]]

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    context.user_data['waiting_for_link'] = True
    logger.info("🔵 register_start: waiting_for_link = True")

async def process_link_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el link enviado por el usuario en modo conversación."""
    logger.info("🔵🔵🔵🔵 process_link_message EJECUTADO 🔵🔵🔵🔵")
    logger.info(f"📨 Mensaje recibido: {update.message.text}")
    logger.info(f"📨 waiting_for_link = {context.user_data.get('waiting_for_link')}")
    
    if not context.user_data.get('waiting_for_link'):
        logger.info("⚠️ waiting_for_link = False, ignorando mensaje")
        return

    user = update.effective_user
    telegram_id = user.id
    url = update.message.text.strip()
    logger.info(f"🔵 Procesando link: {url}")

    keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]]

    # Validar URL
    if not is_valid_url(url):
        logger.info(f"❌ URL no válida: {url}")
        await update.message.reply_text(
            "❌ **URL no válida.**\n\n"
            "Asegúrate de incluir `http://` o `https://`.\n"
            "Ejemplo: `https://tusitio.com`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return

    # Obtener usuario para verificar nivel VIP
    db_user = get_user(telegram_id)
    days = get_promotion_days(db_user)
    vip_level = db_user.get("vip_level", 0) if db_user else 0
    logger.info(f"🔵 Usuario VIP nivel: {vip_level}, días de promoción: {days}")

    # Verificar si el usuario ya tiene links activos
    existing_links = get_user_links(telegram_id)
    max_links = 3 if vip_level > 0 else 1
    logger.info(f"🔵 Links activos: {len(existing_links)}/{max_links}")

    if existing_links and len(existing_links) >= max_links:
        logger.info(f"⚠️ Límite de links alcanzado: {len(existing_links)}/{max_links}")
        await update.message.reply_text(
            f"⚠️ **Límite de links alcanzado.**\n\n"
            f"📌 Links activos: {len(existing_links)}/{max_links}\n\n"
            f"Para tener más links, actualiza a VIP con el botón de abajo.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ VIP", callback_data="vip_info")],
                [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
            ]),
            parse_mode='Markdown'
        )
        context.user_data['waiting_for_link'] = False
        return

    # Registrar nuevo link
    register_link(telegram_id, url, link_number=1, days=days)
    logger.info(f"✅ Link registrado: {url}")

    # Calcular fecha de expiración
    expires_at = datetime.utcnow() + timedelta(days=days)
    expires_formatted = format_expiration_date(expires_at)
    vip_text = " (VIP: 30 días)" if vip_level > 0 else ""

    await update.message.reply_text(
        f"✅ **¡Link registrado con éxito!**\n\n"
        f"🔗 Tu link: `{url}`\n"
        f"⏳ Promoción activa por **{days} días**{vip_text}\n"
        f"📅 Expira: {expires_at.strftime('%d/%m/%Y %H:%M')} UTC\n"
        f"⏰ Tiempo restante: {expires_formatted}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Ir al Panel Principal", callback_data="volver_menu")]]),
        parse_mode='Markdown'
    )

    context.user_data['waiting_for_link'] = False
    logger.info("🔵 waiting_for_link desactivado")

# ===========================================
# FUNCIONES DE COMPATIBILIDAD
# ===========================================

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Punto de entrada para /register - redirige al modo conversacional."""
    await register_start(update, context)

async def confirm_replace_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma el reemplazo del link actual."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✏️ Función de reemplazo en desarrollo.\n\nPronto disponible.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
    )

async def confirm_add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma agregar un nuevo link (para usuarios VIP)."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "➕ Función de agregar link en desarrollo.\n\nPronto disponible.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
    )

async def cancel_register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela el registro desde callback (botón)."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop('pending_url', None)
    context.user_data.pop('waiting_for_link', None)
    await query.edit_message_text(
        "❌ Registro de link cancelado.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
    )
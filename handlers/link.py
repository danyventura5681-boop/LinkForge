import logging
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_user, register_link, get_user_links

logger = logging.getLogger(__name__)

# Expresión regular para validar URLs
URL_PATTERN = re.compile(
    r'^https?://'  # http:// o https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # dominio...
    r'localhost|'  # localhost...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...o ip
    r'(?::\d+)?'  # puerto opcional
    r'(?:/?|[/?]\S+)$', re.IGNORECASE)

def is_valid_url(url: str) -> bool:
    """Verifica si una URL es válida."""
    return re.match(URL_PATTERN, url) is not None

def get_promotion_days(user):
    """Determina los días de promoción según el nivel VIP del usuario"""
    if user and user.get("vip_level", 0) > 0:
        return 30  # VIP: 30 días
    return 10  # Usuario normal: 10 días

def format_expiration_date(expires_at):
    """Formatea la fecha de expiración para mostrar"""
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
    # Si viene de un callback (botón)
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "📝 **Envíame el link que quieres promocionar**\n\n"
            "Ejemplo: `https://tusitio.com`\n\n"
            "Recuerda incluir `http://` o `https://`\n\n"
            "❌ Para cancelar, escribe /cancelar",
            parse_mode='Markdown'
        )
    else:
        # Si viene de comando /register
        await update.message.reply_text(
            "📝 **Envíame el link que quieres promocionar**\n\n"
            "Ejemplo: `https://tusitio.com`\n\n"
            "Recuerda incluir `http://` o `https://`\n\n"
            "❌ Para cancelar, escribe /cancelar",
            parse_mode='Markdown'
        )
    
    # Activar estado de espera
    context.user_data['waiting_for_link'] = True

async def process_link_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el link enviado por el usuario en modo conversación."""
    # Verificar si estamos esperando un link
    if not context.user_data.get('waiting_for_link'):
        return
    
    user = update.effective_user
    telegram_id = user.id
    username = user.username or user.first_name or "Usuario"
    
    url = update.message.text.strip()
    
    # Validar URL
    if not is_valid_url(url):
        await update.message.reply_text(
            "❌ **URL no válida.**\n\n"
            "Asegúrate de incluir `http://` o `https://`.\n"
            "Ejemplo: `https://tusitio.com`\n\n"
            "Intenta de nuevo o escribe /cancelar para cancelar.",
            parse_mode='Markdown'
        )
        return
    
    # Obtener usuario para verificar nivel VIP
    db_user = get_user(telegram_id)
    days = get_promotion_days(db_user)
    vip_level = db_user.get("vip_level", 0) if db_user else 0
    
    # Verificar si el usuario ya tiene links activos
    existing_links = get_user_links(telegram_id)
    max_links = 3 if vip_level > 0 else 1
    
    if existing_links and len(existing_links) >= max_links:
        await update.message.reply_text(
            f"⚠️ **Límite de links alcanzado.**\n\n"
            f"📌 Links activos: {len(existing_links)}/{max_links}\n\n"
            f"Para tener más links, actualiza a VIP con /vip.\n"
            f"Para reemplazar tu link actual, usa /replace (próximamente).",
            parse_mode='Markdown'
        )
        context.user_data['waiting_for_link'] = False
        return
    
    # Registrar nuevo link
    register_link(telegram_id, url, link_number=1, days=days)
    
    # Calcular fecha de expiración
    expires_at = datetime.utcnow() + timedelta(days=days)
    expires_formatted = format_expiration_date(expires_at)
    vip_text = " (VIP: 30 días)" if vip_level > 0 else ""
    
    await update.message.reply_text(
        f"✅ **¡Link registrado con éxito!**\n\n"
        f"🔗 Tu link: `{url}`\n"
        f"⏳ Promoción activa por **{days} días**{vip_text}\n"
        f"📅 Expira: {expires_at.strftime('%d/%m/%Y %H:%M')} UTC\n"
        f"⏰ Tiempo restante: {expires_formatted}\n\n"
        f"📊 Usa /ranking para ver tu posición.\n"
        f"🎁 Invita amigos con /referral para ganar reputación.",
        parse_mode='Markdown'
    )
    
    # Limpiar estado de espera
    context.user_data['waiting_for_link'] = False
    
    # Volver al panel principal
    from handlers.start import start
    await start(update, context)

async def cancel_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela el registro de link."""
    if context.user_data.get('waiting_for_link'):
        context.user_data['waiting_for_link'] = False
        await update.message.reply_text("❌ Registro de link cancelado.")
        
        # Volver al panel principal
        from handlers.start import start
        await start(update, context)
    else:
        await update.message.reply_text("No hay ninguna operación pendiente de cancelar.")

# ===========================================
# FUNCIONES DE COMPATIBILIDAD (mantienen el código existente)
# ===========================================

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Punto de entrada para /register - redirige al modo conversacional."""
    await register_start(update, context)

async def confirm_replace_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma el reemplazo del link actual."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    new_url = context.user_data.get('pending_url')

    if not new_url:
        await query.edit_message_text("❌ Operación cancelada. No hay link pendiente.")
        return

    # Obtener usuario para determinar días
    db_user = get_user(user_id)
    days = get_promotion_days(db_user)

    # Eliminar link anterior y registrar nuevo
    from database.database import delete_links, register_link
    delete_links(user_id)
    register_link(user_id, new_url, link_number=1, days=days)

    expires_at = datetime.utcnow() + timedelta(days=days)
    vip_text = " (VIP: 30 días)" if days == 30 else ""

    await query.edit_message_text(
        f"✅ **Link reemplazado con éxito!**\n\n"
        f"🔗 Nuevo link: `{new_url}`\n"
        f"⏳ Promoción activa por **{days} días**{vip_text}\n"
        f"📅 Expira: {expires_at.strftime('%d/%m/%Y %H:%M')} UTC\n\n"
        f"⚠️ Tu reputación se mantiene.",
        parse_mode='Markdown'
    )
    context.user_data.pop('pending_url', None)

async def confirm_add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma agregar un nuevo link (para usuarios VIP)."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    new_url = context.user_data.get('pending_url')

    if not new_url:
        await query.edit_message_text("❌ Operación cancelada. No hay link pendiente.")
        return

    # Obtener usuario para determinar días y número de link
    db_user = get_user(user_id)
    days = get_promotion_days(db_user)
    existing_links = get_user_links(user_id)
    next_link_number = len(existing_links) + 1

    # Registrar nuevo link
    from database.database import register_link
    register_link(user_id, new_url, link_number=next_link_number, days=days)

    expires_at = datetime.utcnow() + timedelta(days=days)

    await query.edit_message_text(
        f"✅ **¡Nuevo link agregado con éxito!**\n\n"
        f"🔗 Link #{next_link_number}: `{new_url}`\n"
        f"⏳ Promoción activa por **{days} días** (VIP)\n"
        f"📅 Expira: {expires_at.strftime('%d/%m/%Y %H:%M')} UTC\n\n"
        f"📊 Usa /ranking para ver tu posición.",
        parse_mode='Markdown'
    )
    context.user_data.pop('pending_url', None)

async def cancel_register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela el registro desde callback (botón)."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop('pending_url', None)
    context.user_data.pop('waiting_for_link', None)
    await query.edit_message_text("❌ Registro de link cancelado.")
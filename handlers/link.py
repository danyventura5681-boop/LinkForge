import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_user, register_link, get_user_links

logger = logging.getLogger(__name__)

# Expresión regular para validar URLs (simplificada pero efectiva)
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

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registra un link para el usuario."""
    user = update.effective_user
    telegram_id = user.id
    username = user.username or user.first_name or "Usuario"
    
    # Verificar que se proporcionó una URL
    if not context.args:
        await update.message.reply_text(
            "🔗 **Uso correcto:** `/register [URL]`\n\n"
            "Ejemplo: `/register https://tusitio.com`",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0]
    
    # Validar URL
    if not is_valid_url(url):
        await update.message.reply_text(
            "❌ **URL no válida.**\n\n"
            "Asegúrate de incluir `http://` o `https://`.\n"
            "Ejemplo: `https://tusitio.com`",
            parse_mode='Markdown'
        )
        return
    
    # Verificar si el usuario ya tiene links activos
    existing_links = get_user_links(telegram_id)
    
    if existing_links and len(existing_links) >= 1:
        # Por ahora solo 1 link (sin VIP)
        keyboard = [
            [InlineKeyboardButton("💎 Actualizar a VIP", callback_data="vip_info")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_register")]
        ]
        await update.message.reply_text(
            f"⚠️ **Ya tienes un link activo.**\n\n"
            f"📌 Link actual: `{existing_links[0]['url']}`\n\n"
            f"Con VIP puedes tener hasta 3 links simultáneos.\n\n"
            f"¿Quieres reemplazar tu link actual?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        # Guardar la nueva URL en contexto para confirmación
        context.user_data['pending_url'] = url
        return
    
    # Registrar nuevo link (10 días de promoción)
    register_link(telegram_id, url, link_number=1, days=10)
    
    await update.message.reply_text(
        f"✅ **¡Link registrado con éxito!**\n\n"
        f"🔗 Tu link: `{url}`\n"
        f"⏳ Promoción activa por **10 días**\n\n"
        f"📊 Usa /ranking para ver tu posición.\n"
        f"🎁 Invita amigos con /referral para ganar reputación.",
        parse_mode='Markdown'
    )
    logger.info(f"✅ Link registrado para {username}: {url}")

async def confirm_replace_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma el reemplazo del link actual."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    new_url = context.user_data.get('pending_url')
    
    if not new_url:
        await query.edit_message_text("❌ Operación cancelada. No hay link pendiente.")
        return
    
    # Eliminar link anterior y registrar nuevo
    from database.database import delete_links, register_link
    delete_links(user_id)
    register_link(user_id, new_url, link_number=1, days=10)
    
    await query.edit_message_text(
        f"✅ **Link reemplazado con éxito!**\n\n"
        f"🔗 Nuevo link: `{new_url}`\n"
        f"⏳ Promoción activa por **10 días**\n\n"
        f"⚠️ Tu reputación anterior se mantiene.",
        parse_mode='Markdown'
    )
    context.user_data.pop('pending_url', None)

async def cancel_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela el registro de link."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop('pending_url', None)
    await query.edit_message_text("❌ Registro de link cancelado.")
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import get_user, register_link, get_user_links, update_link

logger = logging.getLogger(__name__)

# Expresión regular para validar URLs
URL_PATTERN = re.compile(
    r'^https?://'
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
    r'localhost|'
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
    r'(?::\d+)?'
    r'(?:/?|[/?]\S+)$', re.IGNORECASE)

# Constante para ConversationHandler
WAITING_NEW_LINK = 1

def is_valid_url(url: str) -> bool:
    return re.match(URL_PATTERN, url) is not None

def get_promotion_days(user):
    """Determina los días de promoción según el nivel VIP del usuario"""
    if user and user.vip_level > 0:
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
# REGISTRO Y GESTIÓN DE LINKS
# ===========================================

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de registro de link."""
    logger.info("🔵 register_start EJECUTADO")

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
    """Procesa el link enviado por el usuario."""
    logger.info("🔵 process_link_message EJECUTADO")

    if not context.user_data.get('waiting_for_link'):
        logger.info("⚠️ waiting_for_link = False, ignorando mensaje")
        return

    user = update.effective_user
    telegram_id = user.id
    url = update.message.text.strip()
    logger.info(f"🔵 Procesando link: {url}")

    keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]]

    # Borrar el mensaje del usuario
    try:
        await update.message.delete()
        logger.info(f"✅ Mensaje del usuario {telegram_id} borrado")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo borrar mensaje: {e}")

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

    # Obtener usuario
    db_user = get_user(telegram_id)
    vip_level = db_user.vip_level if db_user and db_user.vip_level else 0
    days = 30 if vip_level > 0 else 10

    logger.info(f"🔵 Usuario VIP nivel: {vip_level}, días: {days}")

    # Verificar límite de links
    existing_links = get_user_links(telegram_id)
    max_links = 3 if vip_level > 0 else 1

    if existing_links and len(existing_links) >= max_links:
        logger.info(f"⚠️ Límite alcanzado: {len(existing_links)}/{max_links}")
        await update.message.reply_text(
            f"⚠️ **Límite de links alcanzado.**\n\n"
            f"📌 Links activos: {len(existing_links)}/{max_links}\n\n"
            f"**Opciones:**\n"
            f"1️⃣ Cambiar un link existente\n"
            f"2️⃣ Actualizar a VIP para más links",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Ver mis links", callback_data="manage_links")],
                [InlineKeyboardButton("⭐ VIP", callback_data="vip_info")],
                [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
            ]),
            parse_mode='Markdown'
        )
        context.user_data['waiting_for_link'] = False
        return

    # Registrar link
    register_link(telegram_id, url, link_number=1, days=days)
    logger.info(f"✅ Link registrado: {url}")

    expires_at = datetime.utcnow() + timedelta(days=days)
    expires_formatted = format_expiration_date(expires_at)

    await update.message.reply_text(
        f"✅ **¡Link registrado con éxito!**\n\n"
        f"🔗 Tu link: `{url}`\n"
        f"⏳ Promoción activa por **{days} días**\n"
        f"📅 Expira: {expires_at.strftime('%d/%m/%Y %H:%M')} UTC\n"
        f"⏰ Tiempo restante: {expires_formatted}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Ir al Panel", callback_data="volver_menu")]]),
        parse_mode='Markdown'
    )

    context.user_data['waiting_for_link'] = False

# ===========================================
# GESTIÓN DE LINKS (NUEVO)
# ===========================================

async def manage_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menú para gestionar links del usuario."""
    user_id = update.effective_user.id
    user = get_user(user_id)

    logger.info(f"📌 manage_links: Usuario {user_id} accedió a gestionar links")

    links = get_user_links(user_id)
    vip_level = user.vip_level if user else 0

    if not links:
        text = (
            "📌 **Mis Links**\n\n"
            "❌ No tienes links registrados.\n\n"
            "🔗 Registra tu primer link para comenzar."
        )
        keyboard = [
            [InlineKeyboardButton("🔗 Registrar Link", callback_data="register_link")],
            [InlineKeyboardButton("◀️ Volver", callback_data="volver_menu")]
        ]
    else:
        text = "📌 **Mis Links**\n\n"
        for i, link in enumerate(links, 1):
            expires_in = format_expiration_date(link.expires_at)
            text += f"{i}. `{link.url}`\n⏱️ {expires_in} | 👁️ {link.clicks_received} clicks\n\n"

        keyboard = []
        for i, link in enumerate(links, 1):
            keyboard.append([InlineKeyboardButton(
                f"✏️ Cambiar Link {i}",
                callback_data=f"change_link_{link.id}"
            )])

        if vip_level > 0 and len(links) < 3:
            keyboard.append([InlineKeyboardButton("➕ Agregar Link", callback_data="add_link")])

        keyboard.append([InlineKeyboardButton("◀️ Volver", callback_data="volver_menu")])

    if update.callback_query:
        query = update.callback_query
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

async def change_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de cambiar un link para ConversationHandler."""
    query = update.callback_query
    await query.answer()

    link_id = int(query.data.split('_')[2])
    context.user_data['changing_link_id'] = link_id

    logger.info(f"✏️ change_link_start: Cambiando link {link_id}")

    await query.edit_message_text(
        "✏️ **Envía el nuevo link:**\n\n"
        "El tiempo de expiración NO se modificará.\n"
        "Solo la URL será reemplazada.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="manage_links")]])
    )
    
    return WAITING_NEW_LINK

async def process_change_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el cambio de link para ConversationHandler."""
    user_id = update.effective_user.id
    new_url = update.message.text.strip()
    link_id = context.user_data.get('changing_link_id')

    logger.info(f"✏️ process_change_link: Cambiando link {link_id} a: {new_url}")

    # Borrar mensaje
    try:
        await update.message.delete()
    except:
        pass

    # Validar URL
    if not is_valid_url(new_url):
        await update.message.reply_text(
            "❌ **URL no válida.**\n\n"
            "Intenta de nuevo con una URL válida.\n"
            "Ejemplo: `https://tusitio.com`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="manage_links")]]),
            parse_mode='Markdown'
        )
        return WAITING_NEW_LINK

    # Actualizar link
    update_link(link_id, new_url)
    logger.info(f"✅ Link {link_id} actualizado")

    await update.message.reply_text(
        f"✅ **¡Link actualizado!**\n\n"
        f"🔗 Nuevo URL: `{new_url}`\n\n"
        f"⏳ La fecha de expiración se mantiene igual.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📌 Ver mis links", callback_data="manage_links")]]),
        parse_mode='Markdown'
    )

    # Limpiar datos
    context.user_data.pop('changing_link_id', None)
    
    return ConversationHandler.END

# ===========================================
# COMPATIBILIDAD
# ===========================================

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Punto de entrada para /register."""
    await register_start(update, context)

async def confirm_replace_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma el reemplazo del link."""
    query = update.callback_query
    await query.answer()
    await manage_links(update, context)

async def confirm_add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma agregar un nuevo link."""
    query = update.callback_query
    await query.answer()
    await register_start(update, context)

async def cancel_register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela el registro."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop('waiting_for_link', None)
    context.user_data.pop('waiting_for_link_change', None)
    context.user_data.pop('changing_link_id', None)
    await query.edit_message_text(
        "❌ Operación cancelada.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
    )
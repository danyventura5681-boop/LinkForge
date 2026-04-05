import logging
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import get_user, register_link, get_user_links, update_link, delete_link, get_link_by_id

logger = logging.getLogger(__name__)

# Expresión regular para validar URLs
URL_PATTERN = re.compile(
    r'^https?://'
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
    r'localhost|'
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
    r'(?::\d+)?'
    r'(?:/?|[/?]\S+)$', re.IGNORECASE)

# Estados para conversación
WAITING_NEW_LINK = 1

def is_valid_url(url: str) -> bool:
    return re.match(URL_PATTERN, url) is not None

def format_time_remaining(expires_at):
    """Calcula los días y horas restantes"""
    if not expires_at:
        return "No activo"
    try:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        now = datetime.utcnow()
        if expires_at <= now:
            return "⚠️ EXPIRADO"
        remaining = expires_at - now
        days = remaining.days
        hours = remaining.seconds // 3600
        if days > 0:
            return f"{days} días, {hours} horas"
        else:
            return f"{hours} horas"
    except Exception:
        return "No disponible"

def get_promotion_days(user):
    if user and user.vip_level > 0:
        return 30
    return 10

# ============================================
# GESTIÓN DE LINKS (MENÚ PRINCIPAL)
# ============================================

async def manage_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menú para gestionar links del usuario."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    logger.info(f"📌 manage_links: Usuario {user_id} accedió a gestionar links")
    
    links = get_user_links(user_id)
    vip_level = user.vip_level if user else 0
    max_links = 3 if vip_level >= 3 else 1
    
    if not links:
        text = (
            "📌 **MIS LINKS**\n\n"
            "❌ No tienes links registrados.\n\n"
            "🔗 Registra tu primer link para comenzar a promocionarlo.\n\n"
            f"💡 Como VIP nivel {vip_level}, puedes tener hasta {max_links} link(s)."
        )
        keyboard = [
            [InlineKeyboardButton("➕ AGREGAR LINK", callback_data="add_new_link")],
            [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
        ]
    else:
        text = f"📌 **MIS LINKS**\n\n📊 Total: {len(links)}/{max_links} links\n\n"
        
        keyboard = []
        for i, link in enumerate(links, 1):
            time_left = format_time_remaining(link.expires_at)
            text += f"**{i}. Link**\n"
            text += f"🔗 `{link.url}`\n"
            text += f"👁️ Visitas: {link.clicks_received} | ⏳ {time_left}\n\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"✏️ Cambiar Link {i}",
                    callback_data=f"change_link_{link.id}"
                ),
                InlineKeyboardButton(
                    f"🗑️ Eliminar Link {i}",
                    callback_data=f"delete_link_{link.id}"
                )
            ])
        
        # Botón para agregar nuevo link (solo si no alcanzó el límite)
        if len(links) < max_links:
            keyboard.append([InlineKeyboardButton("➕ AGREGAR LINK", callback_data="add_new_link")])
        
        keyboard.append([InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")])
    
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

# ============================================
# AGREGAR LINK (NUEVO)
# ============================================

async def add_new_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso para agregar un nuevo link."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    links = get_user_links(user_id)
    max_links = 3 if user.vip_level >= 3 else 1
    
    if len(links) >= max_links:
        await query.edit_message_text(
            f"⚠️ **Límite de links alcanzado**\n\n"
            f"📊 Tienes {len(links)}/{max_links} links.\n\n"
            f"💡 Actualiza a VIP 3 para tener hasta 3 links.\n\n"
            f"🔄 Puedes cambiar o eliminar un link existente.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Ver mis links", callback_data="manage_links")],
                [InlineKeyboardButton("⭐ VIP", callback_data="vip_info")],
                [InlineKeyboardButton("◀️ Volver", callback_data="volver_menu")]
            ]),
            parse_mode='Markdown'
        )
        return
    
    text = (
        "📝 **AGREGAR NUEVO LINK**\n\n"
        "📌 **Instrucciones:**\n"
        "1️⃣ Envía el link que quieres promocionar\n"
        "2️⃣ Puede ser de cualquier plataforma\n"
        "3️⃣ El link debe ser público\n\n"
        "🔗 **Ejemplo:** `https://tusitio.com`\n\n"
        "⚠️ Recuerda incluir `http://` o `https://`"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Cancelar", callback_data="manage_links")]]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['waiting_for_new_link'] = True
    return WAITING_NEW_LINK

async def process_new_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el nuevo link enviado por el usuario."""
    if not context.user_data.get('waiting_for_new_link'):
        return
    
    user_id = update.effective_user.id
    user = get_user(user_id)
    url = update.message.text.strip()
    
    logger.info(f"🔗 process_new_link: Usuario {user_id} envió URL: {url}")
    
    # Verificar límite nuevamente
    links = get_user_links(user_id)
    max_links = 3 if user.vip_level >= 3 else 1
    
    if len(links) >= max_links:
        await update.message.reply_text(
            f"⚠️ **Límite de links alcanzado**\n\n"
            f"Tienes {len(links)}/{max_links} links.\n\n"
            f"Elimina o cambia un link existente antes de agregar uno nuevo.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Mis links", callback_data="manage_links")]])
        )
        context.user_data['waiting_for_new_link'] = False
        return
    
    # Validar URL
    if not is_valid_url(url):
        await update.message.reply_text(
            "❌ **URL no válida**\n\n"
            "Asegúrate de incluir `http://` o `https://`.\n"
            "Ejemplo: `https://tusitio.com`\n\n"
            "🔗 Envía un enlace válido o /cancel para cancelar.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="manage_links")]]),
            parse_mode='Markdown'
        )
        return WAITING_NEW_LINK
    
    # Registrar link
    days = 30 if user.vip_level > 0 else 10
    register_link(user_id, url, link_number=len(links) + 1, days=days)
    
    expires_at = datetime.utcnow() + timedelta(days=days)
    
    await update.message.delete()
    await update.message.reply_text(
        f"✅ **¡Link agregado con éxito!**\n\n"
        f"🔗 `{url}`\n"
        f"⏳ Promoción activa por **{days} días**\n"
        f"📅 Expira: {expires_at.strftime('%d/%m/%Y %H:%M')} UTC\n\n"
        f"📊 Los usuarios pueden visitar tu link y ganar reputación.\n"
        f"💡 Comparte tu link para más visitas.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Ver mis links", callback_data="manage_links")],
            [InlineKeyboardButton("🏠 Volver al Menú", callback_data="volver_menu")]
        ]),
        parse_mode='Markdown'
    )
    
    context.user_data['waiting_for_new_link'] = False
    return ConversationHandler.END

# ============================================
# CAMBIAR LINK
# ============================================

async def change_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso para cambiar un link."""
    query = update.callback_query
    await query.answer()
    
    link_id = int(query.data.split('_')[2])
    context.user_data['changing_link_id'] = link_id
    
    logger.info(f"✏️ change_link_start: Cambiando link {link_id}")
    
    text = (
        "✏️ **CAMBIAR LINK**\n\n"
        "📝 Envía el **nuevo enlace**:\n\n"
        "⚠️ El tiempo de expiración NO se modificará.\n"
        "💡 Solo la URL será reemplazada.\n\n"
        "🔗 **Ejemplo:** `https://tunuevositio.com`"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Cancelar", callback_data="manage_links")]]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['waiting_for_link_change'] = True
    return WAITING_NEW_LINK

async def process_change_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el cambio de link."""
    if not context.user_data.get('waiting_for_link_change'):
        return
    
    user_id = update.effective_user.id
    new_url = update.message.text.strip()
    link_id = context.user_data.get('changing_link_id')
    
    logger.info(f"✏️ process_change_link: Usuario {user_id} cambiando link {link_id} a: {new_url}")
    
    # Validar URL
    if not is_valid_url(new_url):
        await update.message.reply_text(
            "❌ **URL no válida**\n\n"
            "Asegúrate de incluir `http://` o `https://`.\n"
            "Ejemplo: `https://tusitio.com`\n\n"
            "🔗 Envía un enlace válido o /cancel para cancelar.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="manage_links")]]),
            parse_mode='Markdown'
        )
        return WAITING_NEW_LINK
    
    # Actualizar link
    update_link(link_id, new_url)
    
    await update.message.delete()
    await update.message.reply_text(
        f"✅ **¡Link actualizado!**\n\n"
        f"🔗 Nuevo URL: `{new_url}`\n\n"
        f"⏳ La fecha de expiración se mantiene igual.\n\n"
        f"📊 Los usuarios seguirán viendo tu link en el ranking.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Ver mis links", callback_data="manage_links")],
            [InlineKeyboardButton("🏠 Volver al Menú", callback_data="volver_menu")]
        ]),
        parse_mode='Markdown'
    )
    
    context.user_data['waiting_for_link_change'] = False
    context.user_data.pop('changing_link_id', None)
    return ConversationHandler.END

# ============================================
# ELIMINAR LINK
# ============================================

async def delete_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elimina un link del usuario."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    link_id = int(query.data.split('_')[2])
    
    from database import get_link_by_id
    
    link = get_link_by_id(link_id)
    
    if not link:
        await query.edit_message_text(
            "❌ Link no encontrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="manage_links")]])
        )
        return
    
    if link.user_id != user_id:
        await query.edit_message_text(
            "❌ No puedes eliminar links de otros usuarios.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="manage_links")]])
        )
        return
    
    from database import delete_link
    
    delete_link(link_id)
    logger.info(f"🗑️ Link {link_id} eliminado por usuario {user_id}")
    
    await query.edit_message_text(
        f"✅ **Link eliminado**\n\n"
        f"🔗 URL: `{link.url}`\n\n"
        f"Tu link ha sido removido del sistema.\n\n"
        f"💡 Puedes agregar un nuevo link si tienes espacios disponibles.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Agregar nuevo link", callback_data="add_new_link")],
            [InlineKeyboardButton("📋 Ver mis links", callback_data="manage_links")],
            [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
        ]),
        parse_mode='Markdown'
    )

# ============================================
# REGISTRO DE LINK (FLUJO ORIGINAL)
# ============================================

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de registro de link (primer link)."""
    logger.info("🔵 register_start EJECUTADO")
    
    user_id = update.effective_user.id
    existing_links = get_user_links(user_id)
    
    if existing_links:
        # Si ya tiene links, redirigir a gestión
        await manage_links(update, context)
        return
    
    text = (
        "📝 **REGISTRAR PRIMER LINK**\n\n"
        "📌 Envíame el link que quieres promocionar\n\n"
        "(Tu Link de referidos de Páginas, Bots, etc., links de grupos en Telegram, WhatsApp, etc.)\n\n"
        "🔗 **Ejemplo:** `https://tusitio.com`\n\n"
        "⚠️ Recuerda incluir `http://` o `https://`"
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
    """Procesa el link enviado por el usuario (primer link)."""
    logger.info("🔵 process_link_message EJECUTADO")
    
    if not context.user_data.get('waiting_for_link'):
        logger.info("⚠️ waiting_for_link = False, ignorando mensaje")
        return
    
    user = update.effective_user
    telegram_id = user.id
    url = update.message.text.strip()
    logger.info(f"🔵 Procesando link: {url}")
    
    keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]]
    
    try:
        await update.message.delete()
        logger.info(f"✅ Mensaje del usuario {telegram_id} borrado")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo borrar mensaje: {e}")
    
    if not is_valid_url(url):
        await update.message.reply_text(
            "❌ **URL no válida.**\n\n"
            "Asegúrate de incluir `http://` o `https://`.\n"
            "Ejemplo: `https://tusitio.com`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    db_user = get_user(telegram_id)
    vip_level = db_user.vip_level if db_user and db_user.vip_level else 0
    days = 30 if vip_level > 0 else 10
    
    existing_links = get_user_links(telegram_id)
    
    if existing_links and len(existing_links) >= 1:
        await update.message.reply_text(
            f"⚠️ **Ya tienes un link registrado**\n\n"
            f"📌 Puedes gestionar tus links desde el menú 'Registrar Link'.\n\n"
            f"💡 Opciones disponibles:\n"
            f"• Cambiar link existente\n"
            f"• Eliminar link\n"
            f"• Agregar nuevo link (VIP)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Gestionar links", callback_data="manage_links")],
                [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
            ]),
            parse_mode='Markdown'
        )
        context.user_data['waiting_for_link'] = False
        return
    
    register_link(telegram_id, url, link_number=1, days=days)
    logger.info(f"✅ Link registrado: {url}")
    
    expires_at = datetime.utcnow() + timedelta(days=days)
    
    await update.message.reply_text(
        f"✅ **¡Link registrado con éxito!**\n\n"
        f"🔗 Tu link: `{url}`\n"
        f"⏳ Promoción activa por **{days} días**\n"
        f"📅 Expira: {expires_at.strftime('%d/%m/%Y %H:%M')} UTC\n\n"
        f"📊 Los usuarios pueden visitar tu link y ganar reputación.\n"
        f"💡 Comparte tu link para más visitas.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Ver mis links", callback_data="manage_links")],
            [InlineKeyboardButton("🏠 Ir al Panel", callback_data="volver_menu")]
        ]),
        parse_mode='Markdown'
    )
    
    context.user_data['waiting_for_link'] = False

# ============================================
# COMPATIBILIDAD
# ============================================

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await register_start(update, context)

async def confirm_replace_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await manage_links(update, context)

async def confirm_add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await add_new_link_start(update, context)

async def cancel_register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop('waiting_for_link', None)
    context.user_data.pop('waiting_for_link_change', None)
    context.user_data.pop('waiting_for_new_link', None)
    await query.edit_message_text(
        "❌ Operación cancelada.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
    )
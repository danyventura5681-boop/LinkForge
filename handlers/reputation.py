import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_top_users, get_user, add_reputation, get_user_links, record_click

logger = logging.getLogger(__name__)

async def earn_reputation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los top 5 links para ganar reputación."""
    user_id = update.effective_user.id
    logger.info(f"🎁 earn_reputation: Usuario {user_id} solicitó ganar reputación")

    # Obtener top 10 usuarios
    top_users = get_top_users(limit=10)

    # NO excluir al administrador de la lista
    # Mostrar los primeros 5 (incluyendo al admin si está en el top)
    available_users = top_users[:5]

    if not available_users:
        text = (
            "🎁 **No hay usuarios disponibles**\n\n"
            "Vuelve más tarde cuando haya más usuarios registrados.\n\n"
            "💡 Consejo: Invita amigos con el botón 'Invitar Amigos' para aumentar la comunidad."
        )
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]]

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
        return

    # ✅ FIX: Guardar solo IDs y links (sin URL completa)
    context.user_data['available_links'] = []
    link_map = {}
    
    text = "🎁 **Gana reputación** 🎁\n\n"
    text += "Haz clic en los links de otros usuarios para ganar **+5 reputación** cada uno.\n\n"
    text += "**Links disponibles:**\n\n"

    keyboard = []
    link_counter = 1
    
    for i, user in enumerate(available_users, 1):
        username = user.username or f"Usuario_{user.telegram_id}"
        text += f"{i}. @{username} - {user.reputation} pts\n"

        # Buscar link del usuario
        user_links = get_user_links(user.telegram_id)
        if user_links:
            link = user_links[0]
            link_url = link.url
            link_id = link.id
            
            # ✅ FIX: Usar ID corto en callback_data
            callback_id = f"link_{link_counter}"
            link_map[callback_id] = {
                'link_id': link_id,
                'user_id': user.telegram_id,
                'url': link_url,
                'username': username
            }
            context.user_data['link_map'] = link_map
            
            keyboard.append([InlineKeyboardButton(
                f"🔗 Visitar @{username} (+5)",
                callback_data=callback_id
            )])
            link_counter += 1

    keyboard.append([InlineKeyboardButton("🔄 Más links", callback_data="more_links")])
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
    logger.info(f"🎁 Mostrados {len(available_users)} usuarios disponibles")

async def visit_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registra la visita a un link y da reputación."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    callback_id = query.data  # Ejemplo: "link_1"
    
    logger.info(f"🔗 visit_link: Usuario {user_id} hizo clic en {callback_id}")

    # ✅ FIX: Obtener datos del mapa guardado
    link_map = context.user_data.get('link_map', {})
    
    if callback_id not in link_map:
        logger.warning(f"❌ Callback ID no encontrado: {callback_id}")
        await query.edit_message_text(
            "❌ Link no encontrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
        )
        return
    
    link_info = link_map[callback_id]
    link_id = link_info['link_id']
    target_user_id = link_info['user_id']
    link_url = link_info['url']
    username = link_info['username']

    # No permitir visitar tu propio link (ni siquiera al admin)
    if user_id == target_user_id:
        await query.edit_message_text(
            "❌ No puedes visitar tu propio link.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
        )
        return

    target_user = get_user(target_user_id)
    if not target_user:
        await query.edit_message_text(
            "❌ Usuario no encontrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
        )
        return

    # ✅ Registrar el clic y dar reputación
    record_click(user_id, link_id, reputation_earned=5)
    logger.info(f"✅ +5 reputación para usuario {user_id} por visitar link de {target_user_id}")

    await query.edit_message_text(
        f"✅ **¡+5 reputación!**\n\n"
        f"Has visitado el link de **@{username}**\n\n"
        f"🔗 **Link visitado:** `{link_url}`\n\n"
        f"🎁 Sigue visitando links para ganar más puntos.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎁 Ver más links", callback_data="more_links")],
            [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
        ]),
        parse_mode='Markdown'
    )

async def more_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra más links disponibles."""
    query = update.callback_query
    logger.info("🔄 more_links: Mostrando más links")
    await query.answer()
    await earn_reputation(update, context)
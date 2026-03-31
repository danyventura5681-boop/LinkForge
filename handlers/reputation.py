import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_top_users, get_user, add_reputation, get_user_links

logger = logging.getLogger(__name__)

async def earn_reputation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los top 5 links para ganar reputación."""
    user_id = update.effective_user.id
    logger.info(f"🎁 earn_reputation: Usuario {user_id} solicitó ganar reputación")

    top_users = get_top_users(limit=10)
    available_users = [u for u in top_users if u.telegram_id != user_id][:5]

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

    context.user_data['available_links'] = [(u.telegram_id, u.username) for u in available_users]

    text = "🎁 **Gana reputación** 🎁\n\n"
    text += "Haz clic en los links de otros usuarios para ganar **+5 reputación** cada uno.\n\n"
    text += "**Links disponibles:**\n\n"

    keyboard = []
    for i, user in enumerate(available_users, 1):
        username = user.username or f"Usuario_{user.telegram_id}"
        text += f"{i}. @{username} - {user.reputation} pts\n"

        # Buscar link del usuario
        user_links = get_user_links(user.telegram_id)
        if user_links:
            link_url = user_links[0].url
            keyboard.append([InlineKeyboardButton(
                f"🔗 Visitar link de @{username} (+5)",
                callback_data=f"visit_link_{user.telegram_id}_{link_url}"
            )])

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
    parts = query.data.split("_")
    target_user_id = int(parts[2])
    link_url = "_".join(parts[3:]) if len(parts) > 3 else ""

    logger.info(f"🔗 visit_link: Usuario {user_id} visitó link de {target_user_id}")

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

    add_reputation(user_id, 5)
    logger.info(f"✅ +5 reputación para usuario {user_id}")

    username = target_user.username or f"Usuario_{target_user_id}"

    await query.edit_message_text(
        f"✅ **+5 reputación!**\n\n"
        f"Has visitado el link de **@{username}**\n\n"
        f"🔗 Link visitado: {link_url}\n\n"
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
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_top_users, get_user_rank, get_user

logger = logging.getLogger(__name__)

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el top de usuarios por reputación."""
    user_id = update.effective_user.id
    logger.info(f"📊 ranking: Mostrando ranking para usuario {user_id}")

    top_users = get_top_users(limit=10)

    if not top_users:
        text = "📊 **Ranking vacío**\n\nSé el primero en registrar un link usando el botón 'Registrar Link'."
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]]

        # Si viene de un callback (botón), usar query.edit_message_text
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

    text = "🏆 **TOP 10 - Reputación** 🏆\n\n"

    for i, user in enumerate(top_users, 1):
        username = user["username"] or f"Usuario_{user['telegram_id']}"
        reputation = user["reputation"]
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
        text += f"{medal} **{i}. {username}** - {reputation} pts\n"

    user_rank = get_user_rank(user_id)
    user = get_user(user_id)

    if user and user_rank:
        text += f"\n📌 **Tu posición:** #{user_rank} - {user['reputation']} pts"
    else:
        text += "\n📌 **Todavía no tienes reputación.**\nRegistra un link para comenzar."

    keyboard = [
        [InlineKeyboardButton("🔄 Actualizar", callback_data="refresh_ranking")],
        [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
    ]

    # Si viene de un callback (botón), usar query.edit_message_text
    if update.callback_query:
        query = update.callback_query
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        # Si viene de un comando /ranking
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    logger.info("📊 ranking: Ranking mostrado correctamente")

async def ranking_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja botones del ranking"""
    query = update.callback_query
    logger.info(f"🔄 ranking_button_handler: {query.data}")
    await query.answer()

    if query.data == "refresh_ranking":
        logger.info("🔄 Actualizando ranking...")
        await ranking(update, context)
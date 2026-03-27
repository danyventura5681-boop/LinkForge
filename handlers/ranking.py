import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_top_users, get_user_rank

logger = logging.getLogger(__name__)

async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el top de usuarios por reputación."""
    user_id = update.effective_user.id
    
    # Obtener top 10 usuarios
    top_users = get_top_users(limit=10)
    
    if not top_users:
        await update.message.reply_text(
            "📊 **Ranking vacío**\n\n"
            "Sé el primero en registrar un link con /register",
            parse_mode='Markdown'
        )
        return
    
    # Construir mensaje
    text = "🏆 **TOP 10 - Reputación** 🏆\n\n"
    
    for i, user in enumerate(top_users, 1):
        username = user["username"] or f"Usuario_{user['telegram_id']}"
        reputation = user["reputation"]
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
        text += f"{medal} **{i}. {username}** - {reputation} pts\n"
    
    # Posición del usuario actual
    user_rank = get_user_rank(user_id)
    user = get_user(user_id)
    
    if user and user_rank:
        text += f"\n📌 **Tu posición:** #{user_rank} - {user['reputation']} pts"
    else:
        text += "\n📌 **Todavía no tienes reputación.**\nRegistra un link con /register"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Actualizar", callback_data="refresh_ranking")],
        [InlineKeyboardButton("🏠 Volver al inicio", callback_data="back_to_start")]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def ranking_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja botones del ranking"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "refresh_ranking":
        # Re-enviar ranking actualizado
        from handlers.start import start
        await start(update, context)
    elif query.data == "back_to_start":
        from handlers.start import start
        await start(update, context)
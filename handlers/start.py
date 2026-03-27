import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_user, create_user, get_user_rank

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensaje de bienvenida"""
    user = update.effective_user
    telegram_id = user.id
    username = user.username or user.first_name or "Usuario"

    existing_user = get_user(telegram_id)
    
    if not existing_user:
        create_user(telegram_id, username)
        logger.info(f"✅ Nuevo usuario: {username}")
        reputation = 0
        rank = "Nuevo"
    else:
        reputation = existing_user["reputation"]
        rank = get_user_rank(telegram_id) or "?"

    text = (
        f"🚀 **¡Bienvenido a LinkForge, {username}!**\n\n"
        f"💎 **Tu reputación:** {reputation} puntos\n"
        f"📈 **Posición:** #{rank}\n\n"
        f"📌 Usa /register [URL] para comenzar."
    )

    keyboard = [
        [InlineKeyboardButton("🔗 Registrar Link", callback_data="register_link")],
        [InlineKeyboardButton("📊 Ver Ranking", callback_data="show_ranking")]
    ]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "register_link":
        await query.edit_message_text("🔗 Envíame tu link con /register [URL]")
    elif query.data == "show_ranking":
        await query.edit_message_text("📊 Ranking en desarrollo. Usa /ranking")
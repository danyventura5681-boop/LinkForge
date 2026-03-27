import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_user, add_reputation

logger = logging.getLogger(__name__)

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el enlace de referido del usuario."""
    user = update.effective_user
    telegram_id = user.id
    username = user.username or user.first_name or "Usuario"
    
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{telegram_id}"
    
    text = (
        f"👥 **Invita amigos y gana reputación** 👥\n\n"
        f"🔗 **Tu enlace de referido:**\n"
        f"`{referral_link}`\n\n"
        f"🎁 **Recompensa:**\n"
        f"Por cada amigo que se una usando tu enlace, ¡ganas **+50 reputación**!\n\n"
        f"📤 Comparte el enlace con tus amigos y empieza a ganar."
    )
    
    keyboard = [
        [InlineKeyboardButton("📤 Compartir enlace", url=f"https://t.me/share/url?url={referral_link}&text=¡Únete a LinkForge!")],
        [InlineKeyboardButton("🏠 Volver al inicio", callback_data="back_to_start")]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def process_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa cuando un usuario llega por enlace de referido."""
    args = context.args
    if args and args[0].startswith('ref_'):
        referrer_id = int(args[0][4:])
        user_id = update.effective_user.id
        
        # Verificar que no es el mismo usuario
        if user_id == referrer_id:
            return
        
        # Dar reputación al referente
        add_reputation(referrer_id, 50)
        logger.info(f"Referido: {user_id} -> {referrer_id}")
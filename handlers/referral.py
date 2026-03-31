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
    logger.info(f"👥 referral: Usuario {username} solicitó su enlace de referido")

    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{telegram_id}"

    text = (
        f"👥 **Invita amigos y gana reputación** 👥\n\n"
        f"🔗 **Tu enlace de referido:**\n"
        f"`{referral_link}`\n\n"
        f"🎁 **Recompensa:**\n"
        f"Por cada amigo que se una usando tu enlace, ¡ganas **+50 reputación**!\n\n"
        f"📤 Comparte el enlace con tus amigos y empieza a ganar puntos extras.\n\n"
        f"💡 *Consejo: Comparte el enlace en tus redes sociales para más recompensas.*"
    )

    keyboard = [
        [InlineKeyboardButton("📤 Compartir enlace", url=f"https://t.me/share/url?url={referral_link}&text=¡Únete a LinkForge! 🚀 Gana reputación mientras ayudas a otros!")],
        [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
    ]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    logger.info(f"👥 Enlace de referido mostrado para {username}")

async def process_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa cuando un usuario llega por enlace de referido."""
    args = context.args
    logger.info(f"🔗 process_referral: Args recibidos: {args}")
    
    if args and args[0].startswith('ref_'):
        referrer_id = int(args[0][4:])
        user_id = update.effective_user.id
        logger.info(f"🔗 Referido: user {user_id} vino por enlace de {referrer_id}")

        if user_id == referrer_id:
            logger.info("⚠️ Usuario intentó referirse a sí mismo")
            return

        from database.database import get_user
        existing_user = get_user(user_id)
        if existing_user:
            logger.info(f"⚠️ Usuario {user_id} ya existe, no se da recompensa")
            return

        add_reputation(referrer_id, 50)
        logger.info(f"✅ Referido exitoso: {user_id} -> {referrer_id}, +50 reputación")

        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=f"🎉 **¡Alguien se unió por tu enlace!**\n\n"
                     f"👤 Nuevo usuario: {update.effective_user.first_name or 'Alguien'}\n"
                     f"🎁 +50 reputación añadida a tu cuenta.\n\n"
                     f"📊 Usa el botón 'Invitar Amigos' para ver tu enlace personal.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Ver panel", callback_data="volver_menu")]]),
                parse_mode='Markdown'
            )
            logger.info(f"✅ Notificación enviada al referente {referrer_id}")
        except Exception as e:
            logger.error(f"❌ Error notificando al referente {referrer_id}: {e}")
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_user, create_user, get_user_rank

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensaje de bienvenida y panel principal"""
    user = update.effective_user
    telegram_id = user.id
    username = user.username or user.first_name or "Usuario"

    existing_user = get_user(telegram_id)
    
    if not existing_user:
        # Verificar si viene por referido
        args = context.args
        referred_by = None
        if args and args[0].startswith('ref_'):
            referred_by = int(args[0][4:])
        create_user(telegram_id, username, referred_by)
        logger.info(f"✅ Nuevo usuario: {username}")
        reputation = 0
        rank = "Nuevo"
    else:
        reputation = existing_user["reputation"]
        rank = get_user_rank(telegram_id) or "?"

    text = (
        f"🚀 **¡Bienvenido a LinkForge, {username}!** 🚀\n\n"
        f"💎 **Tu reputación:** {reputation} puntos\n"
        f"📈 **Posición en ranking:** #{rank}\n\n"
        f"🔗 **Registra tu link** para comenzar a promocionarlo.\n"
        f"🎁 **Gana reputación** visitando links de otros usuarios.\n"
        f"👥 **Invita amigos** y gana +50 por cada uno.\n"
        f"💎 **Actualiza a VIP** para más beneficios.\n\n"
        f"📌 **Comandos disponibles:**"
    )

    keyboard = [
        [InlineKeyboardButton("🔗 Registrar Link", callback_data="register_link")],
        [InlineKeyboardButton("📊 Ver Ranking", callback_data="show_ranking")],
        [InlineKeyboardButton("🎁 Ganar Reputación", callback_data="earn_reputation")],
        [InlineKeyboardButton("👥 Invitar Amigos", callback_data="referral")],
        [InlineKeyboardButton("💎 VIP", callback_data="vip_menu")],
        [InlineKeyboardButton("🛡️ Admin", callback_data="admin_panel")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones del menú principal"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "register_link":
        await query.edit_message_text(
            "🔗 **Para registrar tu link, usa:**\n\n"
            "`/register https://tusitio.com`\n\n"
            "Recuerda incluir `http://` o `https://`",
            parse_mode='Markdown'
        )
    elif data == "show_ranking":
        from handlers.ranking import ranking
        await ranking(update, context)
    elif data == "earn_reputation":
        from handlers.reputation import earn_reputation
        await earn_reputation(update, context)
    elif data == "referral":
        from handlers.referral import referral
        await referral(update, context)
    elif data == "vip_menu":
        from handlers.vip import vip_menu
        await vip_menu(update, context)
    elif data == "admin_panel":
        from handlers.admin import admin_panel
        await admin_panel(update, context)
    elif data == "back_to_start":
        await start(update, context)
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
        create_user(telegram_id, username)
        logger.info(f"✅ Nuevo usuario: {username}")
        reputation = 0
        rank = "Nuevo"
    else:
        reputation = existing_user["reputation"] if existing_user["reputation"] else 0
        rank = get_user_rank(telegram_id) or "?"

    text = (
        f"🎉 **¡Bienvenido a LinkForge, {username}!**\n\n"
        f"💎 **Tu reputación:** {reputation} puntos\n"
        f"📈 **Posición en ranking:** #{rank}\n\n"
        f"📌 Registra tu link para comenzar a promocionarlo.\n"
        f"🎁 Gana reputación visitando links de otros usuarios.\n"
        f"👥 Invita amigos y gana +50 por cada uno.\n"
        f"⭐ Actualiza a VIP para más beneficios.\n\n"
        f"**Comandos disponibles:**"
    )

    keyboard = [
        [InlineKeyboardButton("🔗 Registrar Link", callback_data="register_link")],
        [InlineKeyboardButton("📊 Ver Ranking", callback_data="show_ranking")],
        [InlineKeyboardButton("🎁 Ganar Reputación", callback_data="earn_reputation")],
        [InlineKeyboardButton("👥 Invitar Amigos", callback_data="referral")],
        [InlineKeyboardButton("⭐ VIP", callback_data="vip_info")],
        [InlineKeyboardButton("🛡️ Admin", callback_data="admin_panel")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones del menú"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "register_link":
        await query.edit_message_text(
            "🔗 **Registra tu link para promocionarlo**\n\n"
            "Usa el comando:\n"
            "`/register https://tusitio.com`\n\n"
            "Recuerda incluir `http://` o `https://`",
            parse_mode='Markdown'
        )
        
    elif data == "show_ranking":
        await query.edit_message_text(
            "📊 **Ranking de reputación**\n\n"
            "Usa el comando:\n"
            "`/ranking`\n\n"
            "Pronto podrás ver los usuarios con más reputación.",
            parse_mode='Markdown'
        )
        
    elif data == "earn_reputation":
        await query.edit_message_text(
            "🎁 **Gana reputación**\n\n"
            "Para ganar puntos, visita los links de otros usuarios:\n\n"
            "1️⃣ Ve al ranking con `/ranking`\n"
            "2️⃣ Haz clic en el link de otro usuario\n"
            "3️⃣ Gana +5 reputación por cada visita\n\n"
            "También puedes:\n"
            "• Invitar amigos: +50 por cada uno\n"
            "• Comprar VIP: +500 a +6000 reputación",
            parse_mode='Markdown'
        )
        
    elif data == "referral":
        user_id = query.from_user.id
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        
        await query.edit_message_text(
            f"👥 **Invita amigos y gana reputación**\n\n"
            f"🔗 **Tu enlace personal:**\n"
            f"`{ref_link}`\n\n"
            f"🎁 **Recompensa:** +50 reputación por cada amigo que se una\n\n"
            f"📤 Comparte este enlace y empieza a ganar puntos extras.",
            parse_mode='Markdown'
        )
        
    elif data == "vip_info":
        text = (
            "⭐ **PLANES VIP** ⭐\n\n"
            "**VIP 1** - $1 USD\n"
            "• 3 links simultáneos\n"
            "• +500 reputación\n"
            "• 30 días de promoción\n\n"
            "**VIP 2** - $5 USD\n"
            "• 3 links simultáneos\n"
            "• +2800 reputación\n"
            "• 30 días de promoción\n\n"
            "**VIP 3** - $10 USD\n"
            "• 3 links simultáneos\n"
            "• +6000 reputación\n"
            "• 30 días de promoción\n\n"
            "💳 **Aceptamos:** TRX, TON, ETH, BTC, BNB, SOL\n\n"
            "Contacta a @danyvg56 para activar tu plan."
        )
        await query.edit_message_text(text, parse_mode='Markdown')
        
    elif data == "admin_panel":
        user_id = query.from_user.id
        if user_id == 5057900537:  # Tu ID de Telegram
            await query.edit_message_text(
                "🛡️ **Panel de Administración**\n\n"
                "Comandos disponibles:\n"
                "`/add_reputation ID cantidad` - Añadir reputación\n"
                "`/ban_user ID` - Banear usuario\n"
                "`/total_users` - Ver total de usuarios\n\n"
                "En desarrollo: panel visual con botones.",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("⛔ Acceso denegado. Solo administradores.")
    
    else:
        await query.edit_message_text("❌ Función en desarrollo. Pronto estará disponible.")
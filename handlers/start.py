import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_user, create_user, get_user_rank, get_user_links

logger = logging.getLogger(__name__)

def format_time_remaining(expires_at_str):
    """Calcula los días y horas restantes"""
    if not expires_at_str:
        return "No activo"
    
    try:
        # Manejar formato ISO
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
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
    except Exception as e:
        logger.error(f"Error formateando tiempo: {e}")
        return "No disponible"

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
        links = []
        vip_level = 0
    else:
        reputation = existing_user["reputation"] if existing_user["reputation"] else 0
        rank = get_user_rank(telegram_id) or "?"
        links = get_user_links(telegram_id)
        vip_level = existing_user.get("vip_level", 0)

    # Obtener link principal (si existe)
    main_link = links[0] if links else None
    
    # Calcular tiempo restante del link
    if main_link and main_link.get("expires_at"):
        time_remaining = format_time_remaining(main_link["expires_at"])
        link_display = f"🔗 **Link activo:** `{main_link['url']}`\n⏳ **Tiempo restante:** {time_remaining}"
        link_status = "✅ Activo" if "EXPIRADO" not in time_remaining else "⚠️ Por renovar"
    else:
        link_display = "🔗 **Link:** No registrado"
        link_status = "❌ Sin link"

    text = (
        f"🎉 **¡Bienvenido a LinkForge, {username}!**\n\n"
        f"🆔 **Tu ID:** `{telegram_id}`\n"
        f"💎 **Tu reputación:** {reputation} puntos\n"
        f"📈 **Posición en ranking:** #{rank}\n"
        f"⭐ **VIP Nivel:** {vip_level}\n\n"
        f"{link_display}\n\n"
        f"📌 Registra tu link para comenzar a promocionarlo.\n"
        f"🎁 Gana reputación visitando links de otros usuarios.\n"
        f"👥 Invita amigos y gana +50 por cada uno.\n"
        f"⭐ Actualiza a VIP para más beneficios.\n\n"
        f"**Comandos disponibles:**"
    )

    keyboard = [
        [InlineKeyboardButton("🔗 Mi Link", callback_data="my_link")],
        [InlineKeyboardButton("✏️ Cambiar Link", callback_data="change_link")],
    ]
    
    # Botón de agregar link solo para VIP
    if vip_level > 0:
        keyboard.append([InlineKeyboardButton("➕ Agregar Link (VIP)", callback_data="add_link_vip")])
    
    keyboard.extend([
        [InlineKeyboardButton("📊 Ver Ranking", callback_data="show_ranking")],
        [InlineKeyboardButton("🎁 Ganar Reputación", callback_data="earn_reputation")],
        [InlineKeyboardButton("👥 Invitar Amigos", callback_data="referral")],
        [InlineKeyboardButton("⭐ VIP", callback_data="vip_info")],
        [InlineKeyboardButton("🛡️ Admin", callback_data="admin_panel")],
        [InlineKeyboardButton("🔄 Renovar Link", callback_data="renew_link")]
    ])

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
    
    # Botón de volver al menú principal
    if data == "back_to_start":
        # Reconstruir el panel principal desde cero
        user_id = query.from_user.id
        existing_user = get_user(user_id)
        username = existing_user["username"] if existing_user else "Usuario"
        reputation = existing_user["reputation"] if existing_user else 0
        rank = get_user_rank(user_id) or "?"
        links = get_user_links(user_id)
        vip_level = existing_user.get("vip_level", 0) if existing_user else 0
        
        main_link = links[0] if links else None
        if main_link and main_link.get("expires_at"):
            time_remaining = format_time_remaining(main_link["expires_at"])
            link_display = f"🔗 **Link activo:** `{main_link['url']}`\n⏳ **Tiempo restante:** {time_remaining}"
        else:
            link_display = "🔗 **Link:** No registrado"
        
        text = (
            f"🎉 **¡Bienvenido a LinkForge, {username}!**\n\n"
            f"🆔 **Tu ID:** `{user_id}`\n"
            f"💎 **Tu reputación:** {reputation} puntos\n"
            f"📈 **Posición en ranking:** #{rank}\n"
            f"⭐ **VIP Nivel:** {vip_level}\n\n"
            f"{link_display}\n\n"
            f"📌 Registra tu link para comenzar a promocionarlo.\n"
            f"🎁 Gana reputación visitando links de otros usuarios.\n"
            f"👥 Invita amigos y gana +50 por cada uno.\n"
            f"⭐ Actualiza a VIP para más beneficios.\n\n"
            f"**Comandos disponibles:**"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔗 Mi Link", callback_data="my_link")],
            [InlineKeyboardButton("✏️ Cambiar Link", callback_data="change_link")],
        ]
        if vip_level > 0:
            keyboard.append([InlineKeyboardButton("➕ Agregar Link (VIP)", callback_data="add_link_vip")])
        keyboard.extend([
            [InlineKeyboardButton("📊 Ver Ranking", callback_data="show_ranking")],
            [InlineKeyboardButton("🎁 Ganar Reputación", callback_data="earn_reputation")],
            [InlineKeyboardButton("👥 Invitar Amigos", callback_data="referral")],
            [InlineKeyboardButton("⭐ VIP", callback_data="vip_info")],
            [InlineKeyboardButton("🛡️ Admin", callback_data="admin_panel")],
            [InlineKeyboardButton("🔄 Renovar Link", callback_data="renew_link")]
        ])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return

    # ===========================================
    # BOTONES PRINCIPALES
    # ===========================================
    
    elif data == "my_link":
        user_id = query.from_user.id
        links = get_user_links(user_id)
        
        if not links:
            text = "🔗 **No tienes ningún link registrado.**\n\nUsa `/register https://tusitio.com` para comenzar."
        else:
            main_link = links[0]
            time_left = format_time_remaining(main_link.get("expires_at"))
            created = main_link.get("created_at", "")
            if created:
                created = created[:10] if isinstance(created, str) else str(created)[:10]
            else:
                created = "N/A"
            
            text = (
                f"🔗 **Tu link actual:**\n`{main_link['url']}`\n\n"
                f"📊 **Clics recibidos:** {main_link.get('clicks_received', 0)}\n"
                f"⏳ **Tiempo restante:** {time_left}\n"
                f"📅 **Registrado:** {created}\n\n"
                f"✏️ Usa `/register [NUEVA_URL]` para cambiarlo.\n"
                f"💰 Compra VIP para extender la promoción a 30 días."
            )
        
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="back_to_start")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif data == "change_link":
        text = (
            "✏️ **Cambiar link**\n\n"
            "Envía tu nuevo link con el comando:\n"
            "`/register https://tusitio.com`\n\n"
            "⚠️ Tu reputación se mantiene, pero la promoción reinicia a 10 días (30 si eres VIP)."
        )
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="back_to_start")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif data == "renew_link":
        text = (
            "🔄 **Renovar promoción**\n\n"
            "Para extender la promoción de tu link:\n\n"
            "🔹 **Usuarios normales:** 10 días (gratis)\n"
            "🔹 **VIP 1-3:** 30 días\n\n"
            "⭐ **Activa VIP para:**\n"
            "• 30 días de promoción\n"
            "• +500 a +6000 reputación\n"
            "• Hasta 3 links simultáneos\n\n"
            "Usa `/vip` para ver los planes."
        )
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="back_to_start")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif data == "register_link":
        text = (
            "🔗 **Registra tu link para promocionarlo**\n\n"
            "Usa el comando:\n"
            "`/register https://tusitio.com`\n\n"
            "Recuerda incluir `http://` o `https://`"
        )
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="back_to_start")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "show_ranking":
        text = (
            "📊 **Ranking de reputación**\n\n"
            "Usa el comando:\n"
            "`/ranking`\n\n"
            "Pronto podrás ver los usuarios con más reputación."
        )
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="back_to_start")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "earn_reputation":
        text = (
            "🎁 **Gana reputación**\n\n"
            "Para ganar puntos, visita los links de otros usuarios:\n\n"
            "1️⃣ Ve al ranking con `/ranking`\n"
            "2️⃣ Haz clic en el link de otro usuario\n"
            "3️⃣ Gana +5 reputación por cada visita\n\n"
            "También puedes:\n"
            "• Invitar amigos: +50 por cada uno\n"
            "• Comprar VIP: +500 a +6000 reputación"
        )
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="back_to_start")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "referral":
        user_id = query.from_user.id
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        
        text = (
            f"👥 **Invita amigos y gana reputación**\n\n"
            f"🔗 **Tu enlace personal:**\n"
            f"`{ref_link}`\n\n"
            f"🎁 **Recompensa:** +50 reputación por cada amigo que se una\n\n"
            f"📤 Comparte este enlace y empieza a ganar puntos extras."
        )
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="back_to_start")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

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
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="back_to_start")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "add_link_vip":
        user_id = query.from_user.id
        existing_user = get_user(user_id)
        vip_level = existing_user.get("vip_level", 0) if existing_user else 0
        
        if vip_level == 0:
            text = "⭐ **Solo disponible para usuarios VIP.**\n\nActualiza tu cuenta con `/vip` para acceder a múltiples links."
        else:
            text = (
                f"➕ **Agregar nuevo link (VIP Nivel {vip_level})**\n\n"
                "Envía tu nuevo link con el comando:\n"
                "`/addlink https://tusitio.com`\n\n"
                f"📌 Links activos actuales: {len(get_user_links(user_id))}/3\n"
                "Cada nuevo link tiene 30 días de promoción."
            )
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="back_to_start")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "admin_panel":
        user_id = query.from_user.id
        if user_id == 5057900537:  # Tu ID de Telegram
            text = (
                "🛡️ **Panel de Administración**\n\n"
                "Comandos disponibles:\n"
                "`/add_reputation ID cantidad` - Añadir reputación\n"
                "`/ban_user ID` - Banear usuario\n"
                "`/total_users` - Ver total de usuarios\n\n"
                "En desarrollo: panel visual con botones."
            )
        else:
            text = "⛔ Acceso denegado. Solo administradores."
        
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="back_to_start")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    else:
        text = "❌ Función en desarrollo. Pronto estará disponible."
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="back_to_start")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
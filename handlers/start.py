import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import (
    get_user, create_user, get_user_rank, get_user_links, 
    get_referrals_count, get_user_videos
)

logger = logging.getLogger(__name__)

# Diccionario para almacenar usuarios que aceptaron políticas
USER_ACCEPTED_PRIVACY = {}

def format_time_remaining(expires_at):
    """Calcula los días y horas restantes (acepta datetime o string)"""
    if not expires_at:
        return "No activo"

    try:
        if isinstance(expires_at, datetime):
            expires_dt = expires_at
        else:
            expires_dt = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))

        now = datetime.utcnow()

        if expires_dt <= now:
            return "⚠️ EXPIRADO"

        remaining = expires_dt - now
        days = remaining.days
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60

        if days > 0:
            return f"{days} días, {hours} horas"
        elif hours > 0:
            return f"{hours} horas, {minutes} minutos"
        else:
            return f"{minutes} minutos"
    except Exception as e:
        logger.error(f"Error formateando tiempo: {e}")
        return "No disponible"

async def privacy_policy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la política de privacidad y solicita aceptación."""
    user_id = update.effective_user.id
    
    text = (
        "📋 **POLÍTICA DE PRIVACIDAD Y TÉRMINOS DE USO** 📋\n\n"
        "Bienvenido a **LinkForge**.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📌 **1. SERVICIO OFRECIDO**\n"
        "LinkForge es una plataforma que permite a los usuarios promocionar "
        "enlaces de referidos, videos y contenido digital, así como ganar "
        "reputación interactuando con el contenido de otros usuarios.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ **2. LIMITACIÓN DE RESPONSABILIDAD**\n"
        "LinkForge NO se hace responsable por:\n"
        "• Enlaces maliciosos o fraudulentos publicados por usuarios\n"
        "• Empresas o servicios que no cumplan con las recompensas prometidas\n"
        "• Daños directos o indirectos derivados del uso de enlaces de terceros\n"
        "• Pérdida de datos, reputación o beneficios por mal uso de la plataforma\n\n"
        "El usuario es el único responsable de verificar la legitimidad de los "
        "enlaces que comparte y de los que visita.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔒 **3. DATOS RECOPILADOS**\n"
        "• ID de Telegram\n"
        "• Nombre de usuario\n"
        "• Enlaces registrados\n"
        "• Reputación y nivel VIP\n\n"
        "No compartimos tus datos con terceros.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ **Al presionar 'ACEPTO', confirmas que:**\n"
        "• Has leído y aceptas estos términos\n"
        "• Eres mayor de edad\n"
        "• Usarás la plataforma de manera responsable\n\n"
        "📧 Contacto: @dany_vg56"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ ACEPTO LOS TÉRMINOS", callback_data="accept_privacy")],
        [InlineKeyboardButton("❌ RECHAZAR", callback_data="reject_privacy")]
    ]
    
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

async def accept_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usuario acepta la política de privacidad."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    USER_ACCEPTED_PRIVACY[user_id] = True
    
    await query.edit_message_text(
        "✅ **Has aceptado los términos de uso.**\n\n"
        "📊 Redirigiendo al panel principal...",
        parse_mode='Markdown'
    )
    
    # Mostrar menú principal
    await start(update, context)

async def reject_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usuario rechaza la política de privacidad."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "❌ **Debes aceptar los términos de uso para usar LinkForge.**\n\n"
        "Si cambias de opinión, usa /start nuevamente.",
        parse_mode='Markdown'
    )

async def process_visit_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Marca que el usuario realmente abrió el link."""
    user = update.effective_user
    args = context.args

    if not args or not args[0].startswith("visit_"):
        return

    token = args[0][6:]

    from handlers.reputation import LINK_VISITS

    if token in LINK_VISITS:
        LINK_VISITS[token]["visited"] = True
        logger.info(f"✅ Usuario {user.id} abrió el link correctamente (token={token})")
        try:
            await update.message.reply_text(
                "✅ **Verificación exitosa!**\n\n"
                "Ya puedes cerrar esta ventana y volver al bot.",
                parse_mode='Markdown'
            )
        except:
            pass
    else:
        logger.warning(f"❌ Token no encontrado en start: {token}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Mensaje de bienvenida y panel principal.
    """
    # Procesar token de visita
    await process_visit_token(update, context)
    
    user = update.effective_user
    telegram_id = user.id
    username = user.username or user.first_name or "Usuario"

    # Verificar si ya aceptó políticas
    if telegram_id not in USER_ACCEPTED_PRIVACY:
        await privacy_policy(update, context)
        return

    existing_user = get_user(telegram_id)

    # Manejo de referidos
    if not existing_user:
        referrer_id = None
        if context.args and context.args[0].startswith("ref_"):
            try:
                referrer_id = int(context.args[0][4:])
                if referrer_id == telegram_id:
                    referrer_id = None
            except (ValueError, IndexError):
                referrer_id = None

        user_created = create_user(telegram_id, username, referred_by=referrer_id)
        if user_created:
            logger.info(f"✅ Nuevo usuario creado: {telegram_id} (@{username})")
        
        reputation = 0
        rank = "Nuevo"
        links = []
        vip_level = 0
        referrals_count = 0
    else:
        reputation = existing_user.reputation or 0
        rank = get_user_rank(telegram_id) or "?"
        links = get_user_links(telegram_id)
        vip_level = existing_user.vip_level or 0
        referrals_count = get_referrals_count(telegram_id)

    # Obtener videos del usuario
    user_videos = get_user_videos(telegram_id) if existing_user else []
    max_videos = 3 if vip_level >= 3 else 1

    # Construir mensaje
    text = (
        f"🎉 **¡Bienvenido a LinkForge, {username}!** 🎉\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **{username}**\n"
        f"🆔 `{telegram_id}`\n"
        f"💎 **Reputación:** {reputation} puntos\n"
        f"👥 **Referidos:** {referrals_count}\n"
        f"🏆 **Ranking:** #{rank}\n"
        f"⭐ **VIP Nivel:** {vip_level}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 **LINKS ACTIVOS**\n"
    )
    
    # Mostrar links
    if links:
        for i, link in enumerate(links[:3], 1):
            time_left = format_time_remaining(link.expires_at)
            text += f"{i}️⃣ `{link.url[:50]}...`\n"
        if links:
            text += f"⏳ **Tiempo restante:** {format_time_remaining(links[0].expires_at)}\n"
    else:
        text += "❌ No hay links registrados\n"
    
    text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
    text += f"🎬 **VIDEOS EN TOP**\n"
    
    # Mostrar videos
    if user_videos:
        for i, video in enumerate(user_videos[:3], 1):
            text += f"{i}️⃣ `{video.title[:40]}...`\n"
    else:
        text += "❌ No hay videos publicados\n"
    
    text += (
        f"\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 Registra tu link para comenzar a promocionarlo.\n"
        f"🏆 Gana reputación visitando links de otros usuarios, "
        f"Entre más reputación más alto tú posición en el Top 😉\n"
        f"👥 Invita amigos y gana +50 por cada uno.\n"
        f"⭐ Actualiza a VIP para más beneficios.\n\n"
        f"**Opciones disponibles:**"
    )

    # Teclado del menú principal
    keyboard = [
        [InlineKeyboardButton("🔗 Registrar Link", callback_data="register_link")],
        [InlineKeyboardButton("💎 Ganar Reputación", callback_data="earn_reputation")],
        [InlineKeyboardButton("🎁 Recompensa Diaria", callback_data="daily_reward")],
        [InlineKeyboardButton("👥 Invitar Amigos", callback_data="referral")],
        [InlineKeyboardButton("🏆 Ver Ranking", callback_data="show_ranking")],
        [InlineKeyboardButton("⭐ VIP", callback_data="vip_info")],
        [InlineKeyboardButton("📱 Promocionar Contenido", callback_data="promote_menu")],
    ]

    if telegram_id == 5057900537:
        keyboard.append([InlineKeyboardButton("🛡️ Admin", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones del menú principal"""
    query = update.callback_query
    logger.info(f"🟢 button_handler recibió: {query.data}")
    await query.answer()

    data = query.data

    if data == "register_link":
        logger.info("🔵 Iniciando registro de link...")
        from handlers.link import register_start
        await register_start(update, context)

    elif data == "show_ranking":
        logger.info("🔵 Mostrando ranking...")
        from handlers.ranking import ranking
        await ranking(update, context)

    elif data == "earn_reputation":
        logger.info("🔵 Mostrando ganar reputación...")
        from handlers.reputation import earn_reputation
        await earn_reputation(update, context)

    elif data == "referral":
        logger.info("🔵 Mostrando referidos...")
        from handlers.referral import referral
        await referral(update, context)

    elif data == "vip_info":
        logger.info("🔵 Mostrando VIP...")
        from handlers.vip import vip_menu
        await vip_menu(update, context)

    elif data == "admin_panel":
        logger.info("🔵 Mostrando panel admin...")
        from handlers.admin import admin_panel
        await admin_panel(update, context)

    elif data == "daily_reward":
        logger.info("🎁 Mostrando recompensa diaria...")
        from handlers.daily_reward import daily_reward
        await daily_reward(update, context)

    elif data == "top_videos":
        logger.info("📹 Mostrando top videos...")
        from handlers.video import top_videos
        await top_videos(update, context)

    elif data == "promote_menu":
        logger.info("📱 Mostrando promocionar contenido...")
        from handlers.promote import promote_menu
        await promote_menu(update, context)

    elif data == "accept_privacy":
        await accept_privacy(update, context)
    elif data == "reject_privacy":
        await reject_privacy(update, context)

    else:
        logger.info(f"🟡 Botón no reconocido: {data}")
        await query.edit_message_text(
            "❌ Función en desarrollo. Pronto estará disponible.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
        )

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para volver al menú principal."""
    logger.info("🔙 back_to_start ha sido llamado")

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    existing_user = get_user(user_id)

    if not existing_user:
        await query.edit_message_text("❌ Usuario no encontrado. Usa /start para comenzar.")
        return

    username = existing_user.username or "Usuario"
    reputation = existing_user.reputation or 0
    rank = get_user_rank(user_id) or "?"
    links = get_user_links(user_id)
    vip_level = existing_user.vip_level or 0
    referrals_count = get_referrals_count(user_id)
    
    user_videos = get_user_videos(user_id) if existing_user else []

    text = (
        f"🎉 **¡Bienvenido a LinkForge, {username}!** 🎉\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **{username}**\n"
        f"🆔 `{user_id}`\n"
        f"💎 **Reputación:** {reputation} puntos\n"
        f"👥 **Referidos:** {referrals_count}\n"
        f"🏆 **Ranking:** #{rank}\n"
        f"⭐ **VIP Nivel:** {vip_level}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 **LINKS ACTIVOS**\n"
    )
    
    if links:
        for i, link in enumerate(links[:3], 1):
            text += f"{i}️⃣ `{link.url[:50]}...`\n"
        if links:
            text += f"⏳ **Tiempo restante:** {format_time_remaining(links[0].expires_at)}\n"
    else:
        text += "❌ No hay links registrados\n"
    
    text += f"\n━━━━━━━━━━━━━━━━━━━━\n"
    text += f"🎬 **VIDEOS EN TOP**\n"
    
    if user_videos:
        for i, video in enumerate(user_videos[:3], 1):
            text += f"{i}️⃣ `{video.title[:40]}...`\n"
    else:
        text += "❌ No hay videos publicados\n"
    
    text += (
        f"\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 Registra tu link para comenzar a promocionarlo.\n"
        f"🏆 Gana reputación visitando links de otros usuarios, "
        f"Entre más reputación más alto tú posición en el Top 😉\n"
        f"👥 Invita amigos y gana +50 por cada uno.\n"
        f"⭐ Actualiza a VIP para más beneficios.\n\n"
        f"**Opciones disponibles:**"
    )

    keyboard = [
        [InlineKeyboardButton("🔗 Registrar Link", callback_data="register_link")],
        [InlineKeyboardButton("💎 Ganar Reputación", callback_data="earn_reputation")],
        [InlineKeyboardButton("🎁 Recompensa Diaria", callback_data="daily_reward")],
        [InlineKeyboardButton("👥 Invitar Amigos", callback_data="referral")],
        [InlineKeyboardButton("🏆 Ver Ranking", callback_data="show_ranking")],
        [InlineKeyboardButton("⭐ VIP", callback_data="vip_info")],
        [InlineKeyboardButton("📱 Promocionar Contenido", callback_data="promote_menu")],
    ]

    if user_id == 5057900537:
        keyboard.append([InlineKeyboardButton("🛡️ Admin", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
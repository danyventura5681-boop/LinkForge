import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_user, create_user, get_user_rank, get_user_links

logger = logging.getLogger(__name__)

def format_time_remaining(expires_at):
    """Calcula los días y horas restantes (acepta datetime o string)"""
    if not expires_at:
        return "No activo"

    try:
        # Si es datetime, usarlo directamente
        if isinstance(expires_at, datetime):
            expires_dt = expires_at
        else:
            # Si es string, convertirlo a datetime
            expires_dt = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))

        now = datetime.utcnow()

        if expires_dt <= now:
            return "⚠️ EXPIRADO"

        remaining = expires_dt - now
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
    """
    Mensaje de bienvenida y panel principal.
    🔥 Manejo de referidos (ÚNICO PUNTO DE ENTRADA)
    """
    user = update.effective_user
    telegram_id = user.id
    username = user.username or user.first_name or "Usuario"

    existing_user = get_user(telegram_id)

    # 🔥 FIX REFERIDOS (ÚNICO PUNTO DE ENTRADA)
    if not existing_user:
        referrer_id = None

        # Verificar si viene de un link de referido (ej: t.me/LinkForgeBot?start=ref_123456789)
        if context.args and context.args[0].startswith("ref_"):
            try:
                referrer_id = int(context.args[0][4:])
                logger.info(f"🔍 Referido detectado: {referrer_id} para nuevo usuario {telegram_id}")
                
                # Verificar que no se refiera a sí mismo
                if referrer_id == telegram_id:
                    logger.warning(f"⚠️ Auto-referido detectado para {telegram_id}, ignorando")
                    referrer_id = None
                    
            except (ValueError, IndexError) as e:
                logger.error(f"❌ Error procesando referido: {e}")
                referrer_id = None

        # Crear usuario con el referido (la lógica de reputación está dentro de create_user)
        user_created = create_user(telegram_id, username, referred_by=referrer_id)
        
        if user_created:
            logger.info(f"✅ Nuevo usuario creado: {telegram_id} (@{username}) con referido {referrer_id}")
        else:
            logger.error(f"❌ Error creando usuario: {telegram_id}")
        
        # Datos para el nuevo usuario
        reputation = 0
        rank = "Nuevo"
        links = []
        vip_level = 0
    else:
        # Usuario existente
        reputation = existing_user.reputation if existing_user.reputation else 0
        rank = get_user_rank(telegram_id) or "?"
        links = get_user_links(telegram_id)
        vip_level = existing_user.vip_level if existing_user.vip_level else 0
        logger.info(f"✅ Usuario existente: {telegram_id} (@{username})")

    # Mostrar información del link principal
    main_link = links[0] if links else None
    if main_link and main_link.expires_at:
        time_remaining = format_time_remaining(main_link.expires_at)
        link_display = f"🔗 **Link activo:** `{main_link.url}`\n⏳ **Tiempo restante:** {time_remaining}"
    else:
        link_display = "🔗 **Link:** No registrado"

    # Mensaje de bienvenida
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
        f"**Opciones disponibles:**"
    )

    # Teclado del menú principal
    keyboard = [
        [InlineKeyboardButton("🔗 Registrar Link", callback_data="register_link")],
        [InlineKeyboardButton("📊 Ver Ranking", callback_data="show_ranking")],
        [InlineKeyboardButton("🎁 Ganar Reputación", callback_data="earn_reputation")],
        [InlineKeyboardButton("👥 Invitar Amigos", callback_data="referral")],
        [InlineKeyboardButton("⭐ VIP", callback_data="vip_info")],
    ]

    # Botón de admin solo para el admin principal
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

    else:
        logger.info(f"🟡 Botón no reconocido: {data}")
        await query.edit_message_text(
            "❌ Función en desarrollo. Pronto estará disponible.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
        )

# ===========================================
# HANDLER ÚNICO PARA VOLVER AL MENÚ PRINCIPAL
# ===========================================

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler único para volver al menú principal desde cualquier lugar.
    Reconstruye el panel principal dinámicamente.
    """
    logger.info("🔙 🔙 🔙 back_to_start ha sido llamado 🔙 🔙 🔙")

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
    vip_level = existing_user.vip_level if existing_user.vip_level else 0

    main_link = links[0] if links else None
    if main_link and main_link.expires_at:
        time_remaining = format_time_remaining(main_link.expires_at)
        link_display = f"🔗 **Link activo:** `{main_link.url}`\n⏳ **Tiempo restante:** {time_remaining}"
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
        f"**Opciones disponibles:**"
    )

    keyboard = [
        [InlineKeyboardButton("🔗 Registrar Link", callback_data="register_link")],
        [InlineKeyboardButton("📊 Ver Ranking", callback_data="show_ranking")],
        [InlineKeyboardButton("🎁 Ganar Reputación", callback_data="earn_reputation")],
        [InlineKeyboardButton("👥 Invitar Amigos", callback_data="referral")],
        [InlineKeyboardButton("⭐ VIP", callback_data="vip_info")],
    ]

    if user_id == 5057900537:
        keyboard.append([InlineKeyboardButton("🛡️ Admin", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
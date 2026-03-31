import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.database import (
    get_user, get_user_by_username, add_reputation,
    ban_user, unban_user, make_admin, is_admin, get_total_users, get_all_links
)

logger = logging.getLogger(__name__)

# Estados para conversaciones
WAITING_USER_ID = 1
WAITING_REPUTATION = 2

ADMIN_ID = 5057900537  # Tu ID de Telegram

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el panel de administración (solo para admin)."""
    user_id = update.effective_user.id
    logger.info(f"🛡️ admin_panel: Usuario {user_id} accedió al panel admin")

    if user_id != ADMIN_ID and not is_admin(user_id):
        await update.message.reply_text(
            "⛔ No tienes permisos de administrador.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
        )
        return

    total_users = get_total_users()
    all_links = get_all_links()

    text = (
        f"🛡️ **Panel de Administración** 🛡️\n\n"
        f"📊 **Estadísticas:**\n"
        f"👥 Usuarios totales: {total_users}\n"
        f"🔗 Links activos: {len(all_links)}\n\n"
        f"🛠️ **Acciones disponibles:**"
    )

    keyboard = [
        [InlineKeyboardButton("➕ Añadir reputación", callback_data="admin_add_reputation")],
        [InlineKeyboardButton("👑 Hacer admin", callback_data="admin_make_admin")],
        [InlineKeyboardButton("🚫 Banear usuario", callback_data="admin_ban_user")],
        [InlineKeyboardButton("✅ Desbanear usuario", callback_data="admin_unban_user")],
        [InlineKeyboardButton("📋 Listar usuarios", callback_data="admin_list_users")],
        [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
    ]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    logger.info("🛡️ Panel admin mostrado")

async def add_reputation_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso para añadir reputación."""
    query = update.callback_query
    await query.answer()
    logger.info("➕ add_reputation_start: Iniciando proceso")
    await query.edit_message_text(
        "🔍 **Ingresa el ID o username del usuario:**",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="admin_panel")]])
    )
    return WAITING_USER_ID

async def add_reputation_get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obtiene el usuario y pide la cantidad."""
    user_input = update.message.text.strip()
    logger.info(f"➕ Buscando usuario: {user_input}")

    # Buscar por ID o username
    if user_input.isdigit():
        user = get_user(int(user_input))
    else:
        user = get_user_by_username(user_input)

    if not user:
        await update.message.reply_text(
            "❌ Usuario no encontrado. Intenta de nuevo.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="admin_panel")]])
        )
        return WAITING_USER_ID

    context.user_data['target_user'] = user
    await update.message.reply_text(
        "💰 **Ingresa la cantidad de reputación a añadir:**",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="admin_panel")]])
    )
    return WAITING_REPUTATION

async def add_reputation_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Añade la reputación al usuario."""
    try:
        amount = int(update.message.text.strip())
        logger.info(f"➕ Añadiendo {amount} reputación")
    except ValueError:
        await update.message.reply_text(
            "❌ Ingresa un número válido.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="admin_panel")]])
        )
        return WAITING_REPUTATION

    target_user = context.user_data['target_user']
    add_reputation(target_user["telegram_id"], amount)

    await update.message.reply_text(
        f"✅ Se añadieron **{amount} puntos** a @{target_user['username'] or target_user['telegram_id']}\n"
        f"Nueva reputación: {target_user['reputation'] + amount}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Admin", callback_data="admin_panel")]])
    )
    logger.info(f"✅ Reputación añadida a usuario {target_user['telegram_id']}")

    return ConversationHandler.END

async def make_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Acción para hacer admin a un usuario (conversación)."""
    query = update.callback_query
    await query.answer()
    logger.info("👑 make_admin_action: Iniciando proceso")
    await query.edit_message_text(
        "👑 **Ingresa el ID o username del usuario a hacer admin:**",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="admin_panel")]])
    )
    return WAITING_USER_ID

async def make_admin_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa hacer admin a un usuario."""
    user_input = update.message.text.strip()
    logger.info(f"👑 Procesando hacer admin: {user_input}")

    if user_input.isdigit():
        user = get_user(int(user_input))
    else:
        user = get_user_by_username(user_input)

    if not user:
        await update.message.reply_text(
            "❌ Usuario no encontrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Admin", callback_data="admin_panel")]])
        )
        return ConversationHandler.END

    if user["is_admin"]:
        await update.message.reply_text(
            f"👑 El usuario @{user['username'] or user['telegram_id']} ya es administrador.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Admin", callback_data="admin_panel")]])
        )
        return ConversationHandler.END

    make_admin(user["telegram_id"])

    await update.message.reply_text(
        f"✅ **@{user['username'] or user['telegram_id']} ahora es administrador.**",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Admin", callback_data="admin_panel")]])
    )
    logger.info(f"👑 Usuario {user['telegram_id']} ahora es admin")

    # Notificar al nuevo admin
    try:
        await context.bot.send_message(
            chat_id=user["telegram_id"],
            text="👑 **¡Felicidades! Has sido nombrado administrador de LinkForge.**\n\n"
                 "Ahora tienes acceso al panel de administración.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛡️ Ver Admin Panel", callback_data="admin_panel")]]),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error notificando al nuevo admin: {e}")

    return ConversationHandler.END

async def ban_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Acción para banear usuario (conversación)."""
    query = update.callback_query
    await query.answer()
    logger.info("🚫 ban_user_action: Iniciando proceso")
    await query.edit_message_text(
        "🚫 **Ingresa el ID o username del usuario a banear:**",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="admin_panel")]])
    )
    return WAITING_USER_ID

async def ban_user_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa banear a un usuario."""
    user_input = update.message.text.strip()
    logger.info(f"🚫 Procesando banear: {user_input}")

    if user_input.isdigit():
        user = get_user(int(user_input))
    else:
        user = get_user_by_username(user_input)

    if not user:
        await update.message.reply_text(
            "❌ Usuario no encontrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Admin", callback_data="admin_panel")]])
        )
        return ConversationHandler.END

    if user["is_banned"]:
        await update.message.reply_text(
            f"🚫 El usuario @{user['username'] or user['telegram_id']} ya está baneado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Admin", callback_data="admin_panel")]])
        )
        return ConversationHandler.END

    ban_user(user["telegram_id"])

    await update.message.reply_text(
        f"✅ **@{user['username'] or user['telegram_id']} ha sido baneado.**",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Admin", callback_data="admin_panel")]])
    )
    logger.info(f"🚫 Usuario {user['telegram_id']} baneado")

    # Notificar al usuario baneado
    try:
        await context.bot.send_message(
            chat_id=user["telegram_id"],
            text="🚫 **Has sido baneado de LinkForge.**\n\n"
                 "Si crees que es un error, contacta al administrador.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error notificando al usuario baneado: {e}")

    return ConversationHandler.END

async def unban_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Acción para desbanear usuario (conversación)."""
    query = update.callback_query
    await query.answer()
    logger.info("✅ unban_user_action: Iniciando proceso")
    await query.edit_message_text(
        "✅ **Ingresa el ID o username del usuario a desbanear:**",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="admin_panel")]])
    )
    return WAITING_USER_ID

async def unban_user_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa desbanear a un usuario."""
    user_input = update.message.text.strip()
    logger.info(f"✅ Procesando desbanear: {user_input}")

    if user_input.isdigit():
        user = get_user(int(user_input))
    else:
        user = get_user_by_username(user_input)

    if not user:
        await update.message.reply_text(
            "❌ Usuario no encontrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Admin", callback_data="admin_panel")]])
        )
        return ConversationHandler.END

    if not user["is_banned"]:
        await update.message.reply_text(
            f"✅ El usuario @{user['username'] or user['telegram_id']} no está baneado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Admin", callback_data="admin_panel")]])
        )
        return ConversationHandler.END

    unban_user(user["telegram_id"])

    await update.message.reply_text(
        f"✅ **@{user['username'] or user['telegram_id']} ha sido desbaneado.**",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Admin", callback_data="admin_panel")]])
    )
    logger.info(f"✅ Usuario {user['telegram_id']} desbaneado")

    # Notificar al usuario desbaneado
    try:
        await context.bot.send_message(
            chat_id=user["telegram_id"],
            text="✅ **Has sido desbaneado de LinkForge.**\n\n"
                 "Ya puedes usar el bot nuevamente.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Ir al Panel Principal", callback_data="volver_menu")]]),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error notificando al usuario desbaneado: {e}")

    return ConversationHandler.END

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra lista de usuarios."""
    query = update.callback_query
    await query.answer()
    logger.info("📋 list_users: Mostrando lista de usuarios")

    users = get_all_users()

    if not users:
        await query.edit_message_text(
            "📋 No hay usuarios registrados.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Admin", callback_data="admin_panel")]])
        )
        return

    text = "📋 **Lista de usuarios**\n\n"
    for u in users[:20]:
        admin_flag = "👑 " if u["is_admin"] else ""
        banned_flag = "🚫 " if u["is_banned"] else ""
        text += f"{admin_flag}{banned_flag}`{u['telegram_id']}` - {u['username'] or 'Sin nombre'} - {u['reputation']} pts\n"

    if len(users) > 20:
        text += f"\n... y {len(users) - 20} más."

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Admin", callback_data="admin_panel")]]),
        parse_mode='Markdown'
    )

async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la conversación."""
    await update.message.reply_text(
        "❌ Operación cancelada.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Admin", callback_data="admin_panel")]])
    )
    return ConversationHandler.END
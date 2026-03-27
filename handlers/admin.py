import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.database import (
    get_user, get_user_by_username, add_reputation, set_reputation,
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
    
    if user_id != ADMIN_ID and not is_admin(user_id):
        await update.message.reply_text("⛔ No tienes permisos de administrador.")
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
        [InlineKeyboardButton("🏠 Volver al inicio", callback_data="back_to_start")]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def add_reputation_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso para añadir reputación."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔍 **Ingresa el ID o username del usuario:**")
    return WAITING_USER_ID

async def add_reputation_get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obtiene el usuario y pide la cantidad."""
    user_input = update.message.text.strip()
    
    # Buscar por ID o username
    if user_input.isdigit():
        user = get_user(int(user_input))
    else:
        user = get_user_by_username(user_input)
    
    if not user:
        await update.message.reply_text("❌ Usuario no encontrado. Intenta de nuevo.")
        return WAITING_USER_ID
    
    context.user_data['target_user'] = user
    await update.message.reply_text("💰 **Ingresa la cantidad de reputación a añadir:**")
    return WAITING_REPUTATION

async def add_reputation_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Añade la reputación al usuario."""
    try:
        amount = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Ingresa un número válido.")
        return WAITING_REPUTATION
    
    target_user = context.user_data['target_user']
    add_reputation(target_user["telegram_id"], amount)
    
    await update.message.reply_text(
        f"✅ Se añadieron **{amount} puntos** a @{target_user['username'] or target_user['telegram_id']}\n"
        f"Nueva reputación: {target_user['reputation'] + amount}"
    )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la conversación."""
    await update.message.reply_text("Operación cancelada.")
    return ConversationHandler.END
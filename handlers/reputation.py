import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_top_users, get_user, add_reputation, record_click

logger = logging.getLogger(__name__)

async def earn_reputation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los top 5 links para ganar reputación."""
    user_id = update.effective_user.id
    
    # Obtener top 5 usuarios (excluyendo al propio usuario)
    top_users = get_top_users(limit=10)
    available_users = [u for u in top_users if u["telegram_id"] != user_id][:5]
    
    if not available_users:
        await update.message.reply_text(
            "🎁 **No hay usuarios disponibles**\n\n"
            "Vuelve más tarde cuando haya más usuarios registrados.",
            parse_mode='Markdown'
        )
        return
    
    # Guardar en contexto los links disponibles para esta sesión
    context.user_data['available_links'] = [(u["telegram_id"], u["username"]) for u in available_users]
    
    text = "🎁 **Gana reputación** 🎁\n\n"
    text += "Haz clic en los links de otros usuarios para ganar +5 reputación cada uno.\n\n"
    text += "**Links disponibles:**\n"
    
    keyboard = []
    for i, user in enumerate(available_users, 1):
        username = user["username"] or f"Usuario_{user['telegram_id']}"
        text += f"{i}. @{username} - {user['reputation']} pts\n"
        keyboard.append([InlineKeyboardButton(
            f"🔗 Visitar link de @{username}",
            callback_data=f"visit_link_{user['telegram_id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔄 Más links", callback_data="more_links")])
    keyboard.append([InlineKeyboardButton("🏠 Volver al inicio", callback_data="back_to_start")])
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def visit_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registra la visita a un link y da reputación."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    target_user_id = int(query.data.split("_")[2])
    
    # Verificar que no se visite a sí mismo
    if user_id == target_user_id:
        await query.edit_message_text("❌ No puedes visitar tu propio link.")
        return
    
    # Obtener información del usuario objetivo
    target_user = get_user(target_user_id)
    if not target_user:
        await query.edit_message_text("❌ Usuario no encontrado.")
        return
    
    # Registrar el clic y dar reputación
    # Nota: necesitamos obtener el link_id. Por ahora usamos un valor temporal
    # En tu database.py, record_click necesita link_id
    # Por simplicidad, por ahora solo damos reputación sin registrar el clic en tabla clicks
    add_reputation(user_id, 5)
    
    # Opcional: registrar el clic (requiere link_id)
    # record_click(user_id, link_id, 5)
    
    username = target_user["username"] or f"Usuario_{target_user_id}"
    
    # Eliminar este link de los disponibles
    if 'available_links' in context.user_data:
        context.user_data['available_links'] = [
            (uid, uname) for uid, uname in context.user_data['available_links']
            if uid != target_user_id
        ]
    
    await query.edit_message_text(
        f"✅ **+5 reputación!**\n\n"
        f"Has visitado el link de @{username}\n\n"
        f"Usa /reputation para ver más links disponibles.",
        parse_mode='Markdown'
    )

async def more_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra más links disponibles."""
    query = update.callback_query
    await query.answer()
    await earn_reputation(update, context)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import logging

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensaje de bienvenida y panel principal"""
    user = update.effective_user
    telegram_id = user.id
    username = user.username or user.first_name or "Usuario"
    
    text = (
        f"🚀 **¡Bienvenido a LinkForge, {username}!**\n\n"
        f"📌 **¿Qué es LinkForge?**\n"
        f"Es un bot que te ayuda a promocionar tus links.\n\n"
        f"💎 **¿Cómo funciona?**\n"
        f"1️⃣ Registra tu link con /register [URL]\n"
        f"2️⃣ Aparecerás en el ranking\n"
        f"3️⃣ Cada vez que alguien haga clic en tu link, ¡ganas puntos!\n"
        f"4️⃣ Cuantos más puntos tengas, más arriba estarás en el ranking\n\n"
        f"🏆 **Gana puntos extra:**\n"
        f"• Invita amigos: /referral\n"
        f"• Compra puntos: /recharge\n\n"
        f"📊 **Ver ranking:** /ranking\n\n"
        f"⚡ *Cada clic en tu link = 1 punto*"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 Ver Ranking", callback_data="show_ranking")],
        [InlineKeyboardButton("🔗 Registrar Link", callback_data="register_link")],
        [InlineKeyboardButton("👥 Invitar Amigos", callback_data="referral")],
        [InlineKeyboardButton("💎 Comprar Puntos", callback_data="recharge")]
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
    
    if data == "show_ranking":
        await query.edit_message_text("📊 Función de ranking en desarrollo. Usa /ranking")
    elif data == "register_link":
        await query.edit_message_text("🔗 Envíame tu link con /register [URL]")
    elif data == "referral":
        await query.edit_message_text("👥 Función de referidos en desarrollo. Usa /referral")
    elif data == "recharge":
        await query.edit_message_text("💎 Función de recarga en desarrollo. Usa /recharge")
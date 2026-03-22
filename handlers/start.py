from telegram import Update
from telegram.ext import ContextTypes

from services.user_service import get_or_create_user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # crear o obtener usuario
    db_user = get_or_create_user(
        user_id=user.id,
        username=user.username
    )

    await update.message.reply_text(
        f"🚀 Bienvenido a LinkForge\n\n"
        f"👤 Usuario: @{db_user['username'] or 'sin_username'}\n"
        f"💰 Balance: {db_user['balance']} puntos\n\n"
        f"Gana recompensas usando enlaces de referidos."
    )
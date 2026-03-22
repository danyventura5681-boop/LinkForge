from telegram import Update
from telegram.ext import ContextTypes

from services.referral_service import create_user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    user = update.effective_user
    user_id = user.id
    username = user.username

    referrer_id = None

    # 🔗 Detectar código referral
    if context.args:
        try:
            referrer_id = int(context.args[0])

            # evitar auto-referido
            if referrer_id == user_id:
                referrer_id = None

        except ValueError:
            referrer_id = None

    # ✅ Crear usuario mediante servicio
    created = create_user(
        telegram_id=user_id,
        username=username,
        referrer_id=referrer_id
    )

    if created:
        text = "🎉 Usuario registrado correctamente!"
    else:
        text = "👋 Bienvenido de nuevo!"

    await update.message.reply_text(
        f"{text}\n\n"
        f"🆔 Tu ID: {user_id}"
    )
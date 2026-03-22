from telegram import Update
from telegram.ext import ContextTypes
from services.referral_service import create_user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    referrer_id = None

    # detectar código referral
    if context.args:
        try:
            referrer_id = int(context.args[0])

            # evitar auto-referido
            if referrer_id == user_id:
                referrer_id = None

        except ValueError:
            referrer_id = None

    created = create_user(user_id, referrer_id)

    if created:
        text = "🎉 Usuario registrado correctamente!"
    else:
        text = "👋 Bienvenido de nuevo!"

    await update.message.reply_text(
        f"{text}\n\n"
        f"🆔 Tu ID: {user_id}"
    )
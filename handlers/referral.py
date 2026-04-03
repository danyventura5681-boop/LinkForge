import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_user, add_reputation, create_user

logger = logging.getLogger(__name__)

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el enlace de referido del usuario."""
    user = update.effective_user
    telegram_id = user.id
    username = user.username or user.first_name or "Usuario"
    logger.info(f"👥 referral: Usuario {username} solicitó su enlace de referido")

    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{telegram_id}"

    text = (
        f"👥 **Invita amigos y gana reputación** 👥\n\n"
        f"🔗 **Tu enlace de referido:**\n"
        f"`{referral_link}`\n\n"
        f"🎁 **Recompensa:**\n"
        f"Por cada amigo que se una usando tu enlace, ¡ganas **+50 reputación**!\n\n"
        f"📤 Comparte el enlace con tus amigos y empieza a ganar puntos extras.\n\n"
        f"💡 *Consejo: Comparte el enlace en tus redes sociales para más recompensas.*"
    )

    keyboard = [
        [InlineKeyboardButton("📤 Compartir enlace", url=f"https://t.me/share/url?url={referral_link}&text=¡Únete a LinkForge! 🚀 Gana reputación mientras ayudas a otros!")],
        [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
    ]

    # Si viene de un callback (botón), usar query.edit_message_text
    if update.callback_query:
        query = update.callback_query
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        # Si viene de un comando /referral
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    logger.info(f"👥 Enlace de referido mostrado para {username}")

async def process_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa cuando un usuario llega por enlace de referido."""
    args = context.args
    logger.info(f"🔗 process_referral: Args recibidos: {args}")

    # ✅ Validar que exista el argumento de referido
    if not args or not args[0].startswith('ref_'):
        logger.info("⚠️ No hay referido en los args")
        return

    try:
        referrer_id = int(args[0][4:])
    except (ValueError, IndexError) as e:
        logger.error(f"❌ Error parseando referrer_id: {e}")
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Usuario"
    
    logger.info(f"🔗 process_referral: Usuario {user_id} (@{username}) vino por enlace de referente {referrer_id}")

    # ✅ NO permitir auto-referidos
    if user_id == referrer_id:
        logger.warning(f"⚠️ Usuario {user_id} intentó referirse a sí mismo")
        try:
            await update.message.reply_text(
                "❌ No puedes usar tu propio enlace de referido.\n\n"
                "🔗 Comparte tu enlace con otros usuarios para ganar reputación.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
            )
        except Exception as e:
            logger.error(f"❌ Error enviando mensaje de auto-referido: {e}")
        return

    # ✅ Verificar que el usuario no sea duplicado en la BD
    existing_user = get_user(user_id)
    if existing_user:
        logger.info(f"⚠️ Usuario {user_id} ya existe en BD, verificando si tiene referente...")
        
        # ✅ Si ya existe pero NO tiene referente, asignarle ahora
        if existing_user.referred_by is None:
            logger.info(f"🔗 Asignando referente {referrer_id} al usuario existente {user_id}")
            # Necesitamos actualizar la BD
            from database.database import SessionLocal
            session = SessionLocal()
            try:
                user_obj = session.query(get_user.__self__).filter_by(telegram_id=user_id).first()
                if user_obj:
                    user_obj.referred_by = referrer_id
                    session.commit()
                    logger.info(f"✅ Referente asignado a usuario existente {user_id}")
                    
                    # Dar reputación al referente
                    add_reputation(referrer_id, 50)
                    logger.info(f"✅ +50 reputación dado a referente {referrer_id}")
                    
                    # Notificar
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=f"🎉 **¡Un usuario existente confirmó tu referencia!**\n\n"
                                 f"👤 Usuario: @{username}\n"
                                 f"🎁 +50 reputación añadida a tu cuenta.\n\n"
                                 f"📊 Usa el botón 'Invitar Amigos' para ver tu enlace personal.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Ver panel", callback_data="volver_menu")]]),
                            parse_mode='Markdown'
                        )
                        logger.info(f"✅ Notificación enviada al referente {referrer_id}")
                    except Exception as e:
                        logger.error(f"❌ Error notificando al referente {referrer_id}: {e}")
            except Exception as e:
                logger.error(f"❌ Error asignando referente: {e}")
            finally:
                session.close()
        else:
            logger.info(f"⚠️ Usuario {user_id} ya tiene referente {existing_user.referred_by}, no se da recompensa")
        return

    # ✅ Usuario NUEVO: crear con referido
    logger.info(f"👤 Usuario {user_id} es nuevo, creando con referido {referrer_id}")
    create_user(user_id, username, referred_by=referrer_id)
    logger.info(f"✅ Usuario {user_id} creado con referido {referrer_id}, +50 rep para referente")

    # ✅ Notificar al referente
    try:
        await context.bot.send_message(
            chat_id=referrer_id,
            text=f"🎉 **¡Alguien se unió por tu enlace!**\n\n"
                 f"👤 Nuevo usuario: @{username}\n"
                 f"🎁 +50 reputación añadida a tu cuenta.\n\n"
                 f"📊 Usa el botón 'Invitar Amigos' para ver tu enlace personal.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Ver panel", callback_data="volver_menu")]]),
            parse_mode='Markdown'
        )
        logger.info(f"✅ Notificación enviada al referente {referrer_id}")
    except Exception as e:
        logger.error(f"❌ Error notificando al referente {referrer_id}: {e}")
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import (
    get_user, add_reputation, create_user, SessionLocal, User, get_referrals_count
)

logger = logging.getLogger(__name__)

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el enlace de referido del usuario y estadísticas."""
    user = update.effective_user
    telegram_id = user.id
    username = user.username or user.first_name or "Usuario"
    
    logger.info(f"👥 referral: Usuario {username} solicitó su enlace de referido")
    
    # Obtener estadísticas del usuario
    db_user = get_user(telegram_id)
    referrals_count = get_referrals_count(telegram_id) if db_user else 0
    total_earned = referrals_count * 50
    
    # Generar link de referido
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{telegram_id}"
    
    # Texto con estadísticas
    text = (
        f"👥 **Invita amigos y gana reputación** 👥\n\n"
        f"🔗 **Tu enlace de referido:**\n"
        f"`{referral_link}`\n\n"
        f"📊 **Tus estadísticas:**\n"
        f"• Amigos invitados: **{referrals_count}**\n"
        f"• Reputación ganada: **+{total_earned}**\n\n"
        f"🎁 **Recompensa:**\n"
        f"Por cada amigo que se una usando tu enlace, ¡ganas **+50 reputación**!\n\n"
        f"📤 Comparte el enlace con tus amigos y empieza a ganar puntos extras.\n\n"
        f"💡 *Consejo: Comparte el enlace en tus redes sociales para más recompensas.*"
    )
    
    # Teclado con opciones
    keyboard = [
        [InlineKeyboardButton("📤 Compartir enlace", url=f"https://t.me/share/url?url={referral_link}&text=¡Únete a LinkForge! 🚀 Gana reputación mientras ayudas a otros!")],
        [InlineKeyboardButton("🔄 Ver mis referidos", callback_data="view_referrals")],
        [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
    ]
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
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
    
    logger.info(f"👥 Enlace de referido mostrado para {username} (invitados: {referrals_count})")

async def view_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la lista de usuarios que se unieron por el enlace del usuario."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name or "Usuario"
    
    logger.info(f"👥 view_referrals: Usuario {username} solicitó ver sus referidos")
    
    session = SessionLocal()
    try:
        # Obtener todos los referidos
        referrals = session.query(User).filter_by(referred_by=user_id).order_by(User.created_at.desc()).all()
        
        if not referrals:
            text = (
                f"👥 **Tus referidos**\n\n"
                f"📊 Aún no tienes referidos.\n\n"
                f"🔗 Comparte tu enlace con amigos para ganar +50 reputación por cada uno.\n\n"
                f"💡 ¡Comparte en redes sociales y grupos para más alcance!"
            )
            keyboard = [[InlineKeyboardButton("◀️ Volver", callback_data="referral")]]
        else:
            text = f"👥 **Tus referidos**\n\n📊 **Total:** {len(referrals)} amigos invitados\n\n"
            
            for i, ref in enumerate(referrals[:10], 1):  # Mostrar máximo 10
                ref_username = ref.username or f"Usuario_{ref.telegram_id}"
                joined_date = ref.created_at.strftime("%d/%m/%Y") if ref.created_at else "Fecha desconocida"
                text += f"{i}. @{ref_username}\n   📅 {joined_date}\n\n"
            
            if len(referrals) > 10:
                text += f"\n📊 Y {len(referrals) - 10} referidos más..."
            
            keyboard = [
                [InlineKeyboardButton("📤 Compartir mi enlace", callback_data="referral")],
                [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
            ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"❌ Error en view_referrals: {e}")
        await query.edit_message_text(
            "❌ Error al cargar la lista de referidos. Intenta de nuevo más tarde.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="referral")]])
        )
    finally:
        session.close()

async def process_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa cuando un usuario llega por enlace de referido."""
    args = context.args
    logger.info(f"🔗 process_referral: Args recibidos: {args}")
    
    # Verificar si hay argumentos y si es un enlace de referido
    if not args or not args[0].startswith('ref_'):
        logger.info("⚠️ No hay referido en los args")
        return
    
    # Extraer ID del referente
    try:
        referrer_id = int(args[0][4:])
    except (ValueError, IndexError) as e:
        logger.error(f"❌ Error parseando referrer_id: {e}")
        return
    
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "Usuario"
    
    logger.info(f"🔗 process_referral: Usuario {user_id} (@{username}) vino por enlace de referente {referrer_id}")
    
    # NO permitir auto-referidos
    if user_id == referrer_id:
        logger.warning(f"⚠️ Usuario {user_id} intentó referirse a sí mismo")
        try:
            # Solo enviar mensaje si el usuario ya existe (para no duplicar)
            existing = get_user(user_id)
            if existing:
                await update.message.reply_text(
                    "❌ No puedes usar tu propio enlace de referido.\n\n"
                    "🔗 Comparte tu enlace con otros usuarios para ganar reputación.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
                )
        except Exception as e:
            logger.error(f"❌ Error enviando mensaje de auto-referido: {e}")
        return
    
    # ✅ VERIFICAR SI EL USUARIO YA EXISTE
    existing_user = get_user(user_id)
    
    if existing_user:
        logger.info(f"⚠️ Usuario {user_id} ya existe en BD")
        
        # Si ya existe pero NO tiene referente, asignarle ahora
        if existing_user.referred_by is None:
            logger.info(f"🔗 Asignando referente {referrer_id} al usuario existente {user_id}")
            
            session = SessionLocal()
            try:
                user_obj = session.query(User).filter_by(telegram_id=user_id).first()
                if user_obj:
                    user_obj.referred_by = referrer_id
                    session.commit()
                    logger.info(f"✅ Referente asignado a usuario existente {user_id}")
                    
                    # Dar reputación al referente
                    add_reputation(referrer_id, 50)
                    logger.info(f"✅ +50 reputación dado a referente {referrer_id}")
                    
                    # Notificar al referente
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=f"🎉 **¡Un usuario confirmó tu referencia!**\n\n"
                                 f"👤 Usuario: @{username}\n"
                                 f"🎁 +50 reputación añadida a tu cuenta.\n\n"
                                 f"📊 Usa el botón 'Invitar Amigos' para ver tu enlace personal.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Ver panel", callback_data="volver_menu")]]),
                            parse_mode='Markdown'
                        )
                        logger.info(f"✅ Notificación enviada al referente {referrer_id}")
                    except Exception as e:
                        logger.error(f"❌ Error notificando al referente {referrer_id}: {e}")
                    
                    # Mensaje de confirmación al usuario
                    try:
                        await update.message.reply_text(
                            "✅ **¡Referido confirmado!**\n\n"
                            f"🎉 Gracias por unirte con el enlace de @{username}\n\n"
                            "🔗 Ya puedes registrar tu link y comenzar a ganar reputación.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Ir al Menú", callback_data="volver_menu")]])
                        )
                    except Exception as e:
                        logger.error(f"❌ Error enviando mensaje de confirmación: {e}")
                        
            except Exception as e:
                logger.error(f"❌ Error asignando referente: {e}")
            finally:
                session.close()
        else:
            logger.info(f"⚠️ Usuario {user_id} ya tiene referente {existing_user.referred_by}")
        return
    
    # ✅ USUARIO NUEVO: CREAR CON REFERIDO
    logger.info(f"👤 Usuario {user_id} es nuevo, creando con referido {referrer_id}")
    user_created = create_user(user_id, username, referred_by=referrer_id)
    
    if user_created:
        logger.info(f"✅ Usuario {user_id} creado exitosamente con referido {referrer_id}")
        
        # ✅ NOTIFICAR AL REFERENTE
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=f"🎉 **¡Alguien se unió por tu enlace!**\n\n"
                     f"👤 Nuevo usuario: @{username}\n"
                     f"🎁 +50 reputación añadida a tu cuenta.\n\n"
                     f"📊 Usa el botón 'Invitar Amigos' para ver tu enlace personal.\n"
                     f"👥 Total de referidos: {get_referrals_count(referrer_id)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Ver panel", callback_data="volver_menu")]]),
                parse_mode='Markdown'
            )
            logger.info(f"✅ Notificación enviada al referente {referrer_id}")
        except Exception as e:
            logger.error(f"❌ Error notificando al referente {referrer_id}: {e}")
    else:
        logger.error(f"❌ Error creando usuario {user_id} con referido {referrer_id}")

async def referral_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones del sistema de referidos."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "view_referrals":
        await view_referrals(update, context)
    elif data == "referral":
        await referral(update, context)
    else:
        logger.warning(f"⚠️ Botón de referidos no reconocido: {data}")
        await referral(update, context)
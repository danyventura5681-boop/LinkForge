import logging
import hashlib
import uuid
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.database import (
    get_top_users, get_user, add_reputation, get_user_links, record_click,
    get_referrals_count
)

logger = logging.getLogger(__name__)

# ============================================
# SISTEMA DE TEMPORIZADOR
# ============================================

# Diccionario para almacenar temporizadores activos
# {user_id: {"link_id": int, "target_user_id": int, "username": str, "timestamp": datetime, "message_id": int, "chat_id": int}}
PENDING_VERIFICATIONS = {}

# Constantes
MIN_WAIT_SECONDS = 30      # 30 segundos mínimo de espera
MAX_WAIT_SECONDS = 300     # 5 minutos máximo para verificar
DAILY_LIMIT = 10           # Máximo 10 reputaciones por día

def get_user_daily_verifications(user_id: int) -> int:
    """Obtiene cuántas verificaciones ha hecho el usuario hoy."""
    from database.database import SessionLocal, Click
    session = SessionLocal()
    try:
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        count = session.query(Click).filter(
            Click.user_id == user_id,
            Click.created_at >= today
        ).count()
        return count
    except Exception as e:
        logger.error(f"Error getting daily verifications: {e}")
        return 0
    finally:
        session.close()

async def send_timer_message(update: Update, context: ContextTypes.DEFAULT_TYPE, link_info: dict, wait_seconds: int):
    """Envía mensaje con contador regresivo."""
    user_id = update.effective_user.id
    username = link_info['username']
    link_url = link_info['url']
    link_id = link_info['link_id']
    target_user_id = link_info['user_id']
    
    # Crear mensaje inicial
    text = (
        f"🔗 **Visita este link:**\n"
        f"`{link_url}`\n\n"
        f"👤 **Dueño:** @{username}\n"
        f"⭐ **Reputación a ganar:** +5\n\n"
        f"⏰ **Debes esperar {wait_seconds} segundos** para confirmar que viste el contenido.\n\n"
        f"✅ El botón aparecerá automáticamente cuando termine la espera.\n\n"
        f"⏱️ **Tiempo restante:** {wait_seconds} segundos..."
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Cancelar", callback_data="cancel_verification")]]
    
    if update.callback_query:
        query = update.callback_query
        msg = await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        msg = await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    # Guardar información del mensaje para poder editarlo después
    return msg

async def update_timer_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, remaining: int, link_url: str, username: str):
    """Actualiza el mensaje con el tiempo restante."""
    text = (
        f"🔗 **Visita este link:**\n"
        f"`{link_url}`\n\n"
        f"👤 **Dueño:** @{username}\n"
        f"⭐ **Reputación a ganar:** +5\n\n"
        f"⏰ **Debes esperar {remaining} segundos** para confirmar que viste el contenido.\n\n"
        f"✅ El botón aparecerá automáticamente cuando termine la espera.\n\n"
        f"⏱️ **Tiempo restante:** {remaining} segundos..."
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Cancelar", callback_data="cancel_verification")]]
    
    try:
        await context.bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error updating timer: {e}")

async def finish_verification(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Muestra el botón de confirmación después de la espera."""
    if user_id not in PENDING_VERIFICATIONS:
        return
    
    pending = PENDING_VERIFICATIONS[user_id]
    link_url = pending['url']
    username = pending['username']
    chat_id = pending['chat_id']
    message_id = pending['message_id']
    
    text = (
        f"🔗 **Link visitado:**\n"
        f"`{link_url}`\n\n"
        f"👤 **Dueño:** @{username}\n"
        f"⭐ **Reputación a ganar:** +5\n\n"
        f"✅ **¿Ya viste el contenido?**\n"
        f"Presiona el botón para recibir tu reputación.\n\n"
        f"⚠️ Tienes {MAX_WAIT_SECONDS // 60} minutos para confirmar antes de que expire."
    )
    
    keyboard = [[
        InlineKeyboardButton("✅ Sí, ya lo vi", callback_data="confirm_verification"),
        InlineKeyboardButton("◀️ Cancelar", callback_data="cancel_verification")
    ]]
    
    try:
        await context.bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error showing confirmation button: {e}")

async def start_timer(update: Update, context: ContextTypes.DEFAULT_TYPE, link_info: dict):
    """Inicia el temporizador para un link."""
    user_id = update.effective_user.id
    
    # Verificar límite diario
    daily_count = get_user_daily_verifications(user_id)
    if daily_count >= DAILY_LIMIT:
        text = f"⚠️ **Límite diario alcanzado**\n\nHas usado {daily_count}/{DAILY_LIMIT} verificaciones hoy.\n\nVuelve mañana para ganar más reputación."
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]]
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return False
    
    # Enviar mensaje con temporizador
    msg = await send_timer_message(update, context, link_info, MIN_WAIT_SECONDS)
    
    # Guardar en pending
    PENDING_VERIFICATIONS[user_id] = {
        'link_id': link_info['link_id'],
        'user_id': link_info['user_id'],
        'target_user_id': link_info['user_id'],
        'username': link_info['username'],
        'url': link_info['url'],
        'chat_id': msg.chat_id,
        'message_id': msg.message_id,
        'timestamp': datetime.utcnow(),
        'confirmed': False
    }
    
    # Ejecutar contador regresivo
    for remaining in range(MIN_WAIT_SECONDS - 1, 0, -1):
        await asyncio.sleep(1)
        # Verificar si fue cancelado
        if user_id not in PENDING_VERIFICATIONS:
            return
        if remaining % 5 == 0 or remaining <= 10:  # Actualizar cada 5 segundos o en los últimos 10
            await update_timer_message(context, msg.chat_id, msg.message_id, remaining, link_info['url'], link_info['username'])
    
    # Verificar si sigue pendiente
    if user_id in PENDING_VERIFICATIONS:
        await finish_verification(update, context, user_id)
    
    return True

# ============================================
# FUNCIONES PRINCIPALES
# ============================================

async def earn_reputation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los top 5 links para ganar reputación."""
    user_id = update.effective_user.id
    logger.info(f"🎁 earn_reputation: Usuario {user_id} solicitó ganar reputación")
    
    # Verificar límite diario
    daily_count = get_user_daily_verifications(user_id)
    daily_text = f"📊 **Usados hoy:** {daily_count}/{DAILY_LIMIT}\n\n" if daily_count > 0 else ""

    top_users = get_top_users(limit=10)
    available_users = top_users[:5]

    if not available_users:
        text = (
            f"🎁 **No hay usuarios disponibles**\n\n"
            f"{daily_text}"
            f"Vuelve más tarde cuando haya más usuarios registrados.\n\n"
            f"💡 Consejo: Invita amigos con el botón 'Invitar Amigos' para aumentar la comunidad."
        )
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]]

        if update.callback_query:
            query = update.callback_query
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
        return

    context.user_data['link_map'] = {}
    bot_username = (await context.bot.get_me()).username

    text = f"🎁 **Gana +5 reputación por cada link** 🎁\n\n{daily_text}"

    keyboard = []
    link_counter = 1

    for i, user in enumerate(available_users, 1):
        username = user.username or f"Usuario_{user.telegram_id}"
        
        # No mostrar el propio usuario
        if user.telegram_id == user_id:
            continue
            
        user_links = get_user_links(user.telegram_id)

        if user_links:
            link = user_links[0]
            link_url = link.url
            link_id = link.id

            callback_id = f"link_{link_counter}"
            context.user_data['link_map'][callback_id] = {
                'link_id': link_id,
                'user_id': user.telegram_id,
                'url': link_url,
                'username': username,
                'reputation': user.reputation
            }

            keyboard.append([
                InlineKeyboardButton(
                    f"🔗 @{username} ({user.reputation} pts)",
                    callback_data=callback_id
                )
            ])
            link_counter += 1

    if not keyboard:
        text = (
            f"🎁 **No hay links disponibles**\n\n"
            f"{daily_text}"
            f"Todos los usuarios disponibles son tú mismo o no tienen links activos.\n\n"
            f"💡 Vuelve más tarde o invita nuevos usuarios."
        )
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]]

    keyboard.append([InlineKeyboardButton("🔄 Más links", callback_data="more_links")])
    keyboard.append([InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")])

    if update.callback_query:
        query = update.callback_query
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
    logger.info(f"🎁 Mostrados {len(keyboard)} usuarios disponibles")

async def visit_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de visita con temporizador."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    callback_id = query.data

    logger.info(f"🔗 visit_link: Usuario {user_id} seleccionó link {callback_id}")

    link_map = context.user_data.get('link_map', {})

    if callback_id not in link_map:
        await query.edit_message_text(
            "❌ Link no encontrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]])
        )
        return

    link_info = link_map[callback_id]
    
    # Verificar que no sea su propio link
    if link_info['user_id'] == user_id:
        await query.edit_message_text(
            "❌ No puedes visitar tu propio link.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]])
        )
        return
    
    # Verificar límite diario
    daily_count = get_user_daily_verifications(user_id)
    if daily_count >= DAILY_LIMIT:
        await query.edit_message_text(
            f"⚠️ **Límite diario alcanzado**\n\nHas usado {daily_count}/{DAILY_LIMIT} verificaciones hoy.\n\nVuelve mañana para ganar más reputación.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]]),
            parse_mode='Markdown'
        )
        return
    
    # Iniciar temporizador
    await start_timer(update, context, link_info)

async def confirm_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma la visita y otorga reputación."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Verificar que haya una verificación pendiente
    if user_id not in PENDING_VERIFICATIONS:
        await query.edit_message_text(
            "❌ No hay verificación pendiente.\n\nUsa 'Ganar Reputación' para comenzar.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]])
        )
        return
    
    pending = PENDING_VERIFICATIONS[user_id]
    
    # Verificar expiración (5 minutos máximo después del temporizador)
    age = (datetime.utcnow() - pending['timestamp']).total_seconds()
    if age > MAX_WAIT_SECONDS:
        del PENDING_VERIFICATIONS[user_id]
        await query.edit_message_text(
            "⏰ **Tiempo expirado**\n\nDebes confirmar dentro de los 5 minutos después de ver el contenido.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Intentar de nuevo", callback_data="earn_reputation")]])
        )
        return
    
    # Verificar que no sea su propio link
    if pending['target_user_id'] == user_id:
        del PENDING_VERIFICATIONS[user_id]
        await query.edit_message_text(
            "❌ No puedes verificar tu propio link.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]])
        )
        return
    
    # Verificar límite diario nuevamente
    daily_count = get_user_daily_verifications(user_id)
    if daily_count >= DAILY_LIMIT:
        del PENDING_VERIFICATIONS[user_id]
        await query.edit_message_text(
            f"⚠️ **Límite diario alcanzado**\n\nHas usado {daily_count}/{DAILY_LIMIT} verificaciones hoy.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]]),
            parse_mode='Markdown'
        )
        return
    
    # Registrar el clic y otorgar reputación
    record_click(user_id, pending['link_id'], reputation_earned=5)
    
    logger.info(f"✅ +5 reputación para usuario {user_id} por visitar link de {pending['target_user_id']}")
    
    # Limpiar pending
    del PENDING_VERIFICATIONS[user_id]
    
    await query.edit_message_text(
        f"✅ **¡+5 reputación ganados!**\n\n"
        f"📊 Has visitado el link de **@{pending['username']}**\n\n"
        f"🎁 Usados hoy: {daily_count + 1}/{DAILY_LIMIT}\n\n"
        f"💡 Sigue visitando más links para ganar puntos.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎁 Ver más links", callback_data="earn_reputation")],
            [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
        ]),
        parse_mode='Markdown'
    )

async def cancel_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la verificación pendiente."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id in PENDING_VERIFICATIONS:
        del PENDING_VERIFICATIONS[user_id]
        logger.info(f"❌ Usuario {user_id} canceló la verificación")
    
    await query.edit_message_text(
        "❌ Verificación cancelada.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]])
    )

async def more_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra más links disponibles."""
    query = update.callback_query
    logger.info("🔄 more_links: Mostrando más links")
    await query.answer()
    await earn_reputation(update, context)

# ============================================
# INSTAGRAM TASK
# ============================================

WAITING_INSTAGRAM_USERNAME = 1

async def instagram_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la tarea de seguir Instagram (+100 reputación)."""
    user_id = update.effective_user.id
    logger.info(f"📸 instagram_task: Usuario {user_id} solicitó tarea Instagram")

    text = (
        "📸 **Síguenos en Instagram y gana +100 reputación**\n\n"
        "🔗 Cuenta: @dany_vg56\n\n"
        "📋 **Instrucciones:**\n"
        "1️⃣ Sigue nuestra cuenta en Instagram\n"
        "2️⃣ Haz clic en '✅ Confirmar'\n"
        "3️⃣ Ingresa tu usuario de Instagram\n"
        "4️⃣ El admin confirma y recibes +100 pts\n\n"
        "⏱️ Esto puede tomar hasta 24 horas."
    )

    keyboard = [
        [InlineKeyboardButton("📸 Ir a Instagram", url="https://www.instagram.com/dany_vg56?igsh=M2I4NmRnZjZvdXhr")],
        [InlineKeyboardButton("✅ Confirmar seguimiento", callback_data="confirm_instagram")],
        [InlineKeyboardButton("◀️ Volver", callback_data="volver_menu")]
    ]

    if update.callback_query:
        query = update.callback_query
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

async def confirm_instagram_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de confirmación de Instagram."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    logger.info(f"📸 confirm_instagram_start: Usuario {user_id} iniciando confirmación")

    await query.edit_message_text(
        "📸 **Ingresa tu usuario de Instagram:**\n\n"
        "💡 Sin el @ (ejemplo: dany_vg56)",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="earn_reputation")]])
    )

    return WAITING_INSTAGRAM_USERNAME

async def confirm_instagram_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el username de Instagram y notifica al admin."""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Sin username"
    instagram_user = update.message.text.strip()

    logger.info(f"📸 confirm_instagram_process: Usuario {user_id} ingresó @{instagram_user}")

    if not instagram_user or len(instagram_user) < 3:
        await update.message.reply_text(
            "❌ Usuario inválido. Intenta de nuevo.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="earn_reputation")]])
        )
        return WAITING_INSTAGRAM_USERNAME

    ADMIN_ID = 5057900537
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📸 **Nueva solicitud Instagram**\n\n"
                 f"👤 Usuario: @{username} (ID: {user_id})\n"
                 f"📸 Instagram: @{instagram_user}\n\n"
                 f"✅ Verifica y confirma el seguimiento.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirmar", callback_data=f"confirm_insta_{user_id}_{instagram_user}")],
                [InlineKeyboardButton("❌ Rechazar", callback_data=f"reject_insta_{user_id}")]
            ])
        )
        logger.info(f"✅ Notificación enviada al admin")
    except Exception as e:
        logger.error(f"❌ Error notificando admin: {e}")

    await update.message.reply_text(
        "✅ **Solicitud enviada al administrador**\n\n"
        "⏱️ Confirmaremos tu seguimiento en 24 horas y recibirás +100 reputación.\n\n"
        "💡 Asegúrate de haber seguido la cuenta @dany_vg56",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
    )

    return ConversationHandler.END

# ============================================
# PROMOCIONAR CONTENIDO (VIP)
# ============================================

async def promotion_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menú para promocionar contenido (VIP required)."""
    user_id = update.effective_user.id
    user = get_user(user_id)

    logger.info(f"🎬 promotion_menu: Usuario {user_id} accedió a promocionar")

    if not user or user.vip_level < 1:
        text = (
            "🎬 **Promocionar Contenido** (VIP Required)\n\n"
            "❌ Debes ser VIP para usar esta función.\n\n"
            "📊 **Beneficios VIP:**\n"
            "✅ Promociona videos y obtén +2000 visitas\n"
            "✅ +20 reputación por cada vista\n"
            "✅ Prioridad en mostrado\n\n"
            "⭐ Actualiza a VIP ahora y comienza a promocionar."
        )
        keyboard = [
            [InlineKeyboardButton("⭐ Actualizar a VIP", callback_data="vip_info")],
            [InlineKeyboardButton("◀️ Volver", callback_data="volver_menu")]
        ]

        if update.callback_query:
            query = update.callback_query
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
        return

    text = (
        f"🎬 **Promocionar Contenido** ⭐\n\n"
        f"👤 VIP Level: {user.vip_level}\n\n"
        f"📊 **¿Cómo funciona?**\n"
        f"1️⃣ Envía un link de video\n"
        f"2️⃣ Otros usuarios lo verán con +20 pts\n"
        f"3️⃣ Mínimo 1 minuto de visualización\n"
        f"4️⃣ Objetivo: +2000 visitas\n\n"
        f"✅ Tu video será priorizado en la lista."
    )

    keyboard = [
        [InlineKeyboardButton("🎥 Subir video", callback_data="upload_video")],
        [InlineKeyboardButton("📊 Mis videos", callback_data="my_videos")],
        [InlineKeyboardButton("◀️ Volver", callback_data="volver_menu")]
    ]

    if update.callback_query:
        query = update.callback_query
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
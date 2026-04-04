import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import (
    get_top_users, get_user, add_reputation, get_user_links, record_click,
    get_referrals_count, has_user_claimed_instagram
)

logger = logging.getLogger(__name__)

# ============================================
# SISTEMA DE TEMPORIZADOR (OCULTO)
# ============================================

# Diccionario para almacenar temporizadores activos
PENDING_VERIFICATIONS = {}

# Diccionario para evitar doble recompensa
# {user_id: [link_id1, link_id2, ...]}
USER_VISITED_LINKS = {}

# Constantes
MIN_WAIT_SECONDS = 30      # 30 segundos mínimo de espera
MAX_WAIT_SECONDS = 300     # 5 minutos máximo para verificar

def has_user_visited_link(user_id: int, link_id: int) -> bool:
    """Verifica si el usuario ya ha visitado este link antes."""
    if user_id not in USER_VISITED_LINKS:
        return False
    return link_id in USER_VISITED_LINKS[user_id]

def mark_link_as_visited(user_id: int, link_id: int):
    """Marca que el usuario ya visitó este link."""
    if user_id not in USER_VISITED_LINKS:
        USER_VISITED_LINKS[user_id] = []
    if link_id not in USER_VISITED_LINKS[user_id]:
        USER_VISITED_LINKS[user_id].append(link_id)
    logger.info(f"📌 Link {link_id} marcado como visitado por usuario {user_id}")

async def show_link_with_timer(update: Update, context: ContextTypes.DEFAULT_TYPE, link_info: dict):
    """Muestra el link con botón de confirmación que aparece después de 30s."""
    user_id = update.effective_user.id
    username = link_info['username']
    link_url = link_info['url']
    link_id = link_info['link_id']
    target_user_id = link_info['user_id']

    # Mensaje con el link como botón que redirige
    text = (
        f"🔗 **Gana +5 reputación**\n\n"
        f"👤 **Dueño del link:** @{username}\n"
        f"⭐ **Recompensa:** +5 puntos\n\n"
        f"👇 **Haz clic en el botón para visitar el contenido:**"
    )

    # Link como botón inline que redirige (NO callback_data, es url directa)
    keyboard = [
        [InlineKeyboardButton("🔗 VISITAR LINK", url=link_url)],
        [InlineKeyboardButton("◀️ Cancelar", callback_data="cancel_verification")]
    ]

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

    # Guardar información para cuando pase el temporizador
    PENDING_VERIFICATIONS[user_id] = {
        'link_id': link_id,
        'target_user_id': target_user_id,
        'username': username,
        'url': link_url,
        'chat_id': msg.chat_id,
        'message_id': msg.message_id,
        'timestamp': datetime.utcnow(),
        'confirmed': False
    }

    # Iniciar temporizador oculto de 30 segundos
    asyncio.create_task(hidden_timer(context, user_id, msg.chat_id, msg.message_id, link_url, username, link_id, target_user_id))

    logger.info(f"⏰ Temporizador iniciado para usuario {user_id}, botón aparecerá en {MIN_WAIT_SECONDS}s")

async def hidden_timer(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int, message_id: int, link_url: str, username: str, link_id: int, target_user_id: int):
    """Temporizador oculto que muestra el botón de confirmación después de 30s."""
    await asyncio.sleep(MIN_WAIT_SECONDS)

    # Verificar si la verificación sigue activa
    if user_id not in PENDING_VERIFICATIONS:
        return

    pending = PENDING_VERIFICATIONS[user_id]

    # Verificar que el usuario no haya visitado este link antes
    if has_user_visited_link(user_id, link_id):
        # Si ya lo visitó, mostrar mensaje y eliminar pending
        del PENDING_VERIFICATIONS[user_id]
        text = (
            f"⚠️ **Ya has visitado este link anteriormente**\n\n"
            f"👤 **Dueño del link:** @{username}\n\n"
            f"💡 No puedes recibir reputación dos veces por el mismo link.\n\n"
            f"🔗 Prueba con otros links disponibles."
        )
        keyboard = [[InlineKeyboardButton("🎁 Ver más links", callback_data="earn_reputation")]]
        try:
            await context.bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error mostrando mensaje de link ya visitado: {e}")
        return

    # Texto con el botón de confirmar
    text = (
        f"🔗 **Verificación de visita**\n\n"
        f"👤 **Dueño del link:** @{username}\n"
        f"⭐ **Recompensa:** +5 puntos\n\n"
        f"✅ **¿Ya visitaste el link?**\n"
        f"Presiona el botón para recibir tu reputación.\n\n"
        f"⚠️ Tienes 5 minutos para confirmar."
    )

    # Botón Confirmar con callback_data
    keyboard = [
        [InlineKeyboardButton("✅ CONFIRMAR", callback_data=f"confirm_link_{link_id}_{target_user_id}")],
        [InlineKeyboardButton("◀️ Cancelar", callback_data="cancel_verification")]
    ]

    try:
        await context.bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        logger.info(f"✅ Botón CONFIRMAR apareció para usuario {user_id}")
    except Exception as e:
        logger.error(f"Error mostrando botón de confirmación: {e}")

# ============================================
# FUNCIONES PRINCIPALES
# ============================================

async def earn_reputation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra las opciones para ganar reputación."""
    user_id = update.effective_user.id
    logger.info(f"🎁 earn_reputation: Usuario {user_id} solicitó ganar reputación")

    text = (
        f"🎁 **Gana reputación** 🎁\n\n"
        f"📋 **Elige una opción:**\n\n"
        f"🔗 **Visitar Links** - +5 reputación por link\n"
        f"📹 **Ver Videos** - +30 reputación por video (2 min)\n"
        f"📸 **Tarea Instagram** - +100 reputación (única vez)\n\n"
        f"💡 Cada opción tiene su propia recompensa."
    )

    keyboard = [
        [InlineKeyboardButton("🔗 Visitar Links", callback_data="visit_links")],
        [InlineKeyboardButton("📹 Ver Top Videos", callback_data="top_videos")],
        [InlineKeyboardButton("📸 Tarea Instagram", callback_data="instagram_reward")],
        [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
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

async def visit_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los links disponibles para visitar."""
    user_id = update.effective_user.id
    logger.info(f"🔗 visit_links: Usuario {user_id} solicitó visitar links")

    top_users = get_top_users(limit=10)
    available_users = top_users[:5]

    if not available_users:
        text = (
            f"🔗 **No hay links disponibles**\n\n"
            f"Vuelve más tarde cuando haya más usuarios registrados.\n\n"
            f"💡 Consejo: Invita amigos con el botón 'Invitar Amigos' para aumentar la comunidad."
        )
        keyboard = [[InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]]

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

    text = f"🔗 **Gana +5 reputación por cada link** 🎁\n\n"

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

            # Verificar si el usuario ya visitó este link
            if has_user_visited_link(user_id, link_id):
                continue

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
            f"🔗 **No hay links disponibles**\n\n"
            f"Ya has visitado todos los links disponibles.\n\n"
            f"💡 Vuelve más tarde cuando haya nuevos usuarios o links activos."
        )
        keyboard = [[InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]]

    keyboard.append([InlineKeyboardButton("🔄 Más links", callback_data="more_links")])
    keyboard.append([InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")])

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
    logger.info(f"🔗 Mostrados {link_counter - 1} usuarios disponibles")

async def visit_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de visita con temporizador oculto."""
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

    # Verificar si ya visitó este link antes
    if has_user_visited_link(user_id, link_info['link_id']):
        await query.edit_message_text(
            "⚠️ **Ya has visitado este link anteriormente**\n\n"
            "No puedes recibir reputación dos veces por el mismo link.\n\n"
            "🔗 Prueba con otros links disponibles.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎁 Ver más links", callback_data="earn_reputation")]]),
            parse_mode='Markdown'
        )
        return

    # Mostrar link con temporizador oculto
    await show_link_with_timer(update, context, link_info)

async def confirm_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma la visita y otorga reputación."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    # Extraer datos del callback_data
    data_parts = query.data.split('_')
    if len(data_parts) >= 3:
        link_id = int(data_parts[2])
        target_user_id = int(data_parts[3])
    else:
        await query.edit_message_text(
            "❌ Error en la verificación.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]])
        )
        return

    # Verificar que haya una verificación pendiente
    if user_id not in PENDING_VERIFICATIONS:
        await query.edit_message_text(
            "❌ No hay verificación pendiente.\n\nUsa 'Ganar Reputación' para comenzar.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]])
        )
        return

    pending = PENDING_VERIFICATIONS[user_id]

    # Verificar que coincidan los datos
    if pending['link_id'] != link_id or pending['target_user_id'] != target_user_id:
        await query.edit_message_text(
            "❌ Error en la verificación. Intenta de nuevo.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]])
        )
        return

    # Verificar expiración (5 minutos máximo después del temporizador)
    age = (datetime.utcnow() - pending['timestamp']).total_seconds()
    if age > MAX_WAIT_SECONDS + MIN_WAIT_SECONDS:
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

    # Verificar si ya visitó este link antes (doble chequeo)
    if has_user_visited_link(user_id, link_id):
        del PENDING_VERIFICATIONS[user_id]
        await query.edit_message_text(
            "⚠️ **Ya has recibido reputación por este link**\n\n"
            "No puedes recibir reputación dos veces por el mismo link.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎁 Ver más links", callback_data="earn_reputation")]]),
            parse_mode='Markdown'
        )
        return

    # Registrar el clic y otorgar reputación
    record_click(user_id, pending['link_id'], reputation_earned=5)

    # Marcar este link como visitado por este usuario
    mark_link_as_visited(user_id, link_id)

    logger.info(f"✅ +5 reputación para usuario {user_id} por visitar link de {pending['target_user_id']}")

    # Limpiar pending
    del PENDING_VERIFICATIONS[user_id]

    await query.edit_message_text(
        f"✅ **¡+5 reputación ganados!**\n\n"
        f"📊 Has visitado el link de **@{pending['username']}**\n\n"
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
    await visit_links(update, context)

# ============================================
# TAREA INSTAGRAM (CORREGIDA - MODO CONVERSACIÓN)
# ============================================

WAITING_INSTAGRAM_USERNAME = 1

async def instagram_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la tarea de seguir Instagram (+100 reputación)."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    logger.info(f"📸 instagram_task: Usuario {user_id} solicitó tarea Instagram")

    from database import has_user_claimed_instagram

    # Verificar si ya reclamó
    if has_user_claimed_instagram(user_id):
        text = (
            "📸 Tarea de Instagram\n\n"
            "⚠️ Ya has completado esta tarea anteriormente\n\n"
            "✨ Recompensa: +100 reputación\n"
            "📊 Estado: ✅ Completada\n\n"
            "💡 No puedes reclamar la misma tarea dos veces."
        )
        keyboard = [[InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]]
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=None
        )
        return ConversationHandler.END

    text = (
        "📸 Siguenos en Instagram y gana +100 reputacion\n\n"
        "🔗 Cuenta: @dany_vg56\n\n"
        "📋 Instrucciones:\n"
        "1️⃣ Sigue nuestra cuenta en Instagram\n"
        "2️⃣ Haz clic en '✅ Confirmar'\n"
        "3️⃣ Ingresa tu usuario de Instagram\n"
        "4️⃣ El admin confirma y recibes +100 pts\n\n"
        "⏱️ Esto puede tomar hasta 24 horas."
    )

    keyboard = [
        [InlineKeyboardButton("📸 Ir a Instagram", url="https://www.instagram.com/dany_vg56?igsh=M2I4NmRnZjZvdXhr")],
        [InlineKeyboardButton("✅ Confirmar seguimiento", callback_data="confirm_instagram")],
        [InlineKeyboardButton("◀️ Volver", callback_data="earn_reputation")]
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=None
    )
    
    return WAITING_INSTAGRAM_USERNAME  # ← IMPORTANTE: Retorna el estado


async def instagram_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias para instagram_task."""
    return await instagram_task(update, context)


async def confirm_instagram_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de confirmación de Instagram (pide el username)."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    logger.info(f"📸 confirm_instagram_start: Usuario {user_id} iniciando confirmación")

    text = "📸 Ingresa tu usuario de Instagram:\n\n💡 Sin el @ (ejemplo: dany_vg56)"
    keyboard = [[InlineKeyboardButton("◀️ Cancelar", callback_data="earn_reputation")]]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=None
    )
    
    return WAITING_INSTAGRAM_USERNAME  # ← Retorna el estado para esperar el mensaje


async def confirm_instagram_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el username de Instagram y notifica al admin."""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Sin username"
    instagram_user = update.message.text.strip()

    logger.info(f"📸 confirm_instagram_process: Usuario {user_id} ingresó @{instagram_user}")

    if not instagram_user or len(instagram_user) < 3:
        await update.message.reply_text(
            "❌ Usuario inválido. Intenta de nuevo.\n\n"
            "💡 Ejemplo: dany_vg56 (sin el @)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="earn_reputation")]])
        )
        return WAITING_INSTAGRAM_USERNAME

    # Guardar solicitud en la base de datos
    from database import create_instagram_request
    create_instagram_request(user_id, username, instagram_user)

    ADMIN_ID = 5057900537
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📸 NUEVA SOLICITUD INSTAGRAM\n\n"
                 f"👤 Usuario: @{username}\n"
                 f"🆔 ID: {user_id}\n"
                 f"📸 Instagram: @{instagram_user}\n\n"
                 f"✅ Usa el panel de admin para confirmar o rechazar.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirmar", callback_data=f"confirm_insta_{user_id}_{instagram_user}")],
                [InlineKeyboardButton("❌ Rechazar", callback_data=f"reject_insta_{user_id}")]
            ])
        )
        logger.info(f"✅ Notificación enviada al admin")
    except Exception as e:
        logger.error(f"❌ Error notificando admin: {e}")

    await update.message.reply_text(
        "✅ SOLICITUD ENVIADA\n\n"
        "⏱️ Confirmaremos tu seguimiento en 24 horas.\n\n"
        "✨ Recibirás +100 reputación al ser confirmado.\n\n"
        "💡 Asegúrate de haber seguido @dany_vg56",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
    )

    return ConversationHandler.END


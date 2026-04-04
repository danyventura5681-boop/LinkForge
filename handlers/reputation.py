import logging
import hashlib
import uuid
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.database import (
    get_top_users, get_user, add_reputation, get_user_links, record_click,
    get_referrals_count
)

logger = logging.getLogger(__name__)

# ============================================
# SISTEMA DE TRACKING DE LINKS
# ============================================

LINK_VISITS = {}

def generate_tracking_token(user_id: int, link_id: int) -> str:
    """Genera un token único para rastrear la visita."""
    unique_str = f"{user_id}_{link_id}_{uuid.uuid4()}"
    token = hashlib.sha256(unique_str.encode()).hexdigest()[:16]
    return token

def create_tracking_url(original_url: str, token: str, bot_username: str) -> str:
    """Crea una URL que redirige a través de nuestro bot."""
    tracking_url = f"https://t.me/{bot_username}?start=visit_{token}"
    return tracking_url

def register_link_visit(token: str, user_id: int, link_id: int):
    """Registra que un usuario visitó un link."""
    LINK_VISITS[token] = {
        "user_id": user_id,
        "link_id": link_id,
        "timestamp": datetime.utcnow(),
        "confirmed": False
    }
    logger.info(f"🔗 Visita registrada: token={token}, user={user_id}, link={link_id}")

def verify_link_visit(token: str) -> bool:
    """Verifica que el usuario realmente visitó el link."""
    if token not in LINK_VISITS:
        logger.warning(f"❌ Token no encontrado: {token}")
        return False
    
    visit = LINK_VISITS[token]
    age = (datetime.utcnow() - visit["timestamp"]).total_seconds()
    
    if age > 900:  # 15 minutos
        logger.warning(f"⏱️ Token expirado: {token}")
        del LINK_VISITS[token]
        return False
    
    logger.info(f"✅ Token verificado: {token}")
    return True

def confirm_link_visit(token: str) -> dict:
    """Confirma la visita y retorna los datos."""
    if token not in LINK_VISITS:
        return {"success": False, "error": "Token inválido"}
    
    visit = LINK_VISITS[token]
    visit["confirmed"] = True
    
    return {
        "success": True,
        "user_id": visit["user_id"],
        "link_id": visit["link_id"]
    }

# ============================================
# FUNCIONES PRINCIPALES
# ============================================

async def earn_reputation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los top 5 links para ganar reputación."""
    user_id = update.effective_user.id
    logger.info(f"🎁 earn_reputation: Usuario {user_id} solicitó ganar reputación")

    top_users = get_top_users(limit=10)
    available_users = top_users[:5]

    if not available_users:
        text = (
            "🎁 **No hay usuarios disponibles**\n\n"
            "Vuelve más tarde cuando haya más usuarios registrados.\n\n"
            "💡 Consejo: Invita amigos con el botón 'Invitar Amigos' para aumentar la comunidad."
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
    context.user_data['visit_timestamps'] = {}
    bot_username = (await context.bot.get_me()).username

    text = "🎁 **Gana +5 reputación por cada link** 🎁\n\n"

    keyboard = []
    link_counter = 1

    for i, user in enumerate(available_users, 1):
        username = user.username or f"Usuario_{user.telegram_id}"
        user_links = get_user_links(user.telegram_id)
        
        if user_links:
            link = user_links[0]
            link_url = link.url
            link_id = link.id

            token = generate_tracking_token(user_id, link_id)
            tracking_url = create_tracking_url(link_url, token, bot_username)
            register_link_visit(token, user_id, link_id)
            
            callback_id = f"link_{link_counter}"
            context.user_data['link_map'][callback_id] = {
                'link_id': link_id,
                'user_id': user.telegram_id,
                'url': link_url,
                'username': username,
                'token': token,
                'original_url': link_url
            }

            keyboard.append([
                InlineKeyboardButton(
                    f"🔗 @{username} ({user.reputation} pts)",
                    url=tracking_url
                ),
                InlineKeyboardButton(
                    "✅ Visitado",
                    callback_data=callback_id
                )
            ])
            link_counter += 1

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
    logger.info(f"🎁 Mostrados {len(available_users)} usuarios disponibles")

async def visit_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica la visita y otorga reputación."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    callback_id = query.data

    logger.info(f"🔗 visit_link: Usuario {user_id} confirmó visita en {callback_id}")

    link_map = context.user_data.get('link_map', {})
    
    if callback_id not in link_map:
        await query.edit_message_text(
            "❌ Link no encontrado o ya fue visitado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
        )
        return

    link_info = link_map[callback_id]
    token = link_info['token']
    link_id = link_info['link_id']
    target_user_id = link_info['user_id']
    username = link_info['username']

    # ✅ Verificar que realmente visitó el link
    if not verify_link_visit(token):
        logger.warning(f"⚠️ Token inválido o expirado: {token}")
        await query.edit_message_text(
            "⚠️ **Token expirado o inválido**\n\n"
            "Debes hacer clic en el link primero.\n\n"
            "💡 Haz clic en el botón azul del link y espera a que se abra.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Volver", callback_data="more_links")]])
        )
        return

    if user_id == target_user_id:
        await query.edit_message_text(
            "❌ No puedes visitar tu propio link.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
        )
        return

    target_user = get_user(target_user_id)
    if not target_user:
        await query.edit_message_text(
            "❌ Usuario no encontrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
        )
        return

    # ✅ Registrar el clic y otorgar reputación
    record_click(user_id, link_id, reputation_earned=5)
    confirm_link_visit(token)
    
    logger.info(f"✅ +5 reputación para usuario {user_id} por visitar link de {target_user_id}")

    del link_map[callback_id]

    await query.edit_message_text(
        f"✅ **¡+5 reputación ganados!**\n\n"
        f"📊 Has visitado el link de **@{username}**\n\n"
        f"🎁 Sigue visitando más links para ganar puntos.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎁 Ver más links", callback_data="more_links")],
            [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
        ]),
        parse_mode='Markdown'
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
    
    return "WAITING_INSTAGRAM_USERNAME"

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
        return "WAITING_INSTAGRAM_USERNAME"

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
    
    return "DONE"

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
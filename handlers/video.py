import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import (
    get_user, add_reputation, get_all_videos, get_user_videos,
    add_video, get_video, increment_video_views, get_top_videos
)

logger = logging.getLogger(__name__)

# ============================================
# SISTEMA DE TEMPORIZADOR PARA VIDEOS (2 MINUTOS)
# ============================================

# Diccionario para almacenar temporizadores activos de videos
PENDING_VIDEO_VERIFICATIONS = {}

# Diccionario para evitar doble recompensa por video
# {user_id: [video_id1, video_id2, ...]}
USER_WATCHED_VIDEOS = {}

# Constantes
VIDEO_WAIT_SECONDS = 120      # 2 minutos = 120 segundos
VIDEO_MAX_WAIT_SECONDS = 600  # 10 minutos máximo para verificar
VIDEO_REWARD = 30             # +30 reputación por video

def has_user_watched_video(user_id: int, video_id: int) -> bool:
    """Verifica si el usuario ya ha visto este video antes."""
    if user_id not in USER_WATCHED_VIDEOS:
        return False
    return video_id in USER_WATCHED_VIDEOS[user_id]

def mark_video_as_watched(user_id: int, video_id: int):
    """Marca que el usuario ya vio este video."""
    if user_id not in USER_WATCHED_VIDEOS:
        USER_WATCHED_VIDEOS[user_id] = []
    if video_id not in USER_WATCHED_VIDEOS[user_id]:
        USER_WATCHED_VIDEOS[user_id].append(video_id)
    logger.info(f"📹 Video {video_id} marcado como visto por usuario {user_id}")

async def show_video_with_timer(update: Update, context: ContextTypes.DEFAULT_TYPE, video_info: dict):
    """Muestra el video con botón de confirmación que aparece después de 2 minutos."""
    user_id = update.effective_user.id
    username = video_info['username']
    video_url = video_info['url']
    video_id = video_info['video_id']
    video_title = video_info.get('title', 'Video')
    
    # Mensaje con el video como botón que redirige
    text = (
        f"📹 **Gana +{VIDEO_REWARD} reputación viendo este video**\n\n"
        f"👤 **Creador:** @{username}\n"
        f"🎬 **Título:** {video_title}\n"
        f"⭐ **Recompensa:** +{VIDEO_REWARD} puntos\n\n"
        f"⏱️ **Debes ver al menos 2 minutos del video**\n\n"
        f"👇 **Haz clic en el botón para ver el video:**"
    )
    
    # Video como botón inline que redirige
    keyboard = [
        [InlineKeyboardButton("📹 VER VIDEO", url=video_url)],
        [InlineKeyboardButton("◀️ Cancelar", callback_data="cancel_video_verification")]
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
    PENDING_VIDEO_VERIFICATIONS[user_id] = {
        'video_id': video_id,
        'creator_user_id': video_info['user_id'],
        'username': username,
        'url': video_url,
        'title': video_title,
        'chat_id': msg.chat_id,
        'message_id': msg.message_id,
        'timestamp': datetime.utcnow(),
        'confirmed': False
    }
    
    # Iniciar temporizador oculto de 2 minutos
    asyncio.create_task(video_hidden_timer(context, user_id, msg.chat_id, msg.message_id, video_url, username, video_title, video_id, video_info['user_id']))
    
    logger.info(f"⏰ Temporizador de video iniciado para usuario {user_id}, botón aparecerá en {VIDEO_WAIT_SECONDS}s")

async def video_hidden_timer(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int, message_id: int, video_url: str, username: str, video_title: str, video_id: int, creator_user_id: int):
    """Temporizador oculto que muestra el botón de confirmación después de 2 minutos."""
    await asyncio.sleep(VIDEO_WAIT_SECONDS)
    
    # Verificar si la verificación sigue activa
    if user_id not in PENDING_VIDEO_VERIFICATIONS:
        return
    
    pending = PENDING_VIDEO_VERIFICATIONS[user_id]
    
    # Verificar que el usuario no haya visto este video antes
    if has_user_watched_video(user_id, video_id):
        del PENDING_VIDEO_VERIFICATIONS[user_id]
        text = (
            f"⚠️ **Ya has visto este video anteriormente**\n\n"
            f"👤 **Creador:** @{username}\n"
            f"🎬 **Título:** {video_title}\n\n"
            f"💡 No puedes recibir reputación dos veces por el mismo video.\n\n"
            f"📹 Prueba con otros videos disponibles."
        )
        keyboard = [[InlineKeyboardButton("🎬 Ver Top Videos", callback_data="top_videos")]]
        try:
            await context.bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error mostrando mensaje de video ya visto: {e}")
        return
    
    # Texto con el botón de confirmar
    text = (
        f"📹 **Verificación de video**\n\n"
        f"👤 **Creador:** @{username}\n"
        f"🎬 **Título:** {video_title}\n"
        f"⭐ **Recompensa:** +{VIDEO_REWARD} puntos\n\n"
        f"✅ **¿Ya viste el video (mínimo 2 minutos)?**\n"
        f"Presiona el botón para recibir tu reputación.\n\n"
        f"⚠️ Tienes 10 minutos para confirmar."
    )
    
    # Botón Confirmar
    keyboard = [
        [InlineKeyboardButton("✅ CONFIRMAR", callback_data=f"confirm_video_{video_id}_{creator_user_id}")],
        [InlineKeyboardButton("◀️ Cancelar", callback_data="cancel_video_verification")]
    ]
    
    try:
        await context.bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        logger.info(f"✅ Botón CONFIRMAR de video apareció para usuario {user_id}")
    except Exception as e:
        logger.error(f"Error mostrando botón de confirmación de video: {e}")

# ============================================
# FUNCIONES PRINCIPALES DE VIDEOS
# ============================================

async def top_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el top de videos para ganar reputación."""
    user_id = update.effective_user.id
    logger.info(f"📹 top_videos: Usuario {user_id} solicitó ver top videos")
    
    videos = get_top_videos(limit=10)
    
    if not videos:
        text = (
            f"📹 **Top Videos**\n\n"
            f"🎬 No hay videos disponibles en este momento.\n\n"
            f"💡 Los usuarios VIP pueden subir videos para promocionar su contenido.\n\n"
            f"⭐ ¡Conviértete en VIP para aparecer aquí!"
        )
        keyboard = [
            [InlineKeyboardButton("⭐ VIP", callback_data="vip_info")],
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
        return
    
    context.user_data['video_map'] = {}
    
    text = f"📹 **Top Videos** 🎬\n\n✨ Gana +{VIDEO_REWARD} reputación por cada video (mínimo 2 minutos)\n\n"
    
    keyboard = []
    video_counter = 1
    
    for video in videos:
        # No mostrar videos del propio usuario
        if video.user_id == user_id:
            continue
        
        # Verificar si el usuario ya vio este video
        if has_user_watched_video(user_id, video.id):
            continue
        
        username = video.username or f"Usuario_{video.user_id}"
        
        callback_id = f"video_{video_counter}"
        context.user_data['video_map'][callback_id] = {
            'video_id': video.id,
            'user_id': video.user_id,
            'url': video.url,
            'username': username,
            'title': video.title or 'Sin título',
            'views': video.views or 0
        }
        
        keyboard.append([
            InlineKeyboardButton(
                f"📹 {video.title[:30]} (@{username}) - {video.views} vistas",
                callback_data=callback_id
            )
        ])
        video_counter += 1
    
    if not keyboard:
        text = (
            f"📹 **Top Videos**\n\n"
            f"🎬 No hay videos nuevos disponibles.\n\n"
            f"💡 Ya has visto todos los videos disponibles.\n"
            f"📹 Vuelve más tarde para más contenido."
        )
        keyboard = [[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]]
    
    keyboard.append([InlineKeyboardButton("🔄 Actualizar", callback_data="refresh_videos")])
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
    
    logger.info(f"📹 Mostrados {video_counter - 1} videos disponibles")

async def watch_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de ver un video con temporizador de 2 minutos."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_id = query.data
    
    logger.info(f"📹 watch_video: Usuario {user_id} seleccionó video {callback_id}")
    
    video_map = context.user_data.get('video_map', {})
    
    if callback_id not in video_map:
        await query.edit_message_text(
            "❌ Video no encontrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="top_videos")]])
        )
        return
    
    video_info = video_map[callback_id]
    
    # Verificar que no sea su propio video
    if video_info['user_id'] == user_id:
        await query.edit_message_text(
            "❌ No puedes ver tu propio video.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="top_videos")]])
        )
        return
    
    # Verificar si ya vio este video antes
    if has_user_watched_video(user_id, video_info['video_id']):
        await query.edit_message_text(
            "⚠️ **Ya has visto este video anteriormente**\n\n"
            "No puedes recibir reputación dos veces por el mismo video.\n\n"
            "📹 Prueba con otros videos disponibles.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎬 Ver Top Videos", callback_data="top_videos")]]),
            parse_mode='Markdown'
        )
        return
    
    # Mostrar video con temporizador
    await show_video_with_timer(update, context, video_info)

async def confirm_video_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirma la vista del video y otorga reputación."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Extraer datos del callback_data
    data_parts = query.data.split('_')
    if len(data_parts) >= 3:
        video_id = int(data_parts[2])
        creator_user_id = int(data_parts[3])
    else:
        await query.edit_message_text(
            "❌ Error en la verificación.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="top_videos")]])
        )
        return
    
    # Verificar que haya una verificación pendiente
    if user_id not in PENDING_VIDEO_VERIFICATIONS:
        await query.edit_message_text(
            "❌ No hay verificación pendiente.\n\nUsa 'Top Videos' para comenzar.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="top_videos")]])
        )
        return
    
    pending = PENDING_VIDEO_VERIFICATIONS[user_id]
    
    # Verificar que coincidan los datos
    if pending['video_id'] != video_id or pending['creator_user_id'] != creator_user_id:
        await query.edit_message_text(
            "❌ Error en la verificación. Intenta de nuevo.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="top_videos")]])
        )
        return
    
    # Verificar expiración
    age = (datetime.utcnow() - pending['timestamp']).total_seconds()
    if age > VIDEO_MAX_WAIT_SECONDS + VIDEO_WAIT_SECONDS:
        del PENDING_VIDEO_VERIFICATIONS[user_id]
        await query.edit_message_text(
            "⏰ **Tiempo expirado**\n\nDebes confirmar dentro de los 10 minutos después de ver el video.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Intentar de nuevo", callback_data="top_videos")]])
        )
        return
    
    # Verificar que no sea su propio video
    if pending['creator_user_id'] == user_id:
        del PENDING_VIDEO_VERIFICATIONS[user_id]
        await query.edit_message_text(
            "❌ No puedes verificar tu propio video.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="top_videos")]])
        )
        return
    
    # Verificar si ya vio este video antes
    if has_user_watched_video(user_id, video_id):
        del PENDING_VIDEO_VERIFICATIONS[user_id]
        await query.edit_message_text(
            "⚠️ **Ya has recibido reputación por este video**\n\n"
            "No puedes recibir reputación dos veces por el mismo video.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎬 Ver Top Videos", callback_data="top_videos")]]),
            parse_mode='Markdown'
        )
        return
    
    # Otorgar reputación
    add_reputation(user_id, VIDEO_REWARD)
    
    # Incrementar contador de vistas del video
    increment_video_views(video_id)
    
    # Marcar este video como visto por este usuario
    mark_video_as_watched(user_id, video_id)
    
    logger.info(f"✅ +{VIDEO_REWARD} reputación para usuario {user_id} por ver video de {pending['creator_user_id']}")
    
    # Limpiar pending
    del PENDING_VIDEO_VERIFICATIONS[user_id]
    
    await query.edit_message_text(
        f"✅ **¡+{VIDEO_REWARD} reputación ganados!**\n\n"
        f"📹 Has visto el video **{pending['title']}** de @{pending['username']}\n\n"
        f"💡 Sigue viendo más videos para ganar puntos.\n\n"
        f"🎬 ¡Apoya a los creadores VIP!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Ver más videos", callback_data="top_videos")],
            [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
        ]),
        parse_mode='Markdown'
    )

async def cancel_video_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la verificación de video pendiente."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id in PENDING_VIDEO_VERIFICATIONS:
        del PENDING_VIDEO_VERIFICATIONS[user_id]
        logger.info(f"❌ Usuario {user_id} canceló la verificación de video")
    
    await query.edit_message_text(
        "❌ Verificación cancelada.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="top_videos")]])
    )

async def refresh_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Actualiza la lista de videos."""
    query = update.callback_query
    await query.answer()
    await top_videos(update, context)
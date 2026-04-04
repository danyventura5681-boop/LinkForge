import logging
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.database import (
    get_user, add_video, get_user_videos, delete_video, get_video,
    get_videos_count_by_user, can_user_add_video
)

logger = logging.getLogger(__name__)

# Estados para la conversación de agregar video
WAITING_VIDEO_URL = 1
WAITING_VIDEO_TITLE = 2

# Expresión regular para validar URLs de video (YouTube, Vimeo, etc.)
VIDEO_URL_PATTERN = re.compile(
    r'^(https?://)?(www\.)?(youtube\.com|youtu\.be|vimeo\.com|tiktok\.com|instagram\.com|facebook\.com)/.+$',
    re.IGNORECASE
)

def is_valid_video_url(url: str) -> bool:
    """Valida si la URL es de una plataforma de video soportada."""
    return re.match(VIDEO_URL_PATTERN, url) is not None

async def promote_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menú principal para promocionar contenido (solo VIP)."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    logger.info(f"📱 promote_menu: Usuario {user_id} accedió a promocionar contenido")
    
    # Verificar si es VIP
    if not user or user.vip_level < 1:
        text = (
            "📱 **Promocionar Contenido** ⭐\n\n"
            "❌ **Acceso Restringido**\n\n"
            "Esta función es exclusiva para usuarios VIP.\n\n"
            "📊 **Beneficios VIP:**\n"
            "✅ Publica videos en el Top Videos\n"
            "✅ +30 reputación por cada vista\n"
            "✅ Llega a más usuarios\n"
            "✅ Prioridad en el ranking\n\n"
            "⭐ **Actualiza a VIP ahora** y comienza a promocionar tu contenido."
        )
        keyboard = [
            [InlineKeyboardButton("⭐ Ver Planes VIP", callback_data="vip_info")],
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
    
    # Obtener estadísticas del usuario
    videos_count = get_videos_count_by_user(user_id)
    max_videos = 3 if user.vip_level >= 3 else 1
    remaining_slots = max_videos - videos_count
    
    user_videos = get_user_videos(user_id)
    
    text = (
        f"📱 **Promocionar Contenido** ⭐\n\n"
        f"👤 **Tu nivel VIP:** {user.vip_level}\n"
        f"📹 **Videos publicados:** {videos_count}/{max_videos}\n"
        f"🎬 **Espacios disponibles:** {remaining_slots}\n\n"
        f"📊 **¿Cómo funciona?**\n"
        f"1️⃣ Sube un video (YouTube, TikTok, Instagram, etc.)\n"
        f"2️⃣ Aparecerá en el Top Videos\n"
        f"3️⃣ Otros usuarios lo verán y ganarás visitas\n"
        f"4️⃣ Cada vista te da +30 reputación\n\n"
        f"✨ **Beneficio extra:**\n"
        f"Los videos con más vistas aparecen primero en el ranking."
    )
    
    keyboard = []
    
    if remaining_slots > 0:
        keyboard.append([InlineKeyboardButton("➕ Subir nuevo video", callback_data="add_video")])
    
    if user_videos:
        keyboard.append([InlineKeyboardButton("📋 Mis videos", callback_data="my_uploaded_videos")])
    
    keyboard.append([InlineKeyboardButton("🎬 Ver Top Videos", callback_data="top_videos")])
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

async def add_video_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de agregar un video."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    
    # Verificar límite de videos
    videos_count = get_videos_count_by_user(user_id)
    max_videos = 3 if user.vip_level >= 3 else 1
    
    if videos_count >= max_videos:
        await query.edit_message_text(
            f"⚠️ **Límite de videos alcanzado**\n\n"
            f"📹 Has alcanzado el límite de {max_videos} video(s).\n\n"
            f"💡 Actualiza a VIP 3 para subir hasta 3 videos.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ VIP", callback_data="vip_info")],
                [InlineKeyboardButton("◀️ Volver", callback_data="promote_menu")]
            ]),
            parse_mode='Markdown'
        )
        return
    
    text = (
        "📹 **Subir nuevo video**\n\n"
        "📋 **Instrucciones:**\n"
        "1️⃣ Envía el enlace de tu video\n"
        "2️⃣ Puedes usar YouTube, TikTok, Instagram, Vimeo o Facebook\n"
        "3️⃣ El video debe ser público\n"
        "4️⃣ Mínimo 1 minuto de duración recomendado\n\n"
        "🔗 **Envía el enlace del video:**"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Cancelar", callback_data="promote_menu")]]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return WAITING_VIDEO_URL

async def process_video_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa la URL del video."""
    user_id = update.effective_user.id
    video_url = update.message.text.strip()
    
    logger.info(f"📹 process_video_url: Usuario {user_id} envió URL: {video_url}")
    
    # Validar URL
    if not is_valid_video_url(video_url):
        await update.message.reply_text(
            "❌ **URL no válida**\n\n"
            "Solo se permiten enlaces de:\n"
            "• YouTube (youtube.com, youtu.be)\n"
            "• TikTok (tiktok.com)\n"
            "• Instagram (instagram.com)\n"
            "• Vimeo (vimeo.com)\n"
            "• Facebook (facebook.com)\n\n"
            "💡 Asegúrate de que el enlace sea público.\n\n"
            "🔗 Envía un enlace válido o /cancel para cancelar.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="promote_menu")]])
        )
        return WAITING_VIDEO_URL
    
    # Guardar URL temporalmente
    context.user_data['temp_video_url'] = video_url
    
    text = (
        "📹 **Subir nuevo video**\n\n"
        f"✅ URL válida: `{video_url}`\n\n"
        "📝 **Ahora envía el título de tu video:**\n\n"
        "💡 Ejemplo: `Mi mejor jugada en Fortnite`\n\n"
        "🎬 El título será visible para todos los usuarios."
    )
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="promote_menu")]]),
        parse_mode='Markdown'
    )
    
    return WAITING_VIDEO_TITLE

async def process_video_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el título del video y guarda en la base de datos."""
    user_id = update.effective_user.id
    username = update.effective_user.username or f"Usuario_{user_id}"
    video_title = update.message.text.strip()
    video_url = context.user_data.get('temp_video_url')
    
    logger.info(f"📹 process_video_title: Usuario {user_id} título: {video_title}")
    
    if not video_url:
        await update.message.reply_text(
            "❌ Error: No se encontró la URL del video.\n\n"
            "Por favor, inicia el proceso nuevamente.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="promote_menu")]])
        )
        return ConversationHandler.END
    
    # Validar título
    if len(video_title) < 3 or len(video_title) > 100:
        await update.message.reply_text(
            "❌ **Título inválido**\n\n"
            "El título debe tener entre 3 y 100 caracteres.\n\n"
            "📝 Envía un título válido o /cancel para cancelar.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="promote_menu")]])
        )
        return WAITING_VIDEO_TITLE
    
    # Guardar video en la base de datos
    video = add_video(user_id, username, video_url, video_title)
    
    if video:
        logger.info(f"✅ Video guardado: {video_title} por usuario {user_id}")
        
        # Limpiar datos temporales
        context.user_data.pop('temp_video_url', None)
        
        await update.message.reply_text(
            f"✅ **¡Video publicado con éxito!**\n\n"
            f"📹 **Título:** {video_title}\n"
            f"🔗 **URL:** `{video_url}`\n\n"
            f"🎬 Tu video ya está en el Top Videos.\n"
            f"⭐ Por cada vista recibirás +30 reputación.\n\n"
            f"📊 Comparte tu video para obtener más visitas.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎬 Ver Top Videos", callback_data="top_videos")],
                [InlineKeyboardButton("📱 Mi Panel VIP", callback_data="promote_menu")],
                [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
            ]),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "❌ **Error al publicar el video**\n\n"
            "Por favor, intenta nuevamente más tarde.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="promote_menu")]])
        )
    
    return ConversationHandler.END

async def my_uploaded_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los videos subidos por el usuario."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    videos = get_user_videos(user_id)
    
    if not videos:
        text = (
            "📋 **Mis videos**\n\n"
            "❌ No has subido ningún video aún.\n\n"
            "📹 Sube tu primer video para comenzar a promocionar tu contenido.\n\n"
            f"💡 Como VIP nivel {user.vip_level}, puedes subir hasta {3 if user.vip_level >= 3 else 1} video(s)."
        )
        keyboard = [
            [InlineKeyboardButton("➕ Subir video", callback_data="add_video")],
            [InlineKeyboardButton("◀️ Volver", callback_data="promote_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    text = f"📋 **Mis videos**\n\n📹 Total: {len(videos)} videos\n\n"
    
    keyboard = []
    for video in videos:
        text += f"🎬 **{video.title}**\n"
        text += f"🔗 `{video.url}`\n"
        text += f"👁️ Vistas: {video.views or 0} | 📅 {video.created_at.strftime('%d/%m/%Y')}\n\n"
        
        keyboard.append([InlineKeyboardButton(
            f"🗑️ Eliminar: {video.title[:30]}",
            callback_data=f"delete_video_{video.id}"
        )])
    
    keyboard.append([InlineKeyboardButton("➕ Subir nuevo video", callback_data="add_video")])
    keyboard.append([InlineKeyboardButton("◀️ Volver", callback_data="promote_menu")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def delete_video_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elimina un video del usuario."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    video_id = int(query.data.split('_')[2])
    
    video = get_video(video_id)
    
    if not video:
        await query.edit_message_text(
            "❌ Video no encontrado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="promote_menu")]])
        )
        return
    
    # Verificar que el video pertenezca al usuario
    if video.user_id != user_id:
        await query.edit_message_text(
            "❌ No puedes eliminar videos de otros usuarios.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="promote_menu")]])
        )
        return
    
    delete_video(video_id)
    logger.info(f"🗑️ Video {video_id} eliminado por usuario {user_id}")
    
    await query.edit_message_text(
        f"✅ **Video eliminado**\n\n"
        f"📹 Título: {video.title}\n\n"
        f"Tu video ha sido removido del Top Videos.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Mis videos", callback_data="my_uploaded_videos")],
            [InlineKeyboardButton("◀️ Volver", callback_data="promote_menu")]
        ]),
        parse_mode='Markdown'
    )

async def cancel_promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la operación de agregar video."""
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop('temp_video_url', None)
    
    await query.edit_message_text(
        "❌ Operación cancelada.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="promote_menu")]])
    )
    
    return ConversationHandler.END
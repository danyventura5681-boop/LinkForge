import logging
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import (
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
            "📱 **PROMOCIONAR CONTENIDO** ⭐\n\n"
            "❌ **ACCESO RESTRINGIDO**\n\n"
            "Esta función es exclusiva para usuarios **VIP**.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📊 **BENEFICIOS VIP:**\n\n"
            "✅ Publica videos en el **Top Videos**\n"
            "🏆 **Garantizamos 2000 vistas mínimo** por video\n"
            "📈 **Prioridad en el ranking** por reputación\n"
            "🎬 **Exposición masiva** a toda la comunidad\n"
            "⭐ **Hasta 3 videos** simultáneos (VIP 3)\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💰 **¿CÓMO GANO REPUTACIÓN?**\n\n"
            "• Los usuarios que VEAN tu video ganan +30 reputación\n"
            "• Tú ganas **VISIBILIDAD** y llegas a más personas\n"
            "• Más vistas = más exposición = más crecimiento\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⭐ **Actualiza a VIP ahora** y comienza a promocionar tu contenido.\n\n"
            "💡 *Mientras más reputación tengas, más arriba aparecerá tu video*"
        )
        keyboard = [
            [InlineKeyboardButton("⭐ VER PLANES VIP", callback_data="vip_info")],
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
    
    # Calcular vistas totales
    total_views = sum(video.views or 0 for video in user_videos)

    text = (
        f"📱 **PROMOCIONAR CONTENIDO** ⭐\n\n"
        f"👤 **Tu nivel VIP:** `{user.vip_level}`\n"
        f"📹 **Videos publicados:** `{videos_count}/{max_videos}`\n"
        f"🎬 **Espacios disponibles:** `{remaining_slots}`\n"
        f"👁️ **Vistas totales:** `{total_views}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **¿CÓMO FUNCIONA?**\n\n"
        f"1️⃣ **Sube un video** (YouTube, TikTok, Instagram, Vimeo, Facebook)\n"
        f"2️⃣ **Aparecerá en el Top Videos** ordenado por reputación\n"
        f"3️⃣ **Otros usuarios lo verán** (mínimo 2 minutos)\n"
        f"4️⃣ **Ellos ganan +30 reputación** por cada video visto\n"
        f"5️⃣ **Tú ganas VISIBILIDAD** y llegas a más personas\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **VENTAJAS EXCLUSIVAS VIP:**\n\n"
        f"🏆 **Garantizamos 2000 vistas mínimo** por video\n"
        f"💰 **Contenido monetizable** - Vistas de +2 minutos\n"
        f"📈 **Prioridad en ranking** según tu reputación\n"
        f"🎬 **Máxima exposición** a toda la comunidad\n"
        f"⭐ **Hasta 3 videos** simultáneos (VIP 3)\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ **BENEFICIO EXTRA:**\n"
        f"Los videos de usuarios con **mayor reputación**\n"
        f"aparecen **primero en el ranking** 🚀\n\n"
        f"💡 *Mientras más reputación tengas, más visitas recibirás*"
    )

    keyboard = []

    if remaining_slots > 0:
        keyboard.append([InlineKeyboardButton("➕ SUBIR NUEVO VIDEO 🎬", callback_data="add_video")])

    if user_videos:
        keyboard.append([InlineKeyboardButton("📋 MIS VIDEOS", callback_data="my_uploaded_videos")])

    keyboard.append([InlineKeyboardButton("🎬 VER TOP VIDEOS", callback_data="top_videos")])
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
            f"📹 Has alcanzado el límite de `{max_videos}` video(s).\n\n"
            f"💡 **Actualiza a VIP 3** para subir hasta 3 videos.\n\n"
            f"⭐ [Ver Planes VIP →](callback: vip_info)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ VER PLANES VIP", callback_data="vip_info")],
                [InlineKeyboardButton("◀️ Volver", callback_data="promote_menu")]
            ]),
            parse_mode='Markdown'
        )
        return

    text = (
        "🎬 **SUBIR NUEVO VIDEO** 🎬\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📋 **INSTRUCCIONES:**\n\n"
        "1️⃣ Envía el enlace de tu video\n"
        "2️⃣ Plataformas: YouTube, TikTok, Instagram, Vimeo, Facebook\n"
        "3️⃣ El video debe ser **PÚBLICO**\n"
        "4️⃣ Mínimo **2 minutos** de duración (monetizable)\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 **LO QUE GANAS:**\n\n"
        "🏆 **2000 vistas garantizadas**\n"
        "📈 **Prioridad en el ranking**\n"
        "🎬 **Exposición masiva**\n"
        "⭐ **Visibilidad para tu canal**\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔗 **Envía el enlace de tu video:**"
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
            "❌ **URL NO VÁLIDA** ❌\n\n"
            "Solo se permiten enlaces de:\n"
            "• YouTube (youtube.com, youtu.be) 🎬\n"
            "• TikTok (tiktok.com) 📱\n"
            "• Instagram (instagram.com) 📸\n"
            "• Vimeo (vimeo.com) 🎥\n"
            "• Facebook (facebook.com) 📘\n\n"
            "💡 **Asegúrate de que:**\n"
            "• El enlace sea público\n"
            "• El video tenga al menos 2 minutos\n"
            "• El contenido sea original\n\n"
            "🔗 Envía un enlace válido o /cancel para cancelar.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancelar", callback_data="promote_menu")]])
        )
        return WAITING_VIDEO_URL

    # Guardar URL temporalmente
    context.user_data['temp_video_url'] = video_url

    text = (
        "🎬 **SUBIR NUEVO VIDEO** 🎬\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ **URL válida:** `{video_url}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📝 **Ahora envía el TÍTULO de tu video:**\n\n"
        "💡 **Ejemplo:** `Mi mejor jugada en Fortnite - Gameplay épico`\n\n"
        "🎯 **Consejos para un buen título:**\n"
        "• Usa palabras clave 🔑\n"
        "• Máximo 100 caracteres ✏️\n"
        "• Describe el contenido 📝\n\n"
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
            "❌ **ERROR** ❌\n\n"
            "No se encontró la URL del video.\n\n"
            "Por favor, inicia el proceso nuevamente.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="promote_menu")]])
        )
        return ConversationHandler.END

    # Validar título
    if len(video_title) < 3 or len(video_title) > 100:
        await update.message.reply_text(
            "❌ **TÍTULO INVÁLIDO** ❌\n\n"
            "El título debe tener entre **3 y 100 caracteres**.\n\n"
            f"📏 Longitud actual: {len(video_title)} caracteres\n\n"
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
            f"✅ **¡VIDEO PUBLICADO CON ÉXITO!** 🎉\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📹 **Título:** {video_title}\n"
            f"🔗 **URL:** `{video_url}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **LO QUE VIENE AHORA:**\n\n"
            f"🏆 **Garantizamos 2000 vistas mínimo**\n"
            f"📈 **Prioridad en ranking por tu reputación**\n"
            f"🎬 **Exposición a toda la comunidad**\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 **CONSEJOS PARA MÁS VISTAS:**\n\n"
            f"• Comparte tu video en redes sociales 📱\n"
            f"• Gana reputación para subir en el ranking ⭐\n"
            f"• Invita amigos a la plataforma 👥\n"
            f"• Mantén contenido de calidad 🎯\n\n"
            f"🚀 **¡Tu video ya está en el Top Videos!**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎬 VER TOP VIDEOS", callback_data="top_videos")],
                [InlineKeyboardButton("📱 MI PANEL VIP", callback_data="promote_menu")],
                [InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]
            ]),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "❌ **ERROR AL PUBLICAR EL VIDEO** ❌\n\n"
            "Ocurrió un error inesperado.\n\n"
            "Por favor, intenta nuevamente más tarde.\n\n"
            "Si el problema persiste, contacta al administrador.",
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
            "📋 **MIS VIDEOS**\n\n"
            "❌ No has subido ningún video aún.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🎬 **¿Por qué subir un video?**\n\n"
            "🏆 **2000 vistas garantizadas**\n"
            "📈 **Prioridad en el ranking**\n"
            "🎬 **Exposición masiva**\n"
            "⭐ **Visibilidad para tu canal**\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 Como **VIP nivel {user.vip_level}**, puedes subir hasta **{3 if user.vip_level >= 3 else 1}** video(s).\n\n"
            "🚀 **¡Sube tu primer video ahora!**"
        )
        keyboard = [
            [InlineKeyboardButton("➕ SUBIR VIDEO", callback_data="add_video")],
            [InlineKeyboardButton("◀️ Volver", callback_data="promote_menu")]
        ]

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return

    total_views = sum(video.views or 0 for video in videos)

    text = (
        f"📋 **MIS VIDEOS** 🎬\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📹 **Total:** {len(videos)} videos\n"
        f"👁️ **Vistas totales:** {total_views}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    keyboard = []
    for i, video in enumerate(videos, 1):
        text += (
            f"**{i}. {video.title}**\n"
            f"🔗 `{video.url}`\n"
            f"👁️ Vistas: `{video.views or 0}`\n"
            f"📅 Subido: {video.created_at.strftime('%d/%m/%Y')}\n\n"
        )

        keyboard.append([InlineKeyboardButton(
            f"🗑️ ELIMINAR: {video.title[:25]}",
            callback_data=f"delete_video_{video.id}"
        )])

    keyboard.append([InlineKeyboardButton("➕ SUBIR NUEVO VIDEO", callback_data="add_video")])
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

    views_lost = video.views or 0

    delete_video(video_id)
    logger.info(f"🗑️ Video {video_id} eliminado por usuario {user_id}")

    await query.edit_message_text(
        f"✅ **VIDEO ELIMINADO**\n\n"
        f"📹 **Título:** {video.title}\n"
        f"👁️ **Vistas acumuladas:** {views_lost}\n\n"
        f"Tu video ha sido removido del Top Videos.\n\n"
        f"💡 Puedes subir un nuevo video cuando quieras.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 MIS VIDEOS", callback_data="my_uploaded_videos")],
            [InlineKeyboardButton("➕ SUBIR NUEVO VIDEO", callback_data="add_video")],
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
        "❌ Operación cancelada.\n\n"
        "Puedes volver a intentarlo cuando quieras.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver", callback_data="promote_menu")]])
    )

    return ConversationHandler.END
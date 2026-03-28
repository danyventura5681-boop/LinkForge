import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_user, activate_vip, register_payment, get_user_links

logger = logging.getLogger(__name__)

# Planes VIP
VIP_PLANS = {
    1: {"name": "VIP 1", "price_usd": 1, "reputation": 500, "days": 30, "max_links": 3},
    2: {"name": "VIP 2", "price_usd": 5, "reputation": 2800, "days": 30, "max_links": 3},
    3: {"name": "VIP 3", "price_usd": 10, "reputation": 6000, "days": 30, "max_links": 3}
}

# Direcciones de criptomonedas
CRYPTO_ADDRESSES = {
    "TRX": "TK2K6W7vFehHLB6eQ9CPPjcJ1E6ErCu12Y",
    "TON": "UQBJG1Dh1cRpHZqAMJ0qgD0CDyIUo0y2u82oG--pMm0G0jkl",
    "ETH": "0x1526Fa97f7E7d8A0AB76F3fb94F97A3E1281cA81",
    "BTC": "bc1q4netsk5cnyszu4s036nhj26pm3a405j6wnjnsy",
    "BNB": "0x1526Fa97f7E7d8A0AB76F3fb94F97A3E1281cA81",
    "SOL": "9ncG6PPVVPueqELv3rC8JeNUbnkbhdQ9E522BDJqZvF"
}

def format_vip_expiration(vip_expires_at):
    """Formatea la fecha de expiración VIP"""
    if not vip_expires_at:
        return "No activo"
    
    try:
        if isinstance(vip_expires_at, str):
            vip_expires_at = datetime.fromisoformat(vip_expires_at.replace('Z', '+00:00'))
        
        now = datetime.utcnow()
        if vip_expires_at <= now:
            return "EXPIRADO"
        
        remaining = vip_expires_at - now
        days = remaining.days
        hours = remaining.seconds // 3600
        
        if days > 0:
            return f"{days} días, {hours} horas"
        else:
            return f"{hours} horas"
    except Exception:
        return "No disponible"

async def vip_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el menú de planes VIP."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    current_vip = user.get("vip_level", 0) if user else 0
    vip_expires = user.get("vip_expires_at") if user else None
    reputation = user.get("reputation", 0) if user else 0
    
    # Calcular tiempo restante de VIP
    if current_vip > 0 and vip_expires:
        time_left = format_vip_expiration(vip_expires)
        vip_status = f"✅ **Activo hasta:** {time_left}"
    elif current_vip > 0:
        vip_status = "✅ **Activo**"
    else:
        vip_status = "❌ **No activo**"

    text = (
        f"⭐ **PLANES VIP** ⭐\n\n"
        f"👤 **Tu nivel actual:** {current_vip}\n"
        f"💎 **Tu reputación:** {reputation} pts\n"
        f"{vip_status}\n\n"
        f"**Planes disponibles:**\n"
    )

    keyboard = []
    for level, plan in VIP_PLANS.items():
        text += f"\n**{plan['name']}** - **${plan['price_usd']} USD**\n"
        text += f"🎁 +{plan['reputation']} reputación\n"
        text += f"⏳ {plan['days']} días de promoción\n"
        text += f"🔗 Hasta {plan['max_links']} links simultáneos\n"
        
        # Si es mayor que el nivel actual, mostrar botón
        if level > current_vip:
            keyboard.append([InlineKeyboardButton(
                f"💰 Comprar {plan['name']} (${plan['price_usd']})",
                callback_data=f"buy_vip_{level}"
            )])
        else:
            text += f"✅ *Ya tienes este nivel o superior*\n"

    if current_vip > 0:
        text += f"\n📌 **Tus links activos:** {len(get_user_links(user_id))}/{3 if current_vip > 0 else 1}"
    
    keyboard.append([InlineKeyboardButton("🏠 Volver al inicio", callback_data="back_to_start")])

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def buy_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra instrucciones de pago para VIP."""
    query = update.callback_query
    await query.answer()

    level = int(query.data.split("_")[2])
    plan = VIP_PLANS.get(level)

    if not plan:
        await query.edit_message_text("❌ Plan no válido.")
        return

    # Guardar plan seleccionado en contexto
    context.user_data['pending_vip'] = level
    
    # Generar ID de transacción único (para seguimiento)
    tx_ref = f"VIP{level}_{query.from_user.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    context.user_data['vip_tx_ref'] = tx_ref

    text = (
        f"⭐ **Compra de {plan['name']}** ⭐\n\n"
        f"💰 **Precio:** **${plan['price_usd']} USD**\n"
        f"🎁 **Recompensa:** **+{plan['reputation']} reputación**\n"
        f"⏳ **Duración:** **{plan['days']} días**\n"
        f"🔗 **Links simultáneos:** Hasta {plan['max_links']}\n\n"
        f"📝 **ID de transacción:** `{tx_ref}`\n\n"
        f"💳 **Puedes pagar con las siguientes criptomonedas:**\n"
    )

    for crypto, address in CRYPTO_ADDRESSES.items():
        text += f"\n🔹 **{crypto}:**\n`{address}`"

    text += "\n\n📩 **Después de realizar el pago, usa el comando:**\n"
    text += f"`/confirmar {tx_ref}`\n\n"
    text += "⚠️ *El bot verificará automáticamente el pago en la blockchain y activará tu VIP.*"

    keyboard = [
        [InlineKeyboardButton("🔄 Verificar pago manualmente", callback_data="check_payment")],
        [InlineKeyboardButton("🏠 Volver a VIP", callback_data="vip_menu")]
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica manualmente si un pago pendiente fue completado"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    pending_vip = context.user_data.get('pending_vip')
    tx_ref = context.user_data.get('vip_tx_ref')
    
    if not pending_vip or not tx_ref:
        await query.edit_message_text(
            "❌ No hay ninguna compra pendiente.\n\n"
            "Usa /vip para seleccionar un plan.",
            parse_mode='Markdown'
        )
        return
    
    plan = VIP_PLANS.get(pending_vip)
    
    text = (
        f"🔄 **Verificación de pago**\n\n"
        f"📝 **ID de transacción:** `{tx_ref}`\n"
        f"💰 **Plan:** {plan['name']} (${plan['price_usd']} USD)\n\n"
        f"⚠️ **Por ahora, la verificación es manual.**\n\n"
        f"📩 **Después de realizar el pago, contacta a @danyvg56 con:**\n"
        f"• El hash de la transacción\n"
        f"• Tu ID de transacción: `{tx_ref}`\n\n"
        f"✅ Una vez confirmado, se activará tu VIP."
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Ya pagué, contactar admin", url="https://t.me/danyvg56")],
        [InlineKeyboardButton("🏠 Volver a VIP", callback_data="vip_menu")]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def confirm_payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para confirmar pago manualmente (solo admin)"""
    user_id = update.effective_user.id
    
    # Verificar que es el admin
    if user_id != 5057900537:  # Tu ID de Telegram
        await update.message.reply_text("⛔ Solo administradores pueden usar este comando.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "📝 **Uso:** `/confirmar [ID_TRANSACCION]`\n\n"
            "Ejemplo: `/confirmar VIP1_123456789_20250327120000`",
            parse_mode='Markdown'
        )
        return
    
    tx_ref = args[0]
    
    # Extraer información del tx_ref (formato: VIP{level}_{user_id}_{timestamp})
    try:
        parts = tx_ref.split('_')
        if len(parts) >= 3 and parts[0].startswith('VIP'):
            level = int(parts[0][3:])
            target_user_id = int(parts[1])
            
            plan = VIP_PLANS.get(level)
            if not plan:
                await update.message.reply_text("❌ Plan no válido en la referencia.")
                return
            
            # Activar VIP para el usuario
            activate_vip(target_user_id, level, plan['days'], plan['reputation'])
            
            await update.message.reply_text(
                f"✅ **VIP activado correctamente!**\n\n"
                f"👤 Usuario ID: `{target_user_id}`\n"
                f"⭐ Plan: {plan['name']}\n"
                f"🎁 +{plan['reputation']} reputación\n"
                f"⏳ {plan['days']} días de promoción\n\n"
                f"📝 Referencia: `{tx_ref}`",
                parse_mode='Markdown'
            )
            
            # Notificar al usuario
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"🎉 **¡Tu VIP ha sido activado!**\n\n"
                         f"⭐ Plan: {plan['name']}\n"
                         f"🎁 +{plan['reputation']} reputación\n"
                         f"⏳ {plan['days']} días de promoción\n\n"
                         f"Usa /start para ver tu nuevo estado.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error notificando al usuario: {e}")
                
        else:
            await update.message.reply_text("❌ Formato de referencia inválido.")
            
    except Exception as e:
        logger.error(f"Error procesando confirmación: {e}")
        await update.message.reply_text(f"❌ Error: {e}")
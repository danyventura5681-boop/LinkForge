import logging
import hashlib
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.database import get_user, activate_vip, register_payment, get_user_links
from config import VIP_PLANS, TRX_ADDRESS, TRX_PER_USD

logger = logging.getLogger(__name__)

# Diccionario de direcciones de criptomonedas
CRYPTO_ADDRESSES = {
    "TRX": TRX_ADDRESS,
    "TON": "UQBJG1Dh1cRpHZqAMJ0qgD0CDyIUo0y2u82oG--pMm0G0jkl",
    "ETH": "0x1526Fa97f7E7d8A0AB76F3fb94F97A3E1281cA81",
    "BTC": "bc1q4netsk5cnyszu4s036nhj26pm3a405j6wnjnsy",
    "BNB": "0x1526Fa97f7E7d8A0AB76F3fb94F97A3E1281cA81",
    "SOL": "9ncG6PPVVPueqELv3rC8JeNUbnkbhdQ9E522BDJqZvF"
}

# Estados para conversación de pago manual
WAITING_PAYMENT_AMOUNT, WAITING_PAYMENT_ADDRESS, WAITING_PAYMENT_TX = range(3)

def get_trx_amount(usd_amount):
    """Convierte USD a TRX según tasa fija"""
    return usd_amount * TRX_PER_USD

def generate_payment_hash(user_id, level, amount_usd):
    """Genera un hash único para el pago (para tracking)"""
    unique_string = f"{user_id}_{level}_{amount_usd}_{int(time.time())}"
    return hashlib.sha256(unique_string.encode()).hexdigest()[:16]

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
    logger.info(f"⭐ vip_menu: Usuario {user_id} solicitó planes VIP")

    if user:
        current_vip = user["vip_level"] if user["vip_level"] else 0
        vip_expires = user["vip_expires_at"] if user["vip_expires_at"] else None
        reputation = user["reputation"] if user["reputation"] else 0
    else:
        current_vip = 0
        vip_expires = None
        reputation = 0

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
        trx_amount = get_trx_amount(plan['price_usd'])
        text += f"\n**{plan['name']}** - **${plan['price_usd']} USD** (≈ {trx_amount} TRX)\n"
        text += f"🎁 +{plan['reputation']} reputación\n"
        text += f"⏳ {plan['days']} días de promoción\n"
        text += f"🔗 Hasta {plan['max_links']} links simultáneos\n"

        # Si es mayor que el nivel actual, mostrar botón
        if level > current_vip:
            keyboard.append([InlineKeyboardButton(
                f"💰 Comprar {plan['name']} (${plan['price_usd']} ≈ {trx_amount} TRX)",
                callback_data=f"buy_vip_{level}"
            )])
        else:
            text += f"✅ *Ya tienes este nivel o superior*\n"

    if current_vip > 0:
        text += f"\n📌 **Tus links activos:** {len(get_user_links(user_id))}/{3 if current_vip > 0 else 1}"

    keyboard.append([InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")])

    # Si viene de un callback (botón), usar query.edit_message_text
    if update.callback_query:
        query = update.callback_query
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        # Si viene de un comando /vip
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    logger.info(f"⭐ Menú VIP mostrado para usuario {user_id}")

async def buy_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra instrucciones de pago para VIP con TRX."""
    query = update.callback_query
    await query.answer()

    level = int(query.data.split("_")[2])
    plan = VIP_PLANS.get(level)
    logger.info(f"💰 buy_vip: Usuario {query.from_user.id} comprando {plan['name'] if plan else 'plan inválido'}")

    if not plan:
        await query.edit_message_text(
            "❌ Plan no válido.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver a VIP", callback_data="vip_menu")]])
        )
        return

    user_id = query.from_user.id
    expected_trx = get_trx_amount(plan['price_usd'])
    payment_hash = generate_payment_hash(user_id, level, plan['price_usd'])

    # Guardar plan seleccionado en contexto
    context.user_data['pending_vip'] = level
    context.user_data['payment_hash'] = payment_hash

    # Registrar pago pendiente en la base de datos
    try:
        register_payment(
            user_id=user_id,
            tx_hash=payment_hash,
            amount_usd=plan['price_usd'],
            crypto_amount=expected_trx,
            crypto_currency="TRX",
            vip_level=level
        )
        logger.info(f"✅ Pago registrado: {payment_hash} para usuario {user_id}")
    except Exception as e:
        logger.error(f"Error registrando pago: {e}")

    text = (
        f"⭐ **Compra de {plan['name']}** ⭐\n\n"
        f"💰 **Precio:** **${plan['price_usd']} USD** ≈ **{expected_trx} TRX**\n"
        f"🎁 **Recompensa:** **+{plan['reputation']} reputación**\n"
        f"⏳ **Duración:** **{plan['days']} días**\n"
        f"🔗 **Links simultáneos:** Hasta {plan['max_links']}\n\n"
        f"💳 **Envía exactamente {expected_trx} TRX a esta dirección:**\n"
        f"`{CRYPTO_ADDRESSES['TRX']}`\n\n"
        f"📝 **Tu código de pago:** `{payment_hash}`\n\n"
        f"⚠️ **Importante:** Incluye el código de pago en el **memo** de la transacción para activación automática.\n\n"
        f"✅ Una vez enviado, el bot verificará automáticamente el pago y activará tu VIP.\n"
        f"📌 Si no puedes incluir memo, usa el botón **'✅ Ya pagué'** para verificación manual."
    )

    keyboard = [
        [InlineKeyboardButton("🔄 Verificar pago", callback_data="check_payment")],
        [InlineKeyboardButton("✅ Ya pagué (verificación manual)", callback_data="manual_payment")],
        [InlineKeyboardButton("◀️ Volver a VIP", callback_data="vip_menu")]
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def manual_payment_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de verificación manual de pago."""
    query = update.callback_query
    await query.answer()
    
    pending_vip = context.user_data.get('pending_vip')
    payment_hash = context.user_data.get('payment_hash')
    
    if not pending_vip or not payment_hash:
        await query.edit_message_text(
            "❌ No hay ninguna compra pendiente.\n\nUsa el botón 'VIP' para seleccionar un plan.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver a VIP", callback_data="vip_menu")]])
        )
        return
    
    plan = VIP_PLANS.get(pending_vip)
    expected_trx = get_trx_amount(plan['price_usd'])
    
    text = (
        f"✅ **Verificación manual de pago**\n\n"
        f"Para verificar tu pago, responde las siguientes preguntas:\n\n"
        f"1️⃣ **¿Cuántos TRX enviaste?** (debes enviar exactamente {expected_trx} TRX)\n"
        f"2️⃣ **¿Desde qué dirección enviaste?** (tu wallet TRX)\n"
        f"3️⃣ **Hash de la transacción** (opcional, pero ayuda)\n\n"
        f"Por favor, **envía el monto enviado** (ejemplo: 10):"
    )
    
    await query.edit_message_text(text, parse_mode='Markdown')
    return WAITING_PAYMENT_AMOUNT

async def manual_payment_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el monto enviado."""
    try:
        amount = float(update.message.text.strip())
        context.user_data['manual_amount'] = amount
        await update.message.reply_text(
            f"✅ Monto registrado: {amount} TRX\n\n"
            f"2️⃣ **¿Desde qué dirección enviaste?** (tu wallet TRX)"
        )
        return WAITING_PAYMENT_ADDRESS
    except ValueError:
        await update.message.reply_text("❌ Ingresa un número válido (ejemplo: 10)")
        return WAITING_PAYMENT_AMOUNT

async def manual_payment_get_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe la dirección del remitente."""
    address = update.message.text.strip()
    context.user_data['manual_address'] = address
    await update.message.reply_text(
        f"✅ Dirección registrada: `{address}`\n\n"
        f"3️⃣ **Hash de la transacción** (opcional, escribe 'ninguno' si no lo tienes)"
    )
    return WAITING_PAYMENT_TX

async def manual_payment_get_tx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el hash y envía la información al admin."""
    tx_hash = update.message.text.strip()
    if tx_hash.lower() == 'ninguno':
        tx_hash = "No proporcionado"
    
    pending_vip = context.user_data.get('pending_vip')
    payment_hash = context.user_data.get('payment_hash')
    amount = context.user_data.get('manual_amount')
    address = context.user_data.get('manual_address')
    
    plan = VIP_PLANS.get(pending_vip)
    expected_trx = get_trx_amount(plan['price_usd'])
    
    # Enviar notificación al admin
    admin_id = 5057900537  # Tu ID
    admin_text = (
        f"🛡️ **Nuevo pago pendiente de verificación** 🛡️\n\n"
        f"👤 Usuario: {update.effective_user.id}\n"
        f"👤 Nombre: {update.effective_user.first_name}\n"
        f"⭐ Plan: {plan['name']}\n"
        f"💰 Monto enviado: {amount} TRX (esperado: {expected_trx} TRX)\n"
        f"🏦 Dirección: `{address}`\n"
        f"🔗 Hash TX: `{tx_hash}`\n"
        f"📝 Código pago: `{payment_hash}`\n\n"
        f"Para activar VIP, usa: `/confirmar {payment_hash}`"
    )
    
    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=admin_text,
            parse_mode='Markdown'
        )
        await update.message.reply_text(
            f"✅ **¡Información enviada!**\n\n"
            f"El administrador revisará tu pago y activará tu VIP en breve.\n\n"
            f"📝 Tu código de pago: `{payment_hash}`\n\n"
            f"Puedes contactar a @danyvg56 si tienes alguna duda.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]]),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error enviando notificación al admin: {e}")
        await update.message.reply_text(
            "❌ Error al enviar la información. Contacta a @danyvg56 directamente.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
        )
    
    # Limpiar contexto
    context.user_data.pop('pending_vip', None)
    context.user_data.pop('payment_hash', None)
    context.user_data.pop('manual_amount', None)
    context.user_data.pop('manual_address', None)
    
    return ConversationHandler.END

async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica manualmente si un pago pendiente fue completado"""
    query = update.callback_query
    await query.answer()
    logger.info(f"🔄 check_payment: Usuario {query.from_user.id} verificando pago")

    user_id = query.from_user.id
    pending_vip = context.user_data.get('pending_vip')
    payment_hash = context.user_data.get('payment_hash')

    if not pending_vip or not payment_hash:
        await query.edit_message_text(
            "❌ No hay ninguna compra pendiente.\n\n"
            "Usa el botón 'VIP' para seleccionar un plan.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver a VIP", callback_data="vip_menu")]]),
            parse_mode='Markdown'
        )
        return

    plan = VIP_PLANS.get(pending_vip)
    expected_trx = get_trx_amount(plan['price_usd'])

    text = (
        f"🔄 **Verificación de pago**\n\n"
        f"📝 **Código de pago:** `{payment_hash}`\n"
        f"💰 **Plan:** {plan['name']} (${plan['price_usd']} USD ≈ {expected_trx} TRX)\n"
        f"🏦 **Dirección:** `{CRYPTO_ADDRESSES['TRX']}`\n\n"
        f"⚠️ **Verificación automática:**\n"
        f"El bot revisa los pagos automáticamente.\n\n"
        f"📩 **Si ya enviaste el pago y no se ha activado:**\n"
        f"1. Verifica que enviaste exactamente {expected_trx} TRX\n"
        f"2. Verifica que incluiste `{payment_hash}` en el memo\n"
        f"3. Contacta a @danyvg56 con tu código de pago"
    )

    keyboard = [
        [InlineKeyboardButton("✅ Contactar admin", url="https://t.me/danyvg56")],
        [InlineKeyboardButton("🔄 Reintentar verificación", callback_data="check_payment_retry")],
        [InlineKeyboardButton("◀️ Volver a VIP", callback_data="vip_menu")]
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def check_payment_retry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reintenta verificar el pago pendiente"""
    query = update.callback_query
    await query.answer()
    logger.info(f"🔄 check_payment_retry: Usuario {query.from_user.id} reintentando verificación")

    user_id = query.from_user.id
    pending_vip = context.user_data.get('pending_vip')
    payment_hash = context.user_data.get('payment_hash')

    if not pending_vip or not payment_hash:
        await query.edit_message_text(
            "❌ No hay pago pendiente para verificar.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver a VIP", callback_data="vip_menu")]])
        )
        return

    # Verificar en base de datos si el pago ya fue confirmado
    from database.database import get_payment_by_hash
    payment = get_payment_by_hash(payment_hash)

    if payment and payment["status"] == "confirmed":
        plan = VIP_PLANS.get(pending_vip)
        await query.edit_message_text(
            f"🎉 **¡Pago confirmado!**\n\n"
            f"⭐ Tu {plan['name']} ha sido activado.\n"
            f"🎁 +{plan['reputation']} reputación\n"
            f"⏳ {plan['days']} días de promoción\n\n"
            f"Usa el botón para ver tu nuevo estado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Ir al Panel Principal", callback_data="volver_menu")]]),
            parse_mode='Markdown'
        )
        context.user_data.pop('pending_vip', None)
        context.user_data.pop('payment_hash', None)
    else:
        await query.edit_message_text(
            f"⏳ **Pago aún no confirmado.**\n\n"
            f"📝 Código: `{payment_hash}`\n\n"
            f"Si ya enviaste el pago, espera unos minutos y vuelve a intentar.\n\n"
            f"💡 Si el problema persiste, contacta al administrador.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Contactar admin", url="https://t.me/danyvg56")],
                [InlineKeyboardButton("◀️ Volver a VIP", callback_data="vip_menu")]
            ]),
            parse_mode='Markdown'
        )

async def confirm_payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para confirmar pago manualmente (solo admin)"""
    user_id = update.effective_user.id

    # Verificar que es el admin
    if user_id != 5057900537:
        await update.message.reply_text(
            "⛔ Solo administradores pueden usar este comando.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver al Menú", callback_data="volver_menu")]])
        )
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "📝 **Uso:** `/confirmar [CODIGO_PAGO]`\n\n"
            "Ejemplo: `/confirmar a1b2c3d4e5f6g7h8`\n\n"
            "También puedes usar el formato antiguo: `/confirmar VIP1_123456789_20250327120000`",
            parse_mode='Markdown'
        )
        return

    payment_ref = args[0]
    logger.info(f"🔧 confirm_payment_command: Admin confirmando pago {payment_ref}")

    # Buscar en la base de datos por código de pago
    from database.database import get_payment_by_hash
    payment = get_payment_by_hash(payment_ref)

    # Si no se encuentra, intentar formato antiguo (VIP{level}_{user_id}_{timestamp})
    if not payment and payment_ref.startswith("VIP"):
        try:
            parts = payment_ref.split('_')
            if len(parts) >= 3 and parts[0].startswith('VIP'):
                level = int(parts[0][3:])
                target_user_id = int(parts[1])

                plan = VIP_PLANS.get(level)
                if plan:
                    activate_vip(target_user_id, level, plan['days'], plan['reputation'])

                    await update.message.reply_text(
                        f"✅ **VIP activado correctamente!**\n\n"
                        f"👤 Usuario ID: `{target_user_id}`\n"
                        f"⭐ Plan: {plan['name']}\n"
                        f"🎁 +{plan['reputation']} reputación\n"
                        f"⏳ {plan['days']} días de promoción",
                        parse_mode='Markdown'
                    )

                    try:
                        await context.bot.send_message(
                            chat_id=target_user_id,
                            text=f"🎉 **¡Tu VIP ha sido activado!**\n\n"
                                 f"⭐ Plan: {plan['name']}\n"
                                 f"🎁 +{plan['reputation']} reputación\n"
                                 f"⏳ {plan['days']} días de promoción\n\n"
                                 f"Usa el botón para ver tu nuevo estado.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Ir al Panel Principal", callback_data="volver_menu")]]),
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"Error notificando al usuario: {e}")
                    return
        except Exception as e:
            logger.error(f"Error procesando formato antiguo: {e}")

    # Si encontramos el pago en la base de datos
    if payment and payment["status"] == "pending":
        plan = VIP_PLANS.get(payment["vip_level"])
        if plan:
            from database.database import confirm_payment
            confirm_payment(payment_ref)
            activate_vip(payment["user_id"], payment["vip_level"], plan['days'], plan['reputation'])

            await update.message.reply_text(
                f"✅ **Pago confirmado y VIP activado!**\n\n"
                f"👤 Usuario ID: `{payment['user_id']}`\n"
                f"⭐ Plan: {plan['name']}\n"
                f"🎁 +{plan['reputation']} reputación\n"
                f"💰 Monto: ${plan['price_usd']} USD",
                parse_mode='Markdown'
            )

            try:
                await context.bot.send_message(
                    chat_id=payment["user_id"],
                    text=f"🎉 **¡Pago confirmado!**\n\n"
                         f"⭐ Tu {plan['name']} ha sido activado.\n"
                         f"🎁 +{plan['reputation']} reputación\n"
                         f"⏳ {plan['days']} días de promoción\n\n"
                         f"Usa el botón para ver tu nuevo estado.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Ir al Panel Principal", callback_data="volver_menu")]]),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error notificando al usuario: {e}")
        else:
            await update.message.reply_text("❌ Plan no válido en el pago.")
    elif payment and payment["status"] == "confirmed":
        await update.message.reply_text("ℹ️ Este pago ya fue confirmado anteriormente.")
    else:
        await update.message.reply_text(f"❌ No se encontró ningún pago pendiente con el código: `{payment_ref}`", parse_mode='Markdown')
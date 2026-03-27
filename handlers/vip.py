import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import get_user, activate_vip

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

async def vip_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el menú de planes VIP."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    text = (
        f"💎 **Planes VIP** 💎\n\n"
        f"Actualmente eres **Nivel {user['vip_level'] or 0}**\n"
        f"Reputación: {user['reputation']} pts\n\n"
        f"**Planes disponibles:**\n"
    )
    
    keyboard = []
    for level, plan in VIP_PLANS.items():
        text += f"\n**{plan['name']}** - ${plan['price_usd']} USD\n"
        text += f"🎁 +{plan['reputation']} reputación\n"
        text += f"⏳ {plan['days']} días de promoción\n"
        text += f"🔗 Hasta {plan['max_links']} links simultáneos\n"
        keyboard.append([InlineKeyboardButton(
            f"💰 Comprar {plan['name']} (${plan['price_usd']})",
            callback_data=f"buy_vip_{level}"
        )])
    
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
    
    text = (
        f"💎 **Compra de {plan['name']}** 💎\n\n"
        f"💰 Precio: **${plan['price_usd']} USD**\n"
        f"🎁 Recompensa: **+{plan['reputation']} reputación**\n"
        f"⏳ Duración: **{plan['days']} días**\n\n"
        f"**Puedes pagar con las siguientes criptomonedas:**\n"
    )
    
    for crypto, address in CRYPTO_ADDRESSES.items():
        text += f"\n🔹 **{crypto}:**\n`{address}`"
    
    text += "\n\n📩 **Después de realizar el pago, envía el hash de la transacción con /confirmar [HASH]**\n\n"
    text += "⚠️ *La activación es manual por ahora. Pronto será automática.*"
    
    keyboard = [[InlineKeyboardButton("🏠 Volver a VIP", callback_data="vip_menu")]]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
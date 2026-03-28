import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env (solo para desarrollo local)
load_dotenv()

# Token del bot
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN no está definido en las variables de entorno")

# Direcciones de criptomonedas para pagos VIP
TRX_ADDRESS = "TK2K6W7vFehHLB6eQ9CPPjcJ1E6ErCu12Y"
TON_ADDRESS = "UQBJG1Dh1cRpHZqAMJ0qgD0CDyIUo0y2u82oG--pMm0G0jkl"
ETH_ADDRESS = "0x1526Fa97f7E7d8A0AB76F3fb94F97A3E1281cA81"
BTC_ADDRESS = "bc1q4netsk5cnyszu4s036nhj26pm3a405j6wnjnsy"
BNB_ADDRESS = "0x1526Fa97f7E7d8A0AB76F3fb94F97A3E1281cA81"
SOL_ADDRESS = "9ncG6PPVVPueqELv3rC8JeNUbnkbhdQ9E522BDJqZvF"

# Tasa de cambio fija (1 USD = 10 TRX)
TRX_PER_USD = 10

# Planes VIP
VIP_PLANS = {
    1: {"name": "VIP 1", "price_usd": 1, "reputation": 500, "days": 30, "max_links": 3},
    2: {"name": "VIP 2", "price_usd": 5, "reputation": 2800, "days": 30, "max_links": 3},
    3: {"name": "VIP 3", "price_usd": 10, "reputation": 6000, "days": 30, "max_links": 3}
}

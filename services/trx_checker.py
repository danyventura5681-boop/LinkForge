import logging
import requests
from datetime import datetime, timedelta
from database.database import get_pending_payments, confirm_payment, activate_vip
from config import TRX_ADDRESS, TRX_PER_USD

logger = logging.getLogger(__name__)

# Configuración de TronGrid API (gratis)
TRONGRID_API = "https://api.trongrid.io"

def get_expected_trx_amount(usd_amount):
    """Calcula la cantidad de TRX esperada según el monto en USD"""
    return usd_amount * TRX_PER_USD

def check_trx_payment(tx_hash):
    """Verifica una transacción específica en TronGrid"""
    try:
        url = f"{TRONGRID_API}/v1/transactions/{tx_hash}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                tx = data["data"][0]

                # Verificar que la transacción fue a nuestra dirección
                contract = tx.get("raw_data", {}).get("contract", [{}])[0]
                value = contract.get("parameter", {}).get("value", {})
                to_address = value.get("to_address")

                if to_address and to_address == TRX_ADDRESS:
                    # Obtener cantidad en TRX (convertir de SUN a TRX: 1 TRX = 1,000,000 SUN)
                    amount_sun = value.get("amount", 0)
                    amount_trx = amount_sun / 1_000_000

                    return {
                        "success": True,
                        "amount_trx": amount_trx,
                        "from_address": value.get("owner_address"),
                        "timestamp": tx.get("raw_data", {}).get("timestamp", 0)
                    }

        return {"success": False, "error": "Transacción no encontrada"}

    except Exception as e:
        logger.error(f"Error verificando transacción {tx_hash}: {e}")
        return {"success": False, "error": str(e)}

def scan_pending_payments():
    """Escanea pagos pendientes y verifica si fueron completados"""
    pending_payments = get_pending_payments()
    results = []

    for payment in pending_payments:
        # payment es un objeto SQLAlchemy, NO un diccionario
        tx_hash = payment.tx_hash  # CAMBIADO: payment["tx_hash"] -> payment.tx_hash
        result = check_trx_payment(tx_hash)

        if result["success"]:
            # Verificar que el monto coincide con el esperado
            expected_trx = get_expected_trx_amount(payment.amount_usd)  # CAMBIADO
            received_trx = result["amount_trx"]

            # Tolerancia del 5% para variaciones de precio
            if abs(received_trx - expected_trx) <= expected_trx * 0.05:
                # Confirmar pago y activar VIP
                confirm_payment(tx_hash)
                # Calcular reputación según nivel VIP
                bonus_map = {1: 500, 2: 2800, 3: 6000}
                reputation_bonus = bonus_map.get(payment.vip_level, 0)  # CAMBIADO
                activate_vip(payment.user_id, payment.vip_level, 30, reputation_bonus)  # CAMBIADO
                results.append({
                    "success": True,
                    "user_id": payment.user_id,  # CAMBIADO
                    "vip_level": payment.vip_level,  # CAMBIADO
                    "tx_hash": tx_hash
                })
            else:
                results.append({
                    "success": False,
                    "user_id": payment.user_id,  # CAMBIADO
                    "error": f"Monto incorrecto. Esperado: {expected_trx} TRX, Recibido: {received_trx} TRX"
                })
        else:
            results.append({
                "success": False,
                "user_id": payment.user_id,  # CAMBIADO
                "error": result.get("error", "No confirmado")
            })

    return results
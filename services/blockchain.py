import logging
import requests
from database.database import register_payment, confirm_payment, get_payment_by_hash, activate_vip
from config import TRX_ADDRESS, TRX_PER_USD

logger = logging.getLogger(__name__)

# Configuración de APIs
TRONGRID_API = "https://api.trongrid.io"
BSCSCAN_API = "https://api.bscscan.com/api"

def get_expected_trx_amount(usd_amount):
    """Convierte USD a TRX según tasa fija"""
    return usd_amount * TRX_PER_USD

def verify_trx_transaction(tx_hash: str, expected_amount: float, recipient: str) -> bool:
    """
    Verifica una transacción en TRX usando TronGrid.
    Retorna True si la transacción es válida y coincide con los datos esperados.
    """
    try:
        url = f"{TRONGRID_API}/v1/transactions/{tx_hash}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Error en TronGrid: {response.status_code}")
            return False

        data = response.json()
        if not data.get("data"):
            logger.warning(f"Transacción {tx_hash} no encontrada")
            return False

        tx = data["data"][0]
        contract = tx.get("raw_data", {}).get("contract", [{}])[0]
        value = contract.get("parameter", {}).get("value", {})
        
        to_address = value.get("to_address")
        if not to_address:
            logger.warning(f"No se encontró dirección de destino en {tx_hash}")
            return False
        
        # Convertir dirección a formato estándar
        # TronGrid devuelve en base64, necesitamos convertir
        import base64
        decoded_address = base64.b64decode(to_address).hex()
        # Los primeros 2 bytes son el prefijo (0x41 para TRX)
        if len(decoded_address) > 2:
            formatted_address = "T" + decoded_address[2:]
        else:
            formatted_address = to_address
        
        if formatted_address != recipient and to_address != recipient:
            logger.warning(f"Dirección destino incorrecta. Esperada: {recipient}, recibida: {formatted_address}")
            return False
        
        amount_sun = value.get("amount", 0)
        amount_trx = amount_sun / 1_000_000
        
        # Tolerancia del 5% para variaciones
        if abs(amount_trx - expected_amount) <= expected_amount * 0.05:
            logger.info(f"✅ Transacción {tx_hash} verificada: {amount_trx} TRX")
            return True
        else:
            logger.warning(f"Monto incorrecto. Esperado: {expected_amount}, recibido: {amount_trx}")
            return False
            
    except Exception as e:
        logger.error(f"Error verificando TRX {tx_hash}: {e}")
        return False

def verify_bsc_transaction(tx_hash: str, expected_amount: float, recipient: str, api_key: str = "") -> bool:
    """Verifica una transacción en BSC usando BSCScan API."""
    try:
        url = f"{BSCSCAN_API}?module=transaction&action=gettxreceiptstatus&txhash={tx_hash}&apikey={api_key}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            return False
        
        data = response.json()
        if data.get("status") != "1":
            return False
        
        # Obtener detalles de la transacción
        url_tx = f"{BSCSCAN_API}?module=account&action=txlist&txhash={tx_hash}&apikey={api_key}"
        response_tx = requests.get(url_tx, timeout=10)
        tx_data = response_tx.json()
        
        if tx_data.get("status") != "1":
            return False
        
        for tx in tx_data.get("result", []):
            if tx.get("to", "").lower() == recipient.lower():
                amount_wei = int(tx.get("value", 0))
                amount_bnb = amount_wei / 1e18
                if abs(amount_bnb - expected_amount) <= expected_amount * 0.05:
                    return True
        
        return False
    except Exception as e:
        logger.error(f"Error verificando BSC {tx_hash}: {e}")
        return False

def process_payment(tx_hash: str, user_id: int, amount_usd: int, crypto_amount: float, crypto_currency: str, vip_level: int):
    """
    Registra un pago pendiente y activa VIP si es válido.
    """
    # Registrar pago pendiente
    register_payment(user_id, tx_hash, amount_usd, crypto_amount, crypto_currency, vip_level)
    logger.info(f"📝 Pago registrado: {tx_hash} para usuario {user_id}")

    # Verificación automática (si se implementa)
    # if crypto_currency == "TRX":
    #     expected_trx = get_expected_trx_amount(amount_usd)
    #     if verify_trx_transaction(tx_hash, expected_trx, TRX_ADDRESS):
    #         confirm_payment(tx_hash)
    #         activate_vip(user_id, vip_level, 30, get_reputation_bonus(vip_level))
    #         logger.info(f"✅ Pago {tx_hash} verificado y VIP activado")

def get_reputation_bonus(vip_level: int) -> int:
    """Obtiene el bono de reputación según el nivel VIP"""
    bonuses = {1: 500, 2: 2800, 3: 6000}
    return bonuses.get(vip_level, 0)

def scan_pending_payments():
    """Escanea pagos pendientes y verifica automáticamente"""
    from database.database import get_pending_payments
    pending = get_pending_payments()
    results = []
    
    for payment in pending:
        # payment es objeto SQLAlchemy
        if payment.crypto_currency == "TRX":
            expected = get_expected_trx_amount(payment.amount_usd)
            if verify_trx_transaction(payment.tx_hash, expected, TRX_ADDRESS):
                confirm_payment(payment.tx_hash)
                activate_vip(payment.user_id, payment.vip_level, 30, get_reputation_bonus(payment.vip_level))
                results.append({"success": True, "user_id": payment.user_id, "tx_hash": payment.tx_hash})
                logger.info(f"✅ Pago automático confirmado: {payment.tx_hash}")
    
    return results
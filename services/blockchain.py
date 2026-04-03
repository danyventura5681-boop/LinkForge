import logging
import requests
from datetime import datetime, timedelta
from database.database import register_payment, confirm_payment, get_payment_by_hash, activate_vip, get_pending_payments
from config import TRX_ADDRESS, TRX_PER_USD

logger = logging.getLogger(__name__)

# Configuración de APIs
TRONGRID_API = "https://api.trongrid.io"
BSCSCAN_API = "https://api.bscscan.com/api"

# Direcciones TRON conocidas para validación
TRON_PREFIX = "41"  # Prefijo para direcciones TRON

def get_expected_trx_amount(usd_amount):
    """Convierte USD a TRX según tasa fija"""
    return usd_amount * TRX_PER_USD

def hex_to_tron_address(hex_address: str) -> str:
    """Convierte dirección hex a formato TRON (base58)"""
    try:
        import base58
        # Si ya tiene el prefijo 41, remover
        if hex_address.startswith("41"):
            hex_clean = hex_address[2:]
        else:
            hex_clean = hex_address
        
        # Agregar prefijo TRON
        full_hex = "41" + hex_clean
        
        # Convertir de hex a bytes
        bytes_addr = bytes.fromhex(full_hex)
        
        # Codificar a base58
        tron_addr = base58.b58encode_check(bytes_addr).decode()
        logger.info(f"✅ Dirección convertida: {hex_address} → {tron_addr}")
        return tron_addr
    except Exception as e:
        logger.error(f"❌ Error convirtiendo dirección: {e}")
        return ""

def verify_trx_transaction(tx_hash: str, expected_amount: float, recipient: str) -> bool:
    """
    Verifica una transacción en TRX usando TronGrid.
    Retorna True si:
    - La transacción existe
    - Está confirmada (success = true)
    - Tiene el monto correcto (±5%)
    - Va a la dirección correcta
    """
    try:
        logger.info(f"🔍 Verificando TRX tx: {tx_hash[:16]}...")
        
        url = f"{TRONGRID_API}/v1/transactions/{tx_hash}"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            logger.error(f"❌ TronGrid error: {response.status_code}")
            return False

        data = response.json()
        if "data" not in data or not data.get("data"):
            logger.warning(f"❌ Transacción no encontrada: {tx_hash}")
            return False

        tx = data["data"][0]
        
        # ✅ Verificar que la tx esté confirmada
        if not tx.get("ret", [{}])[0].get("contractRet") == "Success":
            logger.warning(f"⚠️ Transacción no confirmada: {tx_hash}")
            return False
        
        # ✅ Verificar que sea reciente (últimas 72 horas)
        block_timestamp = tx.get("block_timestamp", 0)
        if block_timestamp:
            tx_time = datetime.fromtimestamp(block_timestamp / 1000)
            age = datetime.utcnow() - tx_time
            if age > timedelta(hours=72):
                logger.warning(f"⚠️ Transacción muy antigua: {age.days} días")
                return False

        # Obtener datos del contrato
        contract = tx.get("raw_data", {}).get("contract", [{}])[0]
        contract_type = contract.get("type", "")
        value = contract.get("parameter", {}).get("value", {})

        # ✅ Debe ser una transacción TRX directa (TransferContract)
        if contract_type != "TransferContract":
            logger.warning(f"⚠️ Tipo de contrato incorrecto: {contract_type}")
            return False

        to_address_hex = value.get("to_address", "")
        if not to_address_hex:
            logger.warning(f"❌ No se encontró dirección destino")
            return False

        # Convertir dirección hex a TRON
        to_address_tron = hex_to_tron_address(to_address_hex)
        
        logger.info(f"📍 Dirección destino: {to_address_tron}")
        logger.info(f"📍 Dirección esperada: {recipient}")

        if to_address_tron != recipient:
            logger.warning(f"❌ Dirección incorrecta. Esperada: {recipient}, recibida: {to_address_tron}")
            return False

        # Verificar monto
        amount_sun = value.get("amount", 0)
        amount_trx = amount_sun / 1_000_000

        tolerance = expected_amount * 0.05
        if abs(amount_trx - expected_amount) > tolerance:
            logger.warning(f"❌ Monto incorrecto. Esperado: {expected_amount} TRX, recibido: {amount_trx} TRX")
            return False

        logger.info(f"✅ Transacción verificada: {amount_trx} TRX")
        return True

    except Exception as e:
        logger.error(f"❌ Error verificando TRX {tx_hash}: {e}")
        return False

def verify_bsc_transaction(tx_hash: str, expected_amount: float, recipient: str, api_key: str = "") -> bool:
    """Verifica una transacción en BSC usando BSCScan API."""
    try:
        logger.info(f"🔍 Verificando BSC tx: {tx_hash[:16]}...")
        
        if not api_key:
            logger.warning("⚠️ No hay BSCScan API key configurada")
            return False
        
        url = f"{BSCSCAN_API}?module=transaction&action=gettxreceiptstatus&txhash={tx_hash}&apikey={api_key}"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            logger.error(f"❌ BSCScan error: {response.status_code}")
            return False

        data = response.json()
        
        # ✅ Verificar que esté confirmada
        if data.get("status") != "1":
            logger.warning(f"⚠️ Transacción no confirmada en BSC")
            return False

        if data.get("result", {}).get("isError") == "1":
            logger.warning(f"⚠️ Transacción falló en BSC")
            return False

        # Obtener detalles de la transacción
        url_tx = f"{BSCSCAN_API}?module=account&action=txlist&txhash={tx_hash}&apikey={api_key}"
        response_tx = requests.get(url_tx, timeout=10)
        tx_data = response_tx.json()

        if tx_data.get("status") != "1":
            logger.warning(f"⚠️ No se encontró tx en BSC")
            return False

        for tx in tx_data.get("result", []):
            if tx.get("to", "").lower() == recipient.lower():
                amount_wei = int(tx.get("value", 0))
                amount_bnb = amount_wei / 1e18
                
                tolerance = expected_amount * 0.05
                if abs(amount_bnb - expected_amount) <= tolerance:
                    logger.info(f"✅ Transacción BSC verificada: {amount_bnb} BNB")
                    return True

        logger.warning(f"❌ Transacción a dirección incorrecta")
        return False
        
    except Exception as e:
        logger.error(f"❌ Error verificando BSC {tx_hash}: {e}")
        return False

def process_payment(tx_hash: str, user_id: int, amount_usd: int, crypto_amount: float, crypto_currency: str, vip_level: int):
    """
    Registra un pago pendiente.
    La verificación se hace después con scan_pending_payments()
    """
    try:
        register_payment(user_id, tx_hash, amount_usd, crypto_amount, crypto_currency, vip_level)
        logger.info(f"✅ Pago registrado: {tx_hash} para usuario {user_id} ({amount_usd}$ → VIP{vip_level})")
    except Exception as e:
        logger.error(f"❌ Error registrando pago: {e}")

def get_reputation_bonus(vip_level: int) -> int:
    """Obtiene el bono de reputación según el nivel VIP"""
    bonuses = {1: 500, 2: 2800, 3: 6000}
    return bonuses.get(vip_level, 0)

def scan_pending_payments():
    """
    Escanea pagos pendientes y verifica automáticamente.
    Se ejecuta regularmente (cada 5-10 minutos) vía cron-job.
    """
    try:
        pending = get_pending_payments()
        logger.info(f"📊 Escaneando {len(pending)} pagos pendientes...")
        
        results = {
            "verified": 0,
            "failed": 0,
            "errors": []
        }

        for payment in pending:
            try:
                # ✅ No procesar pagos más antiguos de 72 horas
                age = datetime.utcnow() - payment.created_at
                if age > timedelta(hours=72):
                    logger.warning(f"⚠️ Pago {payment.tx_hash[:16]}... muy antiguo, ignorando")
                    results["failed"] += 1
                    continue

                logger.info(f"🔍 Verificando pago: {payment.tx_hash[:16]}... ({payment.crypto_currency})")
                
                verified = False
                
                if payment.crypto_currency == "TRX":
                    expected_trx = get_expected_trx_amount(payment.amount_usd)
                    verified = verify_trx_transaction(payment.tx_hash, expected_trx, TRX_ADDRESS)
                
                elif payment.crypto_currency == "BNB":
                    from config import BSCSCAN_API_KEY
                    verified = verify_bsc_transaction(payment.tx_hash, payment.crypto_amount, payment.to_address, BSCSCAN_API_KEY)
                
                if verified:
                    # ✅ Confirmar pago y activar VIP
                    confirm_payment(payment.tx_hash)
                    bonus = get_reputation_bonus(payment.vip_level)
                    activate_vip(payment.user_id, payment.vip_level, 30, bonus)
                    
                    logger.info(f"✅ PAGO CONFIRMADO: {payment.tx_hash[:16]}... → Usuario {payment.user_id} → VIP{payment.vip_level}")
                    results["verified"] += 1
                    
                    # Notificar al usuario (opcional)
                    # await notify_user(payment.user_id, f"✅ Pago confirmado, VIP{payment.vip_level} activado")
                else:
                    logger.warning(f"❌ Pago rechazado: {payment.tx_hash[:16]}...")
                    results["failed"] += 1
                    
            except Exception as e:
                logger.error(f"❌ Error procesando pago {payment.tx_hash[:16]}...: {e}")
                results["errors"].append(str(e))
                results["failed"] += 1
        
        logger.info(f"📊 Escaneo completado: {results['verified']} verificados, {results['failed']} fallidos")
        return results
        
    except Exception as e:
        logger.error(f"❌ Error en scan_pending_payments: {e}")
        return {"verified": 0, "failed": 0, "errors": [str(e)]}
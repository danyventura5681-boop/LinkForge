import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Ruta de la base de datos
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "linkforge.db"

def get_connection():
    """Retorna una conexión a la base de datos."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Crea todas las tablas necesarias si no existen."""
    conn = get_connection()
    cursor = conn.cursor()

    # Tabla de usuarios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            reputation INTEGER DEFAULT 0,
            vip_level INTEGER DEFAULT 0,
            vip_expires_at TIMESTAMP,
            referred_by INTEGER,
            is_admin INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabla de links promocionados
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            url TEXT,
            link_number INTEGER DEFAULT 1,
            clicks_received INTEGER DEFAULT 0,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(telegram_id)
        )
    """)

    # Tabla de clics a links de otros
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            link_id INTEGER,
            reputation_earned INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(telegram_id),
            FOREIGN KEY (link_id) REFERENCES links(id)
        )
    """)

    # Tabla de referidos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            reputation_earned INTEGER DEFAULT 50,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users(telegram_id),
            FOREIGN KEY (referred_id) REFERENCES users(telegram_id)
        )
    """)

    # Tabla de pagos VIP
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tx_hash TEXT UNIQUE,
            amount_usd INTEGER,
            crypto_amount REAL,
            crypto_currency TEXT,
            status TEXT DEFAULT 'pending',
            confirmed_at TIMESTAMP,
            vip_level INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(telegram_id)
        )
    """)

    # Tabla de eventos/notificaciones (para scheduler)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            link_id INTEGER,
            hours_before INTEGER,
            sent INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(telegram_id),
            FOREIGN KEY (link_id) REFERENCES links(id)
        )
    """)

    conn.commit()
    conn.close()
    logger.info("✅ Base de datos inicializada correctamente")

# ===========================================
# FUNCIONES DE USUARIO
# ===========================================

def create_user(telegram_id: int, username: str = None, referred_by: int = None):
    """Crea un usuario nuevo."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO users (telegram_id, username, referred_by)
        VALUES (?, ?, ?)
    """, (telegram_id, username, referred_by))

    # Si fue referido, dar reputación al referente
    if referred_by:
        cursor.execute("""
            UPDATE users SET reputation = reputation + 50
            WHERE telegram_id = ?
        """, (referred_by,))

        cursor.execute("""
            INSERT INTO referrals (referrer_id, referred_id, reputation_earned)
            VALUES (?, ?, 50)
        """, (referred_by, telegram_id))

    conn.commit()
    conn.close()

def get_user(telegram_id: int):
    """Obtiene un usuario por telegram_id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_username(username: str):
    """Obtiene un usuario por username."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_reputation(telegram_id: int, amount: int):
    """Añade reputación a un usuario."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET reputation = reputation + ? WHERE telegram_id = ?
    """, (amount, telegram_id))
    conn.commit()
    conn.close()

def set_reputation(telegram_id: int, amount: int):
    """Establece la reputación de un usuario (para admin)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET reputation = ? WHERE telegram_id = ?
    """, (amount, telegram_id))
    conn.commit()
    conn.close()

def ban_user(telegram_id: int):
    """Banea a un usuario."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET is_banned = 1 WHERE telegram_id = ?
    """, (telegram_id,))
    conn.commit()
    conn.close()

def unban_user(telegram_id: int):
    """Desbanea a un usuario."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET is_banned = 0 WHERE telegram_id = ?
    """, (telegram_id,))
    conn.commit()
    conn.close()

def make_admin(telegram_id: int):
    """Convierte a un usuario en administrador."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET is_admin = 1 WHERE telegram_id = ?
    """, (telegram_id,))
    conn.commit()
    conn.close()

def is_admin(telegram_id: int) -> bool:
    """Verifica si un usuario es administrador."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE telegram_id = ?", (telegram_id,))
    result = cursor.fetchone()
    conn.close()
    return result["is_admin"] == 1 if result else False

def get_total_users() -> int:
    """Obtiene el total de usuarios registrados."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM users")
    result = cursor.fetchone()
    conn.close()
    return result["count"]

def get_all_links():
    """Obtiene todos los links en promoción."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.*, u.username, u.reputation
        FROM links l
        JOIN users u ON l.user_id = u.telegram_id
        WHERE l.expires_at > CURRENT_TIMESTAMP
        ORDER BY u.reputation DESC
    """)
    links = cursor.fetchall()
    conn.close()
    return links

# ===========================================
# FUNCIONES DE LINKS
# ===========================================

def register_link(telegram_id: int, url: str, link_number: int = 1, days: int = 10):
    """Registra un nuevo link en promoción."""
    conn = get_connection()
    cursor = conn.cursor()

    expires_at = datetime.utcnow() + timedelta(days=days)

    cursor.execute("""
        INSERT INTO links (user_id, url, link_number, expires_at)
        VALUES (?, ?, ?, ?)
    """, (telegram_id, url, link_number, expires_at))

    conn.commit()
    conn.close()

def get_user_links(telegram_id: int):
    """Obtiene todos los links activos de un usuario."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM links
        WHERE user_id = ? AND expires_at > CURRENT_TIMESTAMP
        ORDER BY link_number
    """, (telegram_id,))
    links = cursor.fetchall()
    conn.close()
    return links

def get_active_link(telegram_id: int, link_number: int = 1):
    """Obtiene un link activo específico."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM links
        WHERE user_id = ? AND link_number = ? AND expires_at > CURRENT_TIMESTAMP
    """, (telegram_id, link_number))
    link = cursor.fetchone()
    conn.close()
    return link

def delete_links(telegram_id: int):
    """Elimina todos los links expirados de un usuario."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM links
        WHERE user_id = ? AND expires_at <= CURRENT_TIMESTAMP
    """, (telegram_id,))
    conn.commit()
    conn.close()

def extend_link_expiration(telegram_id: int, days: int):
    """Extiende la expiración de los links activos."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE links
        SET expires_at = datetime(expires_at, '+' || ? || ' days')
        WHERE user_id = ? AND expires_at > CURRENT_TIMESTAMP
    """, (days, telegram_id))
    conn.commit()
    conn.close()

def get_expiring_links(hours: int):
    """Obtiene links que expiran en X horas."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.*, u.username, u.telegram_id
        FROM links l
        JOIN users u ON l.user_id = u.telegram_id
        WHERE l.expires_at BETWEEN datetime('now', '+1 hour')
        AND datetime('now', '+' || ? || ' hours')
        AND l.expires_at > CURRENT_TIMESTAMP
    """, (hours,))
    links = cursor.fetchall()
    conn.close()
    return links

# ===========================================
# FUNCIONES DE REPUTACIÓN Y RANKING
# ===========================================

def get_top_users(limit: int = 5):
    """Obtiene los usuarios con mayor reputación."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT telegram_id, username, reputation
        FROM users
        WHERE is_banned = 0
        ORDER BY reputation DESC
        LIMIT ?
    """, (limit,))
    users = cursor.fetchall()
    conn.close()
    return users

def get_user_rank(telegram_id: int) -> int:
    """Obtiene la posición de un usuario en el ranking."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) + 1 as rank
        FROM users
        WHERE reputation > (SELECT reputation FROM users WHERE telegram_id = ?)
    """, (telegram_id,))
    result = cursor.fetchone()
    conn.close()
    return result["rank"] if result else 0

def record_click(user_id: int, link_id: int, reputation_earned: int = 5):
    """Registra un clic a un link y da reputación al que clicó."""
    conn = get_connection()
    cursor = conn.cursor()

    # Registrar clic
    cursor.execute("""
        INSERT INTO clicks (user_id, link_id, reputation_earned)
        VALUES (?, ?, ?)
    """, (user_id, link_id, reputation_earned))

    # Dar reputación al que clicó
    cursor.execute("""
        UPDATE users SET reputation = reputation + ?
        WHERE telegram_id = ?
    """, (reputation_earned, user_id))

    # Aumentar contador de clics del link
    cursor.execute("""
        UPDATE links SET clicks_received = clicks_received + 1
        WHERE id = ?
    """, (link_id,))

    conn.commit()
    conn.close()

# ===========================================
# FUNCIONES VIP
# ===========================================

def activate_vip(telegram_id: int, vip_level: int, days: int = 30, reputation_bonus: int = 0):
    """Activa un plan VIP para un usuario."""
    conn = get_connection()
    cursor = conn.cursor()

    expires_at = datetime.utcnow() + timedelta(days=days)

    cursor.execute("""
        UPDATE users
        SET vip_level = ?, vip_expires_at = ?, reputation = reputation + ?
        WHERE telegram_id = ?
    """, (vip_level, expires_at, reputation_bonus, telegram_id))

    # Extender links existentes
    cursor.execute("""
        UPDATE links
        SET expires_at = datetime(expires_at, '+' || ? || ' days')
        WHERE user_id = ? AND expires_at > CURRENT_TIMESTAMP
    """, (days, telegram_id))

    conn.commit()
    conn.close()

# ===========================================
# FUNCIONES DE PAGOS
# ===========================================

def register_payment(user_id: int, tx_hash: str, amount_usd: int, crypto_amount: float, crypto_currency: str, vip_level: int):
    """Registra un pago pendiente."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO payments (user_id, tx_hash, amount_usd, crypto_amount, crypto_currency, vip_level)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, tx_hash, amount_usd, crypto_amount, crypto_currency, vip_level))
    conn.commit()
    conn.close()

def confirm_payment(tx_hash: str):
    """Confirma un pago y activa VIP."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, vip_level, amount_usd FROM payments
        WHERE tx_hash = ? AND status = 'pending'
    """, (tx_hash,))
    payment = cursor.fetchone()

    if payment:
        # Mapeo de reputación por plan
        bonus_map = {1: 500, 2: 2800, 3: 6000}
        reputation_bonus = bonus_map.get(payment["vip_level"], 0)

        activate_vip(payment["user_id"], payment["vip_level"], 30, reputation_bonus)

        cursor.execute("""
            UPDATE payments SET status = 'confirmed', confirmed_at = CURRENT_TIMESTAMP
            WHERE tx_hash = ?
        """, (tx_hash,))
        conn.commit()

    conn.close()
    return payment

# ===========================================
# FUNCIONES ADICIONALES PARA PAGOS
# ===========================================

def get_payment_by_hash(tx_hash: str):
    """Obtiene un pago por su hash/código."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM payments 
        WHERE tx_hash = ?
    """, (tx_hash,))
    payment = cursor.fetchone()
    conn.close()
    return payment

def get_pending_payments():
    """Obtiene todos los pagos pendientes de verificación."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM payments 
        WHERE status = 'pending' 
        ORDER BY created_at ASC
    """)
    payments = cursor.fetchall()
    conn.close()
    return payments

def get_payment_by_user(user_id: int, status: str = None):
    """Obtiene los pagos de un usuario específico."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if status:
        cursor.execute("""
            SELECT * FROM payments 
            WHERE user_id = ? AND status = ?
            ORDER BY created_at DESC
        """, (user_id, status))
    else:
        cursor.execute("""
            SELECT * FROM payments 
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
    
    payments = cursor.fetchall()
    conn.close()
    return payments

def update_payment_status(tx_hash: str, status: str):
    """Actualiza el estado de un pago."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE payments 
        SET status = ?, confirmed_at = CURRENT_TIMESTAMP
        WHERE tx_hash = ?
    """, (status, tx_hash))
    conn.commit()
    conn.close()

# ===========================================
# FUNCIONES DE NOTIFICACIONES
# ===========================================

def register_notification(user_id: int, link_id: int, hours_before: int):
    """Registra que se enviará una notificación."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO notifications (user_id, link_id, hours_before)
        VALUES (?, ?, ?)
    """, (user_id, link_id, hours_before))
    conn.commit()
    conn.close()

def mark_notification_sent(notification_id: int):
    """Marca una notificación como enviada."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE notifications SET sent = 1 WHERE id = ?
    """, (notification_id,))
    conn.commit()
    conn.close()

# Inicializar base de datos
init_db()
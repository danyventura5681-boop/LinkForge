import sqlite3
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Ruta de la base de datos
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "linkforge.db"

def get_connection():
    """
    Retorna una conexión a la base de datos.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Crea las tablas necesarias si no existen.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Tabla de usuarios
    cursor.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT,
        link_url TEXT,
        points INTEGER DEFAULT 0,
        total_clicks_received INTEGER DEFAULT 0,
        total_clicks_given INTEGER DEFAULT 0,
        referred_by INTEGER DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # Tabla de clics (para auditoría)
    cursor.execute("""CREATE TABLE IF NOT EXISTS clicks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id INTEGER,
        to_user_id INTEGER,
        points_awarded INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (from_user_id) REFERENCES users(telegram_id),
        FOREIGN KEY (to_user_id) REFERENCES users(telegram_id)
    )""")

    # Tabla de referidos
    cursor.execute("""CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        referred_id INTEGER,
        points_awarded INTEGER DEFAULT 3,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, referred_id)
    )""")

    conn.commit()
    conn.close()
    logger.info("✅ Base de datos inicializada correctamente")

def create_user(telegram_id: int, username: str = None):
    """
    Crea un usuario si no existe.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""INSERT OR IGNORE INTO users (telegram_id, username)
    VALUES (?, ?)""", (telegram_id, username))

    conn.commit()
    conn.close()

def get_user(telegram_id: int):
    """
    Obtiene un usuario por telegram_id.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_username(username: str):
    """
    Obtiene un usuario por username.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user_link(telegram_id: int, link_url: str):
    """
    Actualiza el link de un usuario.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""UPDATE users SET link_url = ? WHERE telegram_id = ?""",
                   (link_url, telegram_id))
    conn.commit()
    conn.close()

def add_points(telegram_id: int, points: int):
    """
    Añade puntos a un usuario.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""UPDATE users SET points = points + ? WHERE telegram_id = ?""",
                   (points, telegram_id))
    conn.commit()
    conn.close()

def record_click(from_user_id: int, to_user_id: int, points: int = 1):
    """
    Registra un clic y otorga puntos al destinatario.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Registrar clic
    cursor.execute("""INSERT INTO clicks (from_user_id, to_user_id, points_awarded)
                      VALUES (?, ?, ?)""", (from_user_id, to_user_id, points))

    # Aumentar puntos del destinatario
    cursor.execute("""UPDATE users SET points = points + ?, total_clicks_received = total_clicks_received + 1
                      WHERE telegram_id = ?""", (points, to_user_id))

    # Aumentar contador de clics del que hizo clic
    cursor.execute("""UPDATE users SET total_clicks_given = total_clicks_given + 1
                      WHERE telegram_id = ?""", (from_user_id,))

    conn.commit()
    conn.close()

def get_ranking(limit: int = 10):
    """
    Obtiene el top de usuarios por puntos.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT telegram_id, username, link_url, points, total_clicks_received
        FROM users
        WHERE link_url IS NOT NULL AND link_url != ''
        ORDER BY points DESC
        LIMIT ?
    """, (limit,))

    ranking = cursor.fetchall()
    conn.close()
    return ranking

def record_referral(user_id: int, referred_id: int):
    """
    Registra un referido y otorga puntos al referente.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Evitar duplicados
    cursor.execute("""SELECT * FROM referrals WHERE user_id = ? AND referred_id = ?""",
                   (user_id, referred_id))
    if cursor.fetchone():
        conn.close()
        return False

    # Registrar referido
    cursor.execute("""INSERT INTO referrals (user_id, referred_id, points_awarded)
                      VALUES (?, ?, ?)""", (user_id, referred_id, 3))

    # Otorgar puntos al referente
    cursor.execute("""UPDATE users SET points = points + 3 WHERE telegram_id = ?""", (user_id,))

    conn.commit()
    conn.close()
    return True

def get_user_stats(telegram_id: int):
    """
    Obtiene estadísticas de un usuario.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT points, total_clicks_received, total_clicks_given
        FROM users WHERE telegram_id = ?
    """, (telegram_id,))

    stats = cursor.fetchone()

    # Contar referidos
    cursor.execute("""SELECT COUNT(*) FROM referrals WHERE user_id = ?""", (telegram_id,))
    referrals_count = cursor.fetchone()[0]

    conn.close()

    return {
        "points": stats["points"] if stats else 0,
        "clicks_received": stats["total_clicks_received"] if stats else 0,
        "clicks_given": stats["total_clicks_given"] if stats else 0,
        "referrals": referrals_count
    }

# Inicializar base de datos al importar
init_db()
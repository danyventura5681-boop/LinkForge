import sqlite3
from pathlib import Path

# 📁 Ruta de la base de datos
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

    # 👤 Tabla de usuarios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            balance INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 🔗 Tabla de referencias
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            referred_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, referred_id)
        )
    """)

    conn.commit()
    conn.close()


def create_user(telegram_id: int, username: str | None):
    """
    Crea un usuario si no existe.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO users (telegram_id, username)
        VALUES (?, ?)
    """, (telegram_id, username))

    conn.commit()
    conn.close()


def get_user(telegram_id: int):
    """
    Obtiene un usuario por telegram_id.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM users WHERE telegram_id = ?
    """, (telegram_id,))

    user = cursor.fetchone()
    conn.close()

    return user
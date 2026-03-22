from database.database import get_connection


def create_user(
    telegram_id: int,
    username: str | None,
    referrer_id: int | None = None
):
    conn = get_connection()
    cursor = conn.cursor()

    # ✅ verificar si ya existe
    cursor.execute(
        "SELECT id FROM users WHERE telegram_id = ?",
        (telegram_id,)
    )
    exists = cursor.fetchone()

    if exists:
        conn.close()
        return False

    # ✅ crear usuario
    cursor.execute(
        """
        INSERT INTO users (telegram_id, username)
        VALUES (?, ?)
        """,
        (telegram_id, username)
    )

    conn.commit()
    conn.close()

    return True


# 🔗 generar link referral
def generate_referral_link(bot_username: str, telegram_id: int) -> str:
    return f"https://t.me/{bot_username}?start={telegram_id}"
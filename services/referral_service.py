from database import get_connection


def create_user(user_id: int, referrer_id: int | None = None):
    conn = get_connection()
    cursor = conn.cursor()

    # verificar si ya existe
    cursor.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user_id,)
    )
    exists = cursor.fetchone()

    if exists:
        conn.close()
        return False

    # crear usuario
    cursor.execute(
        """
        INSERT INTO users (user_id, balance, referrer_id)
        VALUES (?, 0, ?)
        """,
        (user_id, referrer_id)
    )

    conn.commit()
    conn.close()
    return True
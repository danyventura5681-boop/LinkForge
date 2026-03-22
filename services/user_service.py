users = {}


def get_or_create_user(user_id: int, username: str | None):
    if user_id not in users:
        users[user_id] = {
            "id": user_id,
            "username": username,
            "balance": 0,
            "referrals": 0,
        }

    return users[user_id]
import logging
from database import get_user, create_user, add_reputation, get_user_links, get_user_rank
from database import get_referral_count  # Si existe, o crear función

logger = logging.getLogger(__name__)


def get_or_create_user(telegram_id: int, username: str = None):
    """
    Obtiene un usuario de la base de datos o lo crea si no existe.
    Retorna el objeto User de SQLAlchemy.
    """
    user = get_user(telegram_id)
    if not user:
        create_user(telegram_id, username)
        user = get_user(telegram_id)
        logger.info(f"✅ Usuario {telegram_id} creado")
    return user


def get_user_balance(telegram_id: int) -> int:
    """
    Obtiene la reputación (balance) de un usuario.
    """
    user = get_user(telegram_id)
    return user.reputation if user else 0


def get_user_referrals_count(telegram_id: int) -> int:
    """
    Obtiene la cantidad de usuarios referidos por este usuario.
    """
    from database.database import SessionLocal, Referral
    
    session = SessionLocal()
    count = session.query(Referral).filter_by(referrer_id=telegram_id).count()
    session.close()
    return count


def add_user_reputation(telegram_id: int, amount: int):
    """
    Añade reputación a un usuario.
    """
    add_reputation(telegram_id, amount)
    logger.info(f"➕ +{amount} reputación para usuario {telegram_id}")


def get_user_stats(telegram_id: int):
    """
    Obtiene estadísticas completas de un usuario.
    """
    user = get_user(telegram_id)
    if not user:
        return None
    
    links = get_user_links(telegram_id)
    rank = get_user_rank(telegram_id)
    referrals = get_user_referrals_count(telegram_id)
    
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "reputation": user.reputation,
        "vip_level": user.vip_level,
        "vip_expires_at": user.vip_expires_at,
        "is_admin": user.is_admin == 1,
        "is_banned": user.is_banned == 1,
        "rank": rank,
        "active_links": len(links),
        "referrals": referrals,
        "created_at": user.created_at
    }


def update_user_username(telegram_id: int, username: str):
    """
    Actualiza el username de un usuario.
    """
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if user:
        user.username = username
        session.commit()
        logger.info(f"✏️ Username actualizado para {telegram_id}: {username}")
    session.close()
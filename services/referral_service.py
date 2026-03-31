import logging
from database.database import get_user, create_user

logger = logging.getLogger(__name__)


def create_user_safe(
    telegram_id: int,
    username: str = None,
    referrer_id: int = None
) -> bool:
    """
    Crea un usuario si no existe.
    Retorna True si se creó, False si ya existía.
    """
    # Verificar si ya existe
    existing_user = get_user(telegram_id)
    if existing_user:
        logger.info(f"Usuario {telegram_id} ya existe")
        return False

    # Crear usuario con referido
    create_user(telegram_id, username, referred_by=referrer_id)
    logger.info(f"✅ Usuario {telegram_id} creado con referido {referrer_id}")
    return True


def generate_referral_link(bot_username: str, telegram_id: int) -> str:
    """
    Genera el enlace de referido para un usuario.
    """
    return f"https://t.me/{bot_username}?start=ref_{telegram_id}"


def get_referral_count(telegram_id: int) -> int:
    """
    Obtiene la cantidad de usuarios que se unieron por el enlace de un referente.
    """
    from database.database import SessionLocal, Referral
    
    session = SessionLocal()
    count = session.query(Referral).filter_by(referrer_id=telegram_id).count()
    session.close()
    return count


def get_referrals_list(telegram_id: int, limit: int = 10):
    """
    Obtiene la lista de usuarios referidos por un referente.
    """
    from database.database import SessionLocal, Referral, User
    
    session = SessionLocal()
    referrals = session.query(Referral).filter_by(referrer_id=telegram_id).limit(limit).all()
    
    result = []
    for ref in referrals:
        user = session.query(User).filter_by(telegram_id=ref.referred_id).first()
        if user:
            result.append({
                "telegram_id": user.telegram_id,
                "username": user.username,
                "created_at": ref.created_at
            })
    
    session.close()
    return result
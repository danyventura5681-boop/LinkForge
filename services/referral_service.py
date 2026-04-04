import logging
from database import get_user, create_user, get_referrals_count

logger = logging.getLogger(__name__)


def create_user_safe(telegram_id: int, username: str = None, referrer_id: int = None) -> bool:
    """
    Crea un usuario si no existe.
    
    Args:
        telegram_id: ID de Telegram del nuevo usuario
        username: Nombre de usuario de Telegram (opcional)
        referrer_id: ID del usuario que invitó (opcional)
    
    Returns:
        bool: True si se creó el usuario, False si ya existía o hubo error
    
    Note:
        Esta función es segura porque verifica existencia antes de crear.
        La lógica de reputación está centralizada en database.create_user()
    """
    # Verificar si ya existe
    existing_user = get_user(telegram_id)
    
    if existing_user:
        logger.info(f"ℹ️ create_user_safe: Usuario {telegram_id} ya existe, no se crea duplicado")
        return False
    
    # Prevenir auto-referido (seguridad extra)
    if referrer_id == telegram_id:
        logger.warning(f"⚠️ create_user_safe: Auto-referido detectado para {telegram_id}, ignorando referido")
        referrer_id = None
    
    # Crear usuario con referido (la lógica de reputación está dentro de create_user)
    try:
        user = create_user(telegram_id, username, referred_by=referrer_id)
        
        if user:
            logger.info(f"✅ create_user_safe: Usuario {telegram_id} (@{username}) creado exitosamente con referido {referrer_id}")
            return True
        else:
            logger.error(f"❌ create_user_safe: Falló la creación del usuario {telegram_id}")
            return False
            
    except Exception as e:
        logger.error(f"❌ create_user_safe: Error excepcional creando usuario {telegram_id}: {e}")
        return False


def generate_referral_link(bot_username: str, telegram_id: int) -> str:
    """
    Genera el enlace de referido para un usuario.
    
    Args:
        bot_username: Nombre de usuario del bot (sin @)
        telegram_id: ID del usuario que invita
    
    Returns:
        str: Enlace de Telegram con el parámetro de referido
    """
    return f"https://t.me/{bot_username}?start=ref_{telegram_id}"


def get_referral_count(telegram_id: int) -> int:
    """
    Obtiene la cantidad de usuarios que se unieron por el enlace de un referente.
    
    Args:
        telegram_id: ID del referente
    
    Returns:
        int: Número de referidos
    """
    return get_referrals_count(telegram_id)


def get_referrals_list(telegram_id: int, limit: int = 10):
    """
    Obtiene la lista de usuarios referidos por un referente.
    
    Args:
        telegram_id: ID del referente
        limit: Máximo número de referidos a retornar
    
    Returns:
        list: Lista de diccionarios con información de los referidos
    """
    from database.database import SessionLocal, Referral, User
    
    session = SessionLocal()
    try:
        referrals = session.query(Referral).filter_by(referrer_id=telegram_id).order_by(Referral.created_at.desc()).limit(limit).all()
        
        result = []
        for ref in referrals:
            user = session.query(User).filter_by(telegram_id=ref.referred_id).first()
            if user:
                result.append({
                    "telegram_id": user.telegram_id,
                    "username": user.username or f"Usuario_{user.telegram_id}",
                    "reputation": user.reputation,
                    "joined_at": ref.created_at.strftime("%d/%m/%Y %H:%M") if ref.created_at else "Fecha desconocida"
                })
        
        logger.info(f"📊 get_referrals_list: Usuario {telegram_id} tiene {len(result)} referidos")
        return result
        
    except Exception as e:
        logger.error(f"❌ get_referrals_list: Error obteniendo referidos para {telegram_id}: {e}")
        return []
    finally:
        session.close()


def get_referral_stats(telegram_id: int) -> dict:
    """
    Obtiene estadísticas completas de referidos para un usuario.
    
    Args:
        telegram_id: ID del referente
    
    Returns:
        dict: Estadísticas incluyendo total, reputación ganada y lista de referidos
    """
    referrals_list = get_referrals_list(telegram_id, limit=50)
    total_referrals = len(referrals_list)
    total_reputation_earned = total_referrals * 50
    
    return {
        "total_referrals": total_referrals,
        "total_reputation_earned": total_reputation_earned,
        "referrals": referrals_list
    }


def check_referral_valid(referrer_id: int, new_user_id: int) -> bool:
    """
    Verifica si un referido es válido.
    
    Args:
        referrer_id: ID del posible referente
        new_user_id: ID del nuevo usuario
    
    Returns:
        bool: True si el referido es válido, False si no
    """
    # No permitir auto-referidos
    if referrer_id == new_user_id:
        logger.warning(f"⚠️ check_referral_valid: Auto-referido detectado ({referrer_id} == {new_user_id})")
        return False
    
    # Verificar que el referente exista
    referrer = get_user(referrer_id)
    if not referrer:
        logger.warning(f"⚠️ check_referral_valid: Referente {referrer_id} no existe")
        return False
    
    # Verificar que el referente no esté baneado
    if referrer.is_banned:
        logger.warning(f"⚠️ check_referral_valid: Referente {referrer_id} está baneado")
        return False
    
    # Verificar que el nuevo usuario no exista ya
    existing_user = get_user(new_user_id)
    if existing_user:
        logger.warning(f"⚠️ check_referral_valid: Usuario {new_user_id} ya existe")
        return False
    
    logger.info(f"✅ check_referral_valid: Referido válido de {referrer_id} a {new_user_id}")
    return True
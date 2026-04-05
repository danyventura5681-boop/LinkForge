import os
import logging
import time
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean, BigInteger, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from pathlib import Path
import random
import string

logger = logging.getLogger(__name__)

# ===========================================
# CONFIGURACIÓN DE BASE DE DATOS
# ===========================================

# Leer URL de base de datos UNA SOLA VEZ
DATABASE_URL = os.environ.get("DATABASE_URL")

logger.info(f"🔍 DATABASE_URL leída: {'SI' if DATABASE_URL else 'NO'}")
if DATABASE_URL:
    logger.info(f"✅ DATABASE_URL encontrada (primeros 30 chars): {DATABASE_URL[:30]}...")

# Si no hay DATABASE_URL, usar SQLite local (fallback)
if not DATABASE_URL:
    BASE_DIR = Path(__file__).resolve().parent.parent
    DB_PATH = BASE_DIR / "linkforge.db"
    DATABASE_URL = f"sqlite:///{DB_PATH}"
    logger.warning(f"⚠️ Usando SQLite local en: {DB_PATH}")
else:
    logger.info(f"✅ Usando PostgreSQL desde DATABASE_URL")

# Configurar engine con timeout y NullPool para evitar conexiones persistentes
try:
    if DATABASE_URL.startswith("postgresql"):
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            poolclass=NullPool,
            connect_args={
                "connect_timeout": 30,
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5
            }
        )
        logger.info("✅ Conectado a PostgreSQL")
    else:
        engine = create_engine(DATABASE_URL)
        logger.info("✅ Conectado a SQLite")
except Exception as e:
    logger.error(f"❌ Error de conexión a la base de datos: {e}")
    raise

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ===========================================
# MODELOS DE DATOS
# ===========================================

class User(Base):
    __tablename__ = 'users'
    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(String)
    reputation = Column(Integer, default=0)
    vip_level = Column(Integer, default=0)
    vip_expires_at = Column(DateTime, nullable=True)
    referred_by = Column(BigInteger, nullable=True)
    is_admin = Column(Integer, default=0)
    is_banned = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class Link(Base):
    __tablename__ = 'links'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    url = Column(Text)
    link_number = Column(Integer, default=1)
    clicks_received = Column(Integer, default=0)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class Click(Base):
    __tablename__ = 'clicks'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    link_id = Column(Integer)
    reputation_earned = Column(Integer, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)

class Referral(Base):
    __tablename__ = 'referrals'
    id = Column(Integer, primary_key=True, autoincrement=True)
    referrer_id = Column(BigInteger)
    referred_id = Column(BigInteger)
    reputation_earned = Column(Integer, default=50)
    created_at = Column(DateTime, default=datetime.utcnow)

class Payment(Base):
    __tablename__ = 'payments'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    tx_hash = Column(String, unique=True)
    amount_usd = Column(Integer)
    crypto_amount = Column(Float)
    crypto_currency = Column(String)
    status = Column(String, default='pending')
    confirmed_at = Column(DateTime, nullable=True)
    vip_level = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

class Notification(Base):
    __tablename__ = 'notifications'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    link_id = Column(Integer)
    hours_before = Column(Integer)
    sent = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

# ===========================================
# NUEVOS MODELOS PARA VIDEOS (LinkForge 1.1)
# ===========================================

class Video(Base):
    __tablename__ = 'videos'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    username = Column(String)
    url = Column(Text)
    title = Column(String)
    views = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class VideoView(Base):
    __tablename__ = 'video_views'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    video_id = Column(Integer)
    reputation_earned = Column(Integer, default=30)
    created_at = Column(DateTime, default=datetime.utcnow)

class InstagramVerification(Base):
    __tablename__ = 'instagram_verifications'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    username = Column(String)
    instagram_user = Column(String)
    status = Column(String, default='pending')  # pending, approved, rejected
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# ===========================================
# CREAR TABLAS CON REINTENTOS
# ===========================================

def create_tables_with_retry(max_retries=3, delay=5):
    """Intenta crear las tablas con reintentos"""
    for attempt in range(max_retries):
        try:
            Base.metadata.create_all(engine)
            logger.info("✅ Tablas creadas/verificadas correctamente")
            return True
        except Exception as e:
            logger.error(f"❌ Intento {attempt + 1} falló al crear tablas: {e}")
            if attempt < max_retries - 1:
                logger.info(f"🔄 Reintentando en {delay} segundos...")
                time.sleep(delay)
            else:
                logger.error("❌ No se pudieron crear las tablas después de varios intentos")
                raise

# Crear tablas con reintentos
create_tables_with_retry()
logger.info("📊 Base de datos inicializada correctamente")

# ===========================================
# FUNCIONES DE USUARIO
# ===========================================

def create_user(telegram_id: int, username: str = None, referred_by: int = None):
    """
    Crea un usuario nuevo con lógica de referidos centralizada.

    Args:
        telegram_id: ID de Telegram del nuevo usuario
        username: Nombre de usuario de Telegram (opcional)
        referred_by: ID del usuario que invitó (opcional)

    Returns:
        User: El usuario creado o None si hubo error
    """
    session = SessionLocal()
    try:
        # Verificar si el usuario ya existe
        existing_user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if existing_user:
            logger.warning(f"⚠️ create_user: Usuario {telegram_id} ya existe")
            return existing_user

        # Evitar auto-referido (que un usuario se refiera a sí mismo)
        if referred_by == telegram_id:
            logger.warning(f"⚠️ create_user: Auto-referido detectado para {telegram_id}, ignorando referido")
            referred_by = None

        # Crear nuevo usuario
        user = User(
            telegram_id=telegram_id,
            username=username,
            referred_by=referred_by
        )
        session.add(user)

        # Lógica de referido CENTRALIZADA
        if referred_by:
            # Buscar al referente (la persona que invitó)
            referrer = session.query(User).filter_by(telegram_id=referred_by).first()

            if referrer:
                # Verificar que el referente no esté baneado
                if referrer.is_banned:
                    logger.warning(f"⚠️ create_user: Referente {referred_by} está baneado, no se da reputación")
                else:
                    # Dar +50 reputación al referente
                    old_rep = referrer.reputation
                    referrer.reputation += 50

                    # Registrar la referencia
                    referral = Referral(
                        referrer_id=referred_by,
                        referred_id=telegram_id,
                        reputation_earned=50
                    )
                    session.add(referral)

                    logger.info(f"✅ create_user: Referente {referred_by} ganó +50 reputación ({old_rep} → {referrer.reputation})")
            else:
                logger.warning(f"⚠️ create_user: Referente {referred_by} no encontrado en la base de datos")

        session.commit()
        logger.info(f"✅ create_user: Usuario {telegram_id} (@{username}) creado exitosamente con referido {referred_by}")
        return user

    except Exception as e:
        logger.error(f"❌ Error en create_user({telegram_id}): {e}")
        session.rollback()
        return None
    finally:
        session.close()

def get_user(telegram_id: int):
    """Obtiene un usuario por telegram_id."""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()

        # ✅ FIX: Acceder a los atributos para forzar la carga antes de cerrar sesión
        if user:
            _ = user.username
            _ = user.reputation
            _ = user.is_admin
            _ = user.is_banned
            logger.info(f"✅ get_user encontró usuario {telegram_id}: @{user.username} (rep: {user.reputation})")
        else:
            logger.warning(f"❌ get_user: Usuario {telegram_id} no existe")

        return user
    except Exception as e:
        logger.error(f"❌ Error en get_user({telegram_id}): {e}")
        return None
    finally:
        session.close()

def get_user_by_username(username: str):
    """Obtiene un usuario por username."""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(username=username).first()

        # ✅ FIX: Acceder a los atributos para forzar la carga antes de cerrar sesión
        if user:
            _ = user.telegram_id
            _ = user.reputation
            _ = user.is_admin
            _ = user.is_banned
            logger.info(f"✅ get_user_by_username encontró: @{username} (ID: {user.telegram_id}, rep: {user.reputation})")
        else:
            logger.warning(f"❌ get_user_by_username: Username @{username} no existe")

        return user
    except Exception as e:
        logger.error(f"❌ Error en get_user_by_username({username}): {e}")
        return None
    finally:
        session.close()

def get_all_users():
    """Obtiene todos los usuarios."""
    session = SessionLocal()
    try:
        users = session.query(User).all()
        logger.info(f"✅ get_all_users: Se obtuvieron {len(users)} usuarios")
        return users
    except Exception as e:
        logger.error(f"❌ Error en get_all_users(): {e}")
        return []
    finally:
        session.close()

def add_reputation(telegram_id: int, amount: int):
    """Añade reputación a un usuario."""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            old_rep = user.reputation
            user.reputation += amount
            session.commit()
            logger.info(f"✅ add_reputation: Usuario {telegram_id} reputación {old_rep} → {user.reputation} (+{amount})")
        else:
            logger.warning(f"❌ add_reputation: Usuario {telegram_id} no encontrado")
    except Exception as e:
        logger.error(f"❌ Error en add_reputation({telegram_id}, {amount}): {e}")
    finally:
        session.close()

def set_reputation(telegram_id: int, amount: int):
    """Establece la reputación de un usuario (para admin)."""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            old_rep = user.reputation
            user.reputation = amount
            session.commit()
            logger.info(f"✅ set_reputation: Usuario {telegram_id} reputación {old_rep} → {amount}")
        else:
            logger.warning(f"❌ set_reputation: Usuario {telegram_id} no encontrado")
    except Exception as e:
        logger.error(f"❌ Error en set_reputation({telegram_id}, {amount}): {e}")
    finally:
        session.close()

def ban_user(telegram_id: int):
    """Banea a un usuario."""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            user.is_banned = 1
            session.commit()
            logger.info(f"✅ ban_user: Usuario {telegram_id} baneado")
        else:
            logger.warning(f"❌ ban_user: Usuario {telegram_id} no encontrado")
    except Exception as e:
        logger.error(f"❌ Error en ban_user({telegram_id}): {e}")
    finally:
        session.close()

def unban_user(telegram_id: int):
    """Desbanea a un usuario."""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            user.is_banned = 0
            session.commit()
            logger.info(f"✅ unban_user: Usuario {telegram_id} desbaneado")
        else:
            logger.warning(f"❌ unban_user: Usuario {telegram_id} no encontrado")
    except Exception as e:
        logger.error(f"❌ Error en unban_user({telegram_id}): {e}")
    finally:
        session.close()

def make_admin(telegram_id: int):
    """Convierte a un usuario en administrador."""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            user.is_admin = 1
            session.commit()
            logger.info(f"✅ make_admin: Usuario {telegram_id} ahora es admin")
        else:
            logger.warning(f"❌ make_admin: Usuario {telegram_id} no encontrado")
    except Exception as e:
        logger.error(f"❌ Error en make_admin({telegram_id}): {e}")
    finally:
        session.close()

def is_admin(telegram_id: int) -> bool:
    """Verifica si un usuario es administrador."""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        result = user.is_admin == 1 if user else False
        logger.info(f"✅ is_admin({telegram_id}): {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Error en is_admin({telegram_id}): {e}")
        return False
    finally:
        session.close()

def get_total_users() -> int:
    """Obtiene el total de usuarios registrados."""
    session = SessionLocal()
    try:
        count = session.query(User).count()
        logger.info(f"✅ get_total_users: {count} usuarios")
        return count
    except Exception as e:
        logger.error(f"❌ Error en get_total_users(): {e}")
        return 0
    finally:
        session.close()

def get_all_links():
    """Obtiene todos los links en promoción."""
    session = SessionLocal()
    try:
        links = session.query(Link).all()
        logger.info(f"✅ get_all_links: {len(links)} links activos")
        return links
    except Exception as e:
        logger.error(f"❌ Error en get_all_links(): {e}")
        return []
    finally:
        session.close()

# ===========================================
# FUNCIONES DE LINKS
# ===========================================

def register_link(telegram_id: int, url: str, link_number: int = 1, days: int = 10):
    """Registra un nuevo link en promoción."""
    session = SessionLocal()
    try:
        expires_at = datetime.utcnow() + timedelta(days=days)
        link = Link(user_id=telegram_id, url=url, link_number=link_number, expires_at=expires_at)
        session.add(link)
        session.commit()
        logger.info(f"✅ register_link: Link registrado para usuario {telegram_id} ({days} días)")
    except Exception as e:
        logger.error(f"❌ Error en register_link({telegram_id}): {e}")
    finally:
        session.close()

def get_user_links(telegram_id: int):
    """Obtiene todos los links activos de un usuario."""
    session = SessionLocal()
    try:
        links = session.query(Link).filter(
            Link.user_id == telegram_id,
            Link.expires_at > datetime.utcnow()
        ).order_by(Link.link_number).all()
        logger.info(f"✅ get_user_links: {len(links)} links activos para usuario {telegram_id}")
        return links
    except Exception as e:
        logger.error(f"❌ Error en get_user_links({telegram_id}): {e}")
        return []
    finally:
        session.close()

def get_active_link(telegram_id: int, link_number: int = 1):
    """Obtiene un link activo específico."""
    session = SessionLocal()
    try:
        link = session.query(Link).filter(
            Link.user_id == telegram_id,
            Link.link_number == link_number,
            Link.expires_at > datetime.utcnow()
        ).first()
        if link:
            logger.info(f"✅ get_active_link: Link encontrado para usuario {telegram_id}")
        else:
            logger.warning(f"❌ get_active_link: No hay link activo para usuario {telegram_id}")
        return link
    except Exception as e:
        logger.error(f"❌ Error en get_active_link({telegram_id}): {e}")
        return None
    finally:
        session.close()

def delete_links(telegram_id: int):
    """Elimina todos los links expirados de un usuario."""
    session = SessionLocal()
    try:
        session.query(Link).filter(Link.user_id == telegram_id).delete()
        session.commit()
        logger.info(f"✅ delete_links: Links eliminados para usuario {telegram_id}")
    except Exception as e:
        logger.error(f"❌ Error en delete_links({telegram_id}): {e}")
    finally:
        session.close()

def extend_link_expiration(telegram_id: int, days: int):
    """Extiende la expiración de los links activos."""
    session = SessionLocal()
    try:
        session.query(Link).filter(
            Link.user_id == telegram_id,
            Link.expires_at > datetime.utcnow()
        ).update({"expires_at": Link.expires_at + timedelta(days=days)})
        session.commit()
        logger.info(f"✅ extend_link_expiration: Links extendidos +{days} días para usuario {telegram_id}")
    except Exception as e:
        logger.error(f"❌ Error en extend_link_expiration({telegram_id}, {days}): {e}")
    finally:
        session.close()

def get_expiring_links(hours: int):
    """Obtiene links que expiran en X horas."""
    session = SessionLocal()
    try:
        now = datetime.utcnow()
        expire_time = now + timedelta(hours=hours)
        links = session.query(Link).filter(
            Link.expires_at <= expire_time,
            Link.expires_at > now
        ).all()
        logger.info(f"✅ get_expiring_links: {len(links)} links expiran en {hours} horas")
        return links
    except Exception as e:
        logger.error(f"❌ Error en get_expiring_links({hours}): {e}")
        return []
    finally:
        session.close()

def update_link(link_id: int, new_url: str):
    """Actualiza solo la URL de un link, sin cambiar expiración."""
    session = SessionLocal()
    try:
        link = session.query(Link).filter_by(id=link_id).first()
        if link:
            old_url = link.url
            link.url = new_url
            session.commit()
            logger.info(f"✅ Link {link_id} actualizado: {old_url} → {new_url}")
        else:
            logger.warning(f"❌ Link {link_id} no encontrado")
    except Exception as e:
        logger.error(f"❌ Error actualizando link: {e}")
    finally:
        session.close()


# ===========================================
# NUEVAS FUNCIONES PARA LINKS (get_link_by_id y delete_link)
# ===========================================

def get_link_by_id(link_id: int):
    """Obtiene un link por su ID."""
    session = SessionLocal()
    try:
        link = session.query(Link).filter_by(id=link_id).first()
        if link:
            logger.info(f"✅ get_link_by_id: Link {link_id} encontrado")
        else:
            logger.warning(f"❌ get_link_by_id: Link {link_id} no encontrado")
        return link
    except Exception as e:
        logger.error(f"❌ Error en get_link_by_id({link_id}): {e}")
        return None
    finally:
        session.close()

def delete_link(link_id: int):
    """Elimina un link."""
    session = SessionLocal()
    try:
        link = session.query(Link).filter_by(id=link_id).first()
        if link:
            session.delete(link)
            session.commit()
            logger.info(f"✅ delete_link: Link {link_id} eliminado")
        else:
            logger.warning(f"❌ delete_link: Link {link_id} no encontrado")
    except Exception as e:
        logger.error(f"❌ Error en delete_link({link_id}): {e}")
        session.rollback()
    finally:
        session.close()

# ===========================================
# FUNCIONES DE REPUTACIÓN Y RANKING
# ===========================================

def get_top_users(limit: int = 5):
    """Obtiene los usuarios con mayor reputación."""
    session = SessionLocal()
    try:
        users = session.query(User).filter(User.is_banned == 0).order_by(User.reputation.desc()).limit(limit).all()
        logger.info(f"✅ get_top_users: Top {len(users)} usuarios obtenidos")
        return users
    except Exception as e:
        logger.error(f"❌ Error en get_top_users({limit}): {e}")
        return []
    finally:
        session.close()

def get_user_rank(telegram_id: int) -> int:
    """Obtiene la posición de un usuario en el ranking."""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            logger.warning(f"❌ get_user_rank: Usuario {telegram_id} no encontrado")
            return 0
        rank = session.query(User).filter(User.reputation > user.reputation).count() + 1
        logger.info(f"✅ get_user_rank: Usuario {telegram_id} en posición #{rank}")
        return rank
    except Exception as e:
        logger.error(f"❌ Error en get_user_rank({telegram_id}): {e}")
        return 0
    finally:
        session.close()

def record_click(user_id: int, link_id: int, reputation_earned: int = 5):
    """Registra un clic a un link y da reputación al que clicó."""
    session = SessionLocal()
    try:
        # Registrar clic
        click = Click(user_id=user_id, link_id=link_id, reputation_earned=reputation_earned)
        session.add(click)

        # Dar reputación al que clicó
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if user:
            user.reputation += reputation_earned

        # Aumentar contador de clics del link
        link = session.query(Link).filter_by(id=link_id).first()
        if link:
            link.clicks_received += 1

        session.commit()
        logger.info(f"✅ record_click: Usuario {user_id} ganó +{reputation_earned} rep del link {link_id}")
    except Exception as e:
        logger.error(f"❌ Error en record_click({user_id}, {link_id}): {e}")
    finally:
        session.close()

def get_referrals_count(telegram_id: int) -> int:
    """Obtiene la cantidad de referidos de un usuario."""
    session = SessionLocal()
    try:
        count = session.query(Referral).filter_by(referrer_id=telegram_id).count()
        logger.info(f"✅ get_referrals_count: Usuario {telegram_id} tiene {count} referidos")
        return count
    except Exception as e:
        logger.error(f"❌ Error en get_referrals_count: {e}")
        return 0
    finally:
        session.close()

def reset_expired_links_reputation(telegram_id: int):
    """Reinicia la reputación si todos los links expiraron."""
    session = SessionLocal()
    try:
        active_links = session.query(Link).filter(
            Link.user_id == telegram_id,
            Link.expires_at > datetime.utcnow()
        ).count()

        if active_links == 0:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if user:
                old_rep = user.reputation
                user.reputation = 0
                session.commit()
                logger.info(f"✅ Reputación reiniciada: {telegram_id} ({old_rep} → 0)")
    except Exception as e:
        logger.error(f"❌ Error reiniciando reputación: {e}")
    finally:
        session.close()

# ===========================================
# FUNCIONES VIP
# ===========================================

def activate_vip(telegram_id: int, vip_level: int, days: int = 30, reputation_bonus: int = 0):
    """Activa un plan VIP para un usuario."""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            expires_at = datetime.utcnow() + timedelta(days=days)
            user.vip_level = vip_level
            user.vip_expires_at = expires_at
            user.reputation += reputation_bonus

            # Extender links existentes
            session.query(Link).filter(
                Link.user_id == telegram_id,
                Link.expires_at > datetime.utcnow()
            ).update({"expires_at": Link.expires_at + timedelta(days=days)})

            session.commit()
            logger.info(f"✅ activate_vip: Usuario {telegram_id} VIP{vip_level} activado por {days} días (+{reputation_bonus} rep)")
        else:
            logger.warning(f"❌ activate_vip: Usuario {telegram_id} no encontrado")
    except Exception as e:
        logger.error(f"❌ Error en activate_vip({telegram_id}, {vip_level}): {e}")
    finally:
        session.close()

# ===========================================
# FUNCIONES DE PAGOS
# ===========================================

def register_payment(user_id: int, tx_hash: str, amount_usd: int, crypto_amount: float, crypto_currency: str, vip_level: int):
    """Registra un pago pendiente."""
    session = SessionLocal()
    try:
        payment = Payment(
            user_id=user_id,
            tx_hash=tx_hash,
            amount_usd=amount_usd,
            crypto_amount=crypto_amount,
            crypto_currency=crypto_currency,
            vip_level=vip_level
        )
        session.add(payment)
        session.commit()
        logger.info(f"✅ register_payment: Pago registrado - Usuario {user_id}, Hash {tx_hash[:8]}..., ${amount_usd} USD")
    except Exception as e:
        logger.error(f"❌ Error en register_payment({user_id}): {e}")
    finally:
        session.close()

def confirm_payment(tx_hash: str):
    """Confirma un pago y activa VIP."""
    session = SessionLocal()
    try:
        payment = session.query(Payment).filter_by(tx_hash=tx_hash, status='pending').first()
        if payment:
            # Mapeo de reputación por plan
            bonus_map = {1: 500, 2: 2800, 3: 6000}
            reputation_bonus = bonus_map.get(payment.vip_level, 0)

            activate_vip(payment.user_id, payment.vip_level, 30, reputation_bonus)

            payment.status = 'confirmed'
            payment.confirmed_at = datetime.utcnow()
            session.commit()
            logger.info(f"✅ confirm_payment: Pago {tx_hash[:8]}... confirmado y VIP activado")
        else:
            logger.warning(f"❌ confirm_payment: Pago {tx_hash[:8]}... no encontrado")
    except Exception as e:
        logger.error(f"❌ Error en confirm_payment({tx_hash[:8]}...): {e}")
    finally:
        session.close()
    return payment if 'payment' in locals() else None

def get_payment_by_hash(tx_hash: str):
    """Obtiene un pago por su hash/código."""
    session = SessionLocal()
    try:
        payment = session.query(Payment).filter_by(tx_hash=tx_hash).first()
        if payment:
            logger.info(f"✅ get_payment_by_hash: Pago encontrado - {tx_hash[:8]}...")
        else:
            logger.warning(f"❌ get_payment_by_hash: Pago no encontrado - {tx_hash[:8]}...")
        return payment
    except Exception as e:
        logger.error(f"❌ Error en get_payment_by_hash({tx_hash[:8]}...): {e}")
        return None
    finally:
        session.close()

def get_pending_payments():
    """Obtiene todos los pagos pendientes de verificación."""
    session = SessionLocal()
    try:
        payments = session.query(Payment).filter_by(status='pending').order_by(Payment.created_at).all()
        logger.info(f"✅ get_pending_payments: {len(payments)} pagos pendientes")
        return payments
    except Exception as e:
        logger.error(f"❌ Error en get_pending_payments(): {e}")
        return []
    finally:
        session.close()

def get_payment_by_user(user_id: int, status: str = None):
    """Obtiene los pagos de un usuario específico."""
    session = SessionLocal()
    try:
        query = session.query(Payment).filter_by(user_id=user_id)
        if status:
            query = query.filter_by(status=status)
        payments = query.order_by(Payment.created_at.desc()).all()
        logger.info(f"✅ get_payment_by_user: {len(payments)} pagos para usuario {user_id}")
        return payments
    except Exception as e:
        logger.error(f"❌ Error en get_payment_by_user({user_id}): {e}")
        return []
    finally:
        session.close()

def update_payment_status(tx_hash: str, status: str):
    """Actualiza el estado de un pago."""
    session = SessionLocal()
    try:
        session.query(Payment).filter_by(tx_hash=tx_hash).update({"status": status, "confirmed_at": datetime.utcnow()})
        session.commit()
        logger.info(f"✅ update_payment_status: Pago {tx_hash[:8]}... actualizado a '{status}'")
    except Exception as e:
        logger.error(f"❌ Error en update_payment_status({tx_hash[:8]}..., {status}): {e}")
    finally:
        session.close()

# ===========================================
# FUNCIONES DE NOTIFICACIONES
# ===========================================

def register_notification(user_id: int, link_id: int, hours_before: int):
    """Registra que se enviará una notificación."""
    session = SessionLocal()
    try:
        notification = Notification(user_id=user_id, link_id=link_id, hours_before=hours_before)
        session.add(notification)
        session.commit()
        logger.info(f"✅ register_notification: Notificación programada para usuario {user_id} en {hours_before}h")
    except Exception as e:
        logger.error(f"❌ Error en register_notification({user_id}): {e}")
    finally:
        session.close()

def mark_notification_sent(notification_id: int):
    """Marca una notificación como enviada."""
    session = SessionLocal()
    try:
        session.query(Notification).filter_by(id=notification_id).update({"sent": 1})
        session.commit()
        logger.info(f"✅ mark_notification_sent: Notificación {notification_id} marcada como enviada")
    except Exception as e:
        logger.error(f"❌ Error en mark_notification_sent({notification_id}): {e}")
    finally:
        session.close()

# ===========================================
# NUEVAS FUNCIONES PARA VIDEOS (LinkForge 1.1)
# ===========================================

def add_video(user_id: int, username: str, url: str, title: str):
    """Agrega un nuevo video al sistema."""
    session = SessionLocal()
    try:
        video = Video(
            user_id=user_id,
            username=username,
            url=url,
            title=title
        )
        session.add(video)
        session.commit()
        logger.info(f"✅ add_video: Video '{title}' agregado por usuario {user_id}")
        return video
    except Exception as e:
        logger.error(f"❌ Error en add_video({user_id}): {e}")
        session.rollback()
        return None
    finally:
        session.close()

def get_user_videos(user_id: int):
    """Obtiene todos los videos de un usuario."""
    session = SessionLocal()
    try:
        videos = session.query(Video).filter_by(user_id=user_id).order_by(Video.created_at.desc()).all()
        logger.info(f"✅ get_user_videos: {len(videos)} videos encontrados para usuario {user_id}")
        return videos
    except Exception as e:
        logger.error(f"❌ Error en get_user_videos({user_id}): {e}")
        return []
    finally:
        session.close()

def get_videos_count_by_user(user_id: int) -> int:
    """Obtiene la cantidad de videos que tiene un usuario."""
    session = SessionLocal()
    try:
        count = session.query(Video).filter_by(user_id=user_id).count()
        logger.info(f"✅ get_videos_count_by_user: Usuario {user_id} tiene {count} videos")
        return count
    except Exception as e:
        logger.error(f"❌ Error en get_videos_count_by_user({user_id}): {e}")
        return 0
    finally:
        session.close()

def get_top_videos(limit: int = 10):
    """Obtiene los videos ordenados por reputación del usuario dueño."""
    session = SessionLocal()
    try:
        videos = session.query(Video).all()
        # Ordenar por reputación del usuario dueño
        videos_with_reputation = []
        for video in videos:
            user = session.query(User).filter_by(telegram_id=video.user_id).first()
            rep = user.reputation if user else 0
            videos_with_reputation.append((video, rep))

        videos_with_reputation.sort(key=lambda x: x[1], reverse=True)
        result = [v[0] for v in videos_with_reputation[:limit]]

        logger.info(f"✅ get_top_videos: {len(result)} videos obtenidos ordenados por reputación")
        return result
    except Exception as e:
        logger.error(f"❌ Error en get_top_videos({limit}): {e}")
        return []
    finally:
        session.close()

def get_all_videos():
    """Obtiene todos los videos."""
    session = SessionLocal()
    try:
        videos = session.query(Video).order_by(Video.created_at.desc()).all()
        logger.info(f"✅ get_all_videos: {len(videos)} videos totales")
        return videos
    except Exception as e:
        logger.error(f"❌ Error en get_all_videos(): {e}")
        return []
    finally:
        session.close()

def get_video(video_id: int):
    """Obtiene un video por su ID."""
    session = SessionLocal()
    try:
        video = session.query(Video).filter_by(id=video_id).first()
        if video:
            logger.info(f"✅ get_video: Video {video_id} encontrado")
        else:
            logger.warning(f"❌ get_video: Video {video_id} no encontrado")
        return video
    except Exception as e:
        logger.error(f"❌ Error en get_video({video_id}): {e}")
        return None
    finally:
        session.close()

def increment_video_views(video_id: int):
    """Incrementa el contador de vistas de un video."""
    session = SessionLocal()
    try:
        video = session.query(Video).filter_by(id=video_id).first()
        if video:
            video.views += 1
            session.commit()
            logger.info(f"✅ increment_video_views: Video {video_id} ahora tiene {video.views} vistas")
    except Exception as e:
        logger.error(f"❌ Error en increment_video_views({video_id}): {e}")
    finally:
        session.close()

def delete_video(video_id: int):
    """Elimina un video."""
    session = SessionLocal()
    try:
        video = session.query(Video).filter_by(id=video_id).first()
        if video:
            session.delete(video)
            session.commit()
            logger.info(f"✅ delete_video: Video {video_id} eliminado")
        else:
            logger.warning(f"❌ delete_video: Video {video_id} no encontrado")
    except Exception as e:
        logger.error(f"❌ Error en delete_video({video_id}): {e}")
    finally:
        session.close()

def can_user_add_video(user_id: int) -> bool:
    """Verifica si un usuario puede agregar más videos según su nivel VIP."""
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            return False

        videos_count = session.query(Video).filter_by(user_id=user_id).count()
        max_videos = 3 if user.vip_level >= 3 else 1

        can_add = videos_count < max_videos
        logger.info(f"✅ can_user_add_video: Usuario {user_id} puede agregar video: {can_add} ({videos_count}/{max_videos})")
        return can_add
    except Exception as e:
        logger.error(f"❌ Error en can_user_add_video({user_id}): {e}")
        return False
    finally:
        session.close()

# ===========================================
# FUNCIONES PARA CONTROL DE VIDEOS VISTOS
# ===========================================

def has_user_watched_video(user_id: int, video_id: int) -> bool:
    """Verifica si un usuario ya ha visto un video antes."""
    session = SessionLocal()
    try:
        # Buscar en la tabla video_views
        view = session.query(VideoView).filter_by(
            user_id=user_id,
            video_id=video_id
        ).first()

        has_watched = view is not None
        logger.info(f"✅ has_user_watched_video: Usuario {user_id} ha visto video {video_id}: {has_watched}")
        return has_watched
    except Exception as e:
        logger.error(f"❌ Error en has_user_watched_video({user_id}, {video_id}): {e}")
        return False
    finally:
        session.close()

def mark_video_as_watched(user_id: int, video_id: int):
    """Marca que un usuario ha visto un video."""
    session = SessionLocal()
    try:
        # Verificar si ya existe
        existing = session.query(VideoView).filter_by(
            user_id=user_id,
            video_id=video_id
        ).first()

        if existing:
            logger.info(f"ℹ️ mark_video_as_watched: Usuario {user_id} ya había visto video {video_id}")
            return

        # Crear nuevo registro
        view = VideoView(
            user_id=user_id,
            video_id=video_id,
            reputation_earned=30
        )
        session.add(view)
        session.commit()
        logger.info(f"✅ mark_video_as_watched: Usuario {user_id} marcado como que vio video {video_id}")
    except Exception as e:
        logger.error(f"❌ Error en mark_video_as_watched({user_id}, {video_id}): {e}")
        session.rollback()
    finally:
        session.close()

def get_user_watched_videos(user_id: int, limit: int = 50):
    """Obtiene la lista de videos que un usuario ha visto."""
    session = SessionLocal()
    try:
        views = session.query(VideoView).filter_by(user_id=user_id).limit(limit).all()
        video_ids = [view.video_id for view in views]
        logger.info(f"✅ get_user_watched_videos: Usuario {user_id} ha visto {len(video_ids)} videos")
        return video_ids
    except Exception as e:
        logger.error(f"❌ Error en get_user_watched_videos({user_id}): {e}")
        return []
    finally:
        session.close()

# ===========================================
# NUEVAS FUNCIONES PARA INSTAGRAM (LinkForge 1.1)
# ===========================================

def create_instagram_request(user_id: int, username: str, instagram_user: str):
    """Crea una solicitud de verificación de Instagram."""
    session = SessionLocal()
    try:
        request = InstagramVerification(
            user_id=user_id,
            username=username,
            instagram_user=instagram_user,
            status='pending'
        )
        session.add(request)
        session.commit()
        logger.info(f"✅ create_instagram_request: Solicitud creada para usuario {user_id} (@{instagram_user})")
        return request
    except Exception as e:
        logger.error(f"❌ Error en create_instagram_request({user_id}): {e}")
        session.rollback()
        return None
    finally:
        session.close()

def get_pending_instagram_requests():
    """Obtiene todas las solicitudes de Instagram pendientes."""
    session = SessionLocal()
    try:
        requests = session.query(InstagramVerification).filter_by(status='pending').order_by(InstagramVerification.created_at).all()
        logger.info(f"✅ get_pending_instagram_requests: {len(requests)} solicitudes pendientes")
        return requests
    except Exception as e:
        logger.error(f"❌ Error en get_pending_instagram_requests(): {e}")
        return []
    finally:
        session.close()

def approve_instagram_request(request_id: int):
    """Aprueba una solicitud de Instagram y da +100 reputación."""
    session = SessionLocal()
    try:
        request = session.query(InstagramVerification).filter_by(id=request_id).first()
        if request:
            request.status = 'approved'
            request.approved_at = datetime.utcnow()

            # Dar +100 reputación al usuario
            user = session.query(User).filter_by(telegram_id=request.user_id).first()
            if user:
                user.reputation += 100
                logger.info(f"✅ +100 reputación para usuario {request.user_id} por Instagram")

            session.commit()
            logger.info(f"✅ approve_instagram_request: Solicitud {request_id} aprobada")
            return request
        else:
            logger.warning(f"❌ approve_instagram_request: Solicitud {request_id} no encontrada")
            return None
    except Exception as e:
        logger.error(f"❌ Error en approve_instagram_request({request_id}): {e}")
        session.rollback()
        return None
    finally:
        session.close()

def reject_instagram_request(request_id: int):
    """Rechaza una solicitud de Instagram."""
    session = SessionLocal()
    try:
        request = session.query(InstagramVerification).filter_by(id=request_id).first()
        if request:
            request.status = 'rejected'
            session.commit()
            logger.info(f"✅ reject_instagram_request: Solicitud {request_id} rechazada")
            return request
        else:
            logger.warning(f"❌ reject_instagram_request: Solicitud {request_id} no encontrada")
            return None
    except Exception as e:
        logger.error(f"❌ Error en reject_instagram_request({request_id}): {e}")
        session.rollback()
        return None
    finally:
        session.close()

def has_user_claimed_instagram(user_id: int) -> bool:
    """Verifica si un usuario ya reclamó la recompensa de Instagram."""
    session = SessionLocal()
    try:
        request = session.query(InstagramVerification).filter_by(user_id=user_id).first()
        has_claimed = request is not None
        logger.info(f"✅ has_user_claimed_instagram: Usuario {user_id} ha reclamado: {has_claimed}")
        return has_claimed
    except Exception as e:
        logger.error(f"❌ Error en has_user_claimed_instagram({user_id}): {e}")
        return False
    finally:
        session.close()
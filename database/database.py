import os
import logging
import time

logger = logging.getLogger(__name__)

# ===========================================
# DIAGNÓSTICO DE VARIABLES DE ENTORNO
# ===========================================
logger.info("🔍 DIAGNÓSTICO: Variables de entorno disponibles:")
for key in sorted(os.environ.keys()):
    if "DATABASE" in key.upper() or "POSTGRES" in key.upper() or "URL" in key.upper():
        # Mostrar solo primeros 20 chars por seguridad
        value = os.environ[key]
        logger.info(f"   {key} = {value[:30]}..." if len(value) > 30 else f"   {key} = {value}")

DATABASE_URL = os.environ.get("DATABASE_URL")
logger.info(f"🔍 DATABASE_URL leída: {'SI' if DATABASE_URL else 'NO'}")

if not DATABASE_URL:
    logger.error("❌ DATABASE_URL NO encontrada en variables de entorno")
    logger.info("🔍 Posibles causas:")
    logger.info("   1. La variable no está configurada en Railway")
    logger.info("   2. La variable está en Shared Variables pero no en Service Variables")
    logger.info("   3. La variable se agregó después del último deploy")
else:
    logger.info(f"✅ DATABASE_URL encontrada (primeros 30 chars): {DATABASE_URL[:30]}...")
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean, BigInteger, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import random
import string

logger = logging.getLogger(__name__)

# ===========================================
# CONFIGURACIÓN DE BASE DE DATOS
# ===========================================

# Leer URL de base de datos desde variable de entorno
DATABASE_URL = os.environ.get("DATABASE_URL")

# Si no hay DATABASE_URL, usar SQLite local (fallback)
if not DATABASE_URL:
    from pathlib import Path
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
            poolclass=NullPool,  # No mantener conexiones persistentes
            connect_args={
                "connect_timeout": 30,  # Timeout de conexión
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5
            }
        )
        logger.info("✅ Conectado a PostgreSQL (Supabase)")
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
    """Crea un usuario nuevo."""
    session = SessionLocal()

    user = User(telegram_id=telegram_id, username=username, referred_by=referred_by)
    session.add(user)

    # Si fue referido, dar reputación al referente
    if referred_by:
        referrer = session.query(User).filter_by(telegram_id=referred_by).first()
        if referrer:
            referrer.reputation += 50
            referral = Referral(referrer_id=referred_by, referred_id=telegram_id, reputation_earned=50)
            session.add(referral)

    session.commit()
    session.close()

def get_user(telegram_id: int):
    """Obtiene un usuario por telegram_id."""
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    session.close()
    return user

def get_user_by_username(username: str):
    """Obtiene un usuario por username."""
    session = SessionLocal()
    user = session.query(User).filter_by(username=username).first()
    session.close()
    return user

def get_all_users():
    """Obtiene todos los usuarios."""
    session = SessionLocal()
    users = session.query(User).all()
    session.close()
    return users

def add_reputation(telegram_id: int, amount: int):
    """Añade reputación a un usuario."""
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if user:
        user.reputation += amount
        session.commit()
    session.close()

def set_reputation(telegram_id: int, amount: int):
    """Establece la reputación de un usuario (para admin)."""
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if user:
        user.reputation = amount
        session.commit()
    session.close()

def ban_user(telegram_id: int):
    """Banea a un usuario."""
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if user:
        user.is_banned = 1
        session.commit()
    session.close()

def unban_user(telegram_id: int):
    """Desbanea a un usuario."""
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if user:
        user.is_banned = 0
        session.commit()
    session.close()

def make_admin(telegram_id: int):
    """Convierte a un usuario en administrador."""
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if user:
        user.is_admin = 1
        session.commit()
    session.close()

def is_admin(telegram_id: int) -> bool:
    """Verifica si un usuario es administrador."""
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    result = user.is_admin == 1 if user else False
    session.close()
    return result

def get_total_users() -> int:
    """Obtiene el total de usuarios registrados."""
    session = SessionLocal()
    count = session.query(User).count()
    session.close()
    return count

def get_all_links():
    """Obtiene todos los links en promoción."""
    session = SessionLocal()
    links = session.query(Link).all()
    session.close()
    return links

# ===========================================
# FUNCIONES DE LINKS
# ===========================================

def register_link(telegram_id: int, url: str, link_number: int = 1, days: int = 10):
    """Registra un nuevo link en promoción."""
    session = SessionLocal()
    expires_at = datetime.utcnow() + timedelta(days=days)
    link = Link(user_id=telegram_id, url=url, link_number=link_number, expires_at=expires_at)
    session.add(link)
    session.commit()
    session.close()

def get_user_links(telegram_id: int):
    """Obtiene todos los links activos de un usuario."""
    session = SessionLocal()
    links = session.query(Link).filter(
        Link.user_id == telegram_id,
        Link.expires_at > datetime.utcnow()
    ).order_by(Link.link_number).all()
    session.close()
    return links

def get_active_link(telegram_id: int, link_number: int = 1):
    """Obtiene un link activo específico."""
    session = SessionLocal()
    link = session.query(Link).filter(
        Link.user_id == telegram_id,
        Link.link_number == link_number,
        Link.expires_at > datetime.utcnow()
    ).first()
    session.close()
    return link

def delete_links(telegram_id: int):
    """Elimina todos los links expirados de un usuario."""
    session = SessionLocal()
    session.query(Link).filter(Link.user_id == telegram_id).delete()
    session.commit()
    session.close()

def extend_link_expiration(telegram_id: int, days: int):
    """Extiende la expiración de los links activos."""
    session = SessionLocal()
    session.query(Link).filter(
        Link.user_id == telegram_id,
        Link.expires_at > datetime.utcnow()
    ).update({"expires_at": Link.expires_at + timedelta(days=days)})
    session.commit()
    session.close()

def get_expiring_links(hours: int):
    """Obtiene links que expiran en X horas."""
    session = SessionLocal()
    now = datetime.utcnow()
    expire_time = now + timedelta(hours=hours)
    links = session.query(Link).filter(
        Link.expires_at <= expire_time,
        Link.expires_at > now
    ).all()
    session.close()
    return links

# ===========================================
# FUNCIONES DE REPUTACIÓN Y RANKING
# ===========================================

def get_top_users(limit: int = 5):
    """Obtiene los usuarios con mayor reputación."""
    session = SessionLocal()
    users = session.query(User).filter(User.is_banned == 0).order_by(User.reputation.desc()).limit(limit).all()
    session.close()
    return users

def get_user_rank(telegram_id: int) -> int:
    """Obtiene la posición de un usuario en el ranking."""
    session = SessionLocal()
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        return 0
    rank = session.query(User).filter(User.reputation > user.reputation).count() + 1
    session.close()
    return rank

def record_click(user_id: int, link_id: int, reputation_earned: int = 5):
    """Registra un clic a un link y da reputación al que clicó."""
    session = SessionLocal()

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
    session.close()

# ===========================================
# FUNCIONES VIP
# ===========================================

def activate_vip(telegram_id: int, vip_level: int, days: int = 30, reputation_bonus: int = 0):
    """Activa un plan VIP para un usuario."""
    session = SessionLocal()
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
    session.close()

# ===========================================
# FUNCIONES DE PAGOS
# ===========================================

def register_payment(user_id: int, tx_hash: str, amount_usd: int, crypto_amount: float, crypto_currency: str, vip_level: int):
    """Registra un pago pendiente."""
    session = SessionLocal()
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
    session.close()

def confirm_payment(tx_hash: str):
    """Confirma un pago y activa VIP."""
    session = SessionLocal()
    payment = session.query(Payment).filter_by(tx_hash=tx_hash, status='pending').first()
    if payment:
        # Mapeo de reputación por plan
        bonus_map = {1: 500, 2: 2800, 3: 6000}
        reputation_bonus = bonus_map.get(payment.vip_level, 0)

        activate_vip(payment.user_id, payment.vip_level, 30, reputation_bonus)

        payment.status = 'confirmed'
        payment.confirmed_at = datetime.utcnow()
        session.commit()
    session.close()
    return payment

def get_payment_by_hash(tx_hash: str):
    """Obtiene un pago por su hash/código."""
    session = SessionLocal()
    payment = session.query(Payment).filter_by(tx_hash=tx_hash).first()
    session.close()
    return payment

def get_pending_payments():
    """Obtiene todos los pagos pendientes de verificación."""
    session = SessionLocal()
    payments = session.query(Payment).filter_by(status='pending').order_by(Payment.created_at).all()
    session.close()
    return payments

def get_payment_by_user(user_id: int, status: str = None):
    """Obtiene los pagos de un usuario específico."""
    session = SessionLocal()
    query = session.query(Payment).filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status)
    payments = query.order_by(Payment.created_at.desc()).all()
    session.close()
    return payments

def update_payment_status(tx_hash: str, status: str):
    """Actualiza el estado de un pago."""
    session = SessionLocal()
    session.query(Payment).filter_by(tx_hash=tx_hash).update({"status": status, "confirmed_at": datetime.utcnow()})
    session.commit()
    session.close()

# ===========================================
# FUNCIONES DE NOTIFICACIONES
# ===========================================

def register_notification(user_id: int, link_id: int, hours_before: int):
    """Registra que se enviará una notificación."""
    session = SessionLocal()
    notification = Notification(user_id=user_id, link_id=link_id, hours_before=hours_before)
    session.add(notification)
    session.commit()
    session.close()

def mark_notification_sent(notification_id: int):
    """Marca una notificación como enviada."""
    session = SessionLocal()
    session.query(Notification).filter_by(id=notification_id).update({"sent": 1})
    session.commit()
    session.close()
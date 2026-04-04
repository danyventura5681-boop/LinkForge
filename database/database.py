import os
import logging
import time
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, BigInteger, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from pathlib import Path

logger = logging.getLogger(__name__)

# ===========================================
# CONFIGURACIÓN DE BASE DE DATOS
# ===========================================

DATABASE_URL = os.environ.get("DATABASE_URL")

logger.info(f"🔍 DATABASE_URL leída: {'SI' if DATABASE_URL else 'NO'}")

if not DATABASE_URL:
    BASE_DIR = Path(__file__).resolve().parent.parent
    DB_PATH = BASE_DIR / "linkforge.db"
    DATABASE_URL = f"sqlite:///{DB_PATH}"
    logger.warning(f"⚠️ Usando SQLite local en: {DB_PATH}")
else:
    logger.info("✅ Usando PostgreSQL")

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
    else:
        engine = create_engine(DATABASE_URL)
except Exception as e:
    logger.error(f"❌ Error de conexión: {e}")
    raise

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ===========================================
# MODELOS
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
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    url = Column(Text)
    link_number = Column(Integer, default=1)
    clicks_received = Column(Integer, default=0)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class Click(Base):
    __tablename__ = 'clicks'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    link_id = Column(Integer)
    reputation_earned = Column(Integer, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)

class Referral(Base):
    __tablename__ = 'referrals'
    id = Column(Integer, primary_key=True)
    referrer_id = Column(BigInteger)
    referred_id = Column(BigInteger)
    reputation_earned = Column(Integer, default=50)
    created_at = Column(DateTime, default=datetime.utcnow)

class Payment(Base):
    __tablename__ = 'payments'
    id = Column(Integer, primary_key=True)
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
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    link_id = Column(Integer)
    hours_before = Column(Integer)
    sent = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

# ===========================================
# CREAR TABLAS
# ===========================================

def create_tables_with_retry(max_retries=3, delay=5):
    for attempt in range(max_retries):
        try:
            Base.metadata.create_all(engine)
            logger.info("✅ Tablas listas")
            return True
        except Exception as e:
            logger.error(f"❌ Intento {attempt+1}: {e}")
            time.sleep(delay)
    raise Exception("No se pudieron crear tablas")

create_tables_with_retry()

# ===========================================
# USUARIOS (FIX PRINCIPAL AQUÍ)
# ===========================================

def create_user(telegram_id: int, username: str = None, referred_by: int = None):
    session = SessionLocal()

    try:
        # 🔥 Evitar auto-referido
        if referred_by == telegram_id:
            referred_by = None

        user = User(
            telegram_id=telegram_id,
            username=username,
            referred_by=referred_by
        )
        session.add(user)

        # 🔥 Lógica de referidos CENTRALIZADA
        if referred_by:
            referrer = session.query(User).filter_by(telegram_id=referred_by).first()

            if referrer:
                referrer.reputation += 50

                referral = Referral(
                    referrer_id=referred_by,
                    referred_id=telegram_id,
                    reputation_earned=50
                )
                session.add(referral)

                logger.info(f"🎁 +50 para {referred_by} por referir a {telegram_id}")
            else:
                logger.warning(f"Referrer {referred_by} no existe")

        session.commit()

    except Exception as e:
        session.rollback()
        logger.error(f"❌ Error creando usuario: {e}")

    finally:
        session.close()

def get_user(telegram_id: int):
    session = SessionLocal()
    try:
        return session.query(User).filter_by(telegram_id=telegram_id).first()
    finally:
        session.close()

def add_reputation(telegram_id: int, amount: int):
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if user:
            user.reputation += amount
            session.commit()
    finally:
        session.close()

# ===========================================
# LINKS
# ===========================================

def get_user_links(telegram_id: int):
    session = SessionLocal()
    try:
        return session.query(Link).filter(
            Link.user_id == telegram_id,
            Link.expires_at > datetime.utcnow()
        ).all()
    finally:
        session.close()

# ===========================================
# RANKING
# ===========================================

def get_user_rank(telegram_id: int):
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            return 0
        return session.query(User).filter(User.reputation > user.reputation).count() + 1
    finally:
        session.close()
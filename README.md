# 🔗 LinkForge

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.10-green)
![Telegram Bot API](https://img.shields.io/badge/Telegram%20Bot%20API-latest-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**LinkForge** es un bot de Telegram que permite a los usuarios promocionar sus enlaces mediante un sistema de reputación, ranking, referidos y planes VIP. Los usuarios ganan puntos (reputación) interactuando con otros enlaces, invitando amigos o comprando paquetes VIP, lo que les permite posicionar sus links más arriba en el ranking.

---

## 🚀 Características principales

| Característica | Descripción |
|----------------|-------------|
| 🔗 **Registro de links** | Los usuarios pueden registrar sus enlaces para promocionarlos |
| 🏆 **Sistema de ranking** | Los enlaces se posicionan según la reputación del usuario |
| 🎁 **Ganar reputación** | Los usuarios ganan puntos visitando enlaces de otros |
| 👥 **Sistema de referidos** | Invita amigos y gana +50 reputación por cada uno |
| ⭐ **Planes VIP** | 3 niveles de VIP con beneficios exclusivos (más reputación, más links, etc.) |
| 💎 **Pagos con criptomonedas** | Soporte para TRX, TON, ETH, BTC, BNB, SOL |
| 🛡️ **Panel de administración** | Gestión de usuarios, reputación, bans y más |
| 📊 **Estadísticas en tiempo real** | Seguimiento de clics, reputación y posiciones |

---

## 📦 Tecnologías utilizadas

| Tecnología | Propósito |
|------------|-----------|
| **Python 3.10** | Lenguaje principal |
| **python-telegram-bot** | Framework para el bot de Telegram |
| **SQLAlchemy** | ORM para la base de datos |
| **PostgreSQL** | Base de datos persistente (Aiven / Supabase) |
| **FastAPI** | Servidor web para healthchecks y notificaciones |
| **UptimeRobot** | Mantiene el bot activo 24/7 |
| **cron-job.org** | Notificaciones automáticas de expiración |

---

## 🏗️ Arquitectura del proyecto
LinkForge/
├── database/
│   └── database.py
├── handlers/
│   ├── __init__.py
│   ├── admin.py
│   ├── link.py
│   ├── ranking.py
│   ├── referral.py
│   ├── reputation.py
│   ├── start.py
│   └── vip.py
├── services/
│   ├── __init__.py
│   ├── blockchain.py
│   ├── referral_service.py
│   ├── trx_checker.py
│   └── user_service.py
├── utils/
│   └── .gitkeep
├── .env.example
├── .gitignore
├── Dockerfile
├── config.py
├── main.py
├── requirements.txt
└── runtime.txt

---

## 🚀 Instalación y despliegue

### Requisitos previos

- Python 3.10 o superior
- Token de bot de Telegram (crear con [@BotFather](https://t.me/BotFather))
- Base de datos PostgreSQL (Aiven, Supabase o local)

### Instalación local

```bash
# Clonar el repositorio
git clone https://github.com/danyventura5681-boop/LinkForge.git
cd LinkForge

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
export BOT_TOKEN="tu_token_aqui"
export DATABASE_URL="postgresql://usuario:pass@host:5432/db"

# Ejecutar el bot
python main.py


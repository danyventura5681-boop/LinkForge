FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias del sistema para Pillow
RUN apt-get update && apt-get install -y \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero para aprovechar caché
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Comando para iniciar el bot
CMD ["python", "main.py"]
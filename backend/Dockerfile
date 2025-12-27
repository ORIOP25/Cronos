# 1. Usar Python 3.12 (versão leve)
FROM python:3.12-slim

# 2. Configurações para Python em Docker (logs imediatos, sem .pyc)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Criar pasta de trabalho dentro do Docker
WORKDIR /app

# 4. Instalar ferramentas de sistema necessárias (para compilar libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. Copiar a lista de compras e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copiar o código todo do projeto para dentro do Docker
COPY . .

# 7. Expor a porta 8000
EXPOSE 8000

# 8. Comando para arrancar a API (por defeito)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
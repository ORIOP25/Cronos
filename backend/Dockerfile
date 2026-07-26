# Usar Python 3.12 (versão leve)
FROM python:3.12.13-slim@sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28 AS runtime

# Configurações para Python em Docker (logs imediatos, sem .pyc)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Criar pasta de trabalho dentro do Docker
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

RUN addgroup --system cronos && adduser --system --ingroup cronos cronos \
    && chown -R cronos:cronos /app
USER cronos

# Expor a porta 8000
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS ci
USER root
COPY requirements-dev.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements-dev.txt
COPY scripts ./scripts
USER cronos

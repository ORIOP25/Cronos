# Usar Python 3.12 (versão leve)
FROM python:3.14.6-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6 AS base

# Configurações para Python em Docker (logs imediatos, sem .pyc)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Builder stage: install dependencies into an isolated venv using a pip
# cache mount, so rebuilds are fast and the cache never ends up in a layer.
FROM base AS builder
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --require-hashes -r requirements.txt

# Extends the builder venv with dev/test dependencies for the ci target only.
FROM builder AS builder-dev
COPY requirements-dev.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --require-hashes -r requirements-dev.txt

# Runtime stage: only the venv + app code, no compilers/pip cache/build tools.
FROM base AS runtime
COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

RUN addgroup --system cronos && adduser --system --ingroup cronos cronos \
    && chown -R cronos:cronos /app
USER cronos

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS ci
USER root
COPY --from=builder-dev /opt/venv /opt/venv
COPY scripts ./scripts
USER cronos

# Usar Python 3.14 (versão leve)
FROM python:3.15.0rc3-slim@sha256:a3af3d230522dd52f7f2191b39e1892912dbcb0c8dee22afdec3dc83baf0f549 AS base

# Configurações para Python em Docker (logs imediatos, sem .pyc)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Builder stage: install dependencies into an isolated venv. Railway requires
# cache-mount IDs to contain a service ID, but this Dockerfile is shared by the
# API, worker, beat, and bootstrap services, so layer caching is used instead.
FROM base AS builder
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
# standardwebhooks 1.0.1 publishes only a source distribution. Its locked hash
# keeps this explicit exception reproducible while all other packages use wheels.
RUN pip install \
    --require-hashes \
    --only-binary=:all: \
    --no-binary=standardwebhooks \
    -r requirements.txt

# Extends the builder venv with dev/test dependencies for the ci target only.
FROM builder AS builder-dev
COPY requirements-dev.txt .
RUN pip install \
    --require-hashes \
    --only-binary=:all: \
    --no-binary=standardwebhooks \
    -r requirements-dev.txt

# Runtime stage: only the venv + app code, no compilers/pip cache/build tools.
FROM base AS runtime
COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
# The administrative privacy erasure runs in the API container; the image
# ships only its code.
COPY scripts/__init__.py scripts/privacy.py ./scripts/

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

# Keep the production stage as the Dockerfile default. Railway services build
# this file without a target; CI opts into the explicit `ci` target above.
FROM runtime AS production

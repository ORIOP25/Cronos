from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import asyncio as aioredis

# --- Imports de Performance e Segurança ---
from slowapi.errors import RateLimitExceeded

from app.api.api import api_router
from app.config import settings
from app.core.clerk import ClerkGateway
from app.core.exceptions import (
    PUBLIC_ERROR_CATALOG,
    REQUEST_ID_HEADER,
    AppError,
    public_error_detail,
    request_reference,
    status_code_for_kind,
)
from app.core.logging import safe_exception_frames, setup_logging
from app.core.ratelimit import FailClosedSlowAPIMiddleware, limiter
from app.db.database import SessionLocal, engine_async
from app.middleware.request_body_limit import RequestBodyLimitMiddleware

# ==========================================
# CICLO DE VIDA (LIFESPAN)
# ==========================================

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Configurar Logs (PRIMEIRA COISA A FAZER)
    setup_logging()

    # Substituir print por logger.info
    logger.info(
        "-> Servidor a arrancar...",
        version="0.5",
        env=settings.ENVIRONMENT,
        revision=settings.RAILWAY_GIT_COMMIT_SHA or settings.DEPLOYED_REVISION or "unknown",
    )

    redis = aioredis.from_url(str(settings.REDIS_URL), socket_connect_timeout=1)
    app.state.redis = redis
    async with ClerkGateway() as clerk, httpx.AsyncClient() as http_client:
        app.state.clerk = clerk
        app.state.http_client = http_client
        try:
            try:
                await redis.ping()
                logger.info("redis_ready")
            except Exception as exc:
                logger.warning("redis_not_ready", error_type=type(exc).__name__)
            logger.info("rate_limit_configured", enabled=settings.RATELIMIT_ENABLED)
            yield
        finally:
            await redis.close()
            await engine_async.dispose()
            logger.info("ZZZ Servidor a desligar...")


# ==========================================
# INICIALIZAÇÃO DA APP
# ==========================================

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API Escolar Profissional com rate limiting e Docker.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
    redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
    openapi_url=None if settings.ENVIRONMENT == "production" else "/openapi.json",
)


def _legacy_public_context(code: str, metadata: dict) -> dict:
    """Keep explicitly safe fields from pre-contract callers during migration."""
    if code == "preflight_failed":
        return {key: metadata[key] for key in ("status", "report", "issues") if key in metadata}
    return {
        key: metadata[key]
        for key in ("job_id", "pending_draft_id", "draft_state")
        if key in metadata
    }


def _cors_headers(request: Request) -> dict[str, str]:
    """Expose error responses to the exact browser origins already allowed.

    Unexpected exceptions are rendered by the outermost server-error middleware,
    which sits outside the CORS middleware. Without this, a cross-origin browser
    sees a network failure instead of the real HTTP status. Only origins already
    allowed by configuration receive the header; everything else stays rejected.
    """
    headers = getattr(request, "headers", None)
    origin = headers.get("origin") if headers is not None else None
    if origin and origin in settings.CORS_ORIGINS_LIST:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Expose-Headers": REQUEST_ID_HEADER,
            "Vary": "Origin",
        }
    return {}


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    public_context: dict | None = None,
    fields: dict[str, str] | None = None,
    retryable: bool | None = None,
    support_required: bool | None = None,
    headers: dict[str, str] | None = None,
    reference: str | None = None,
    diagnostic_metadata: dict | None = None,
) -> JSONResponse:
    reference = reference or request_reference(request)
    headers = {**(headers or {}), **_cors_headers(request)}
    route = getattr(request, "scope", {}).get("route")
    route_template = getattr(route, "path", None) or "unmatched"
    diagnostic = {}
    if isinstance(diagnostic_metadata, dict):
        job_id = diagnostic_metadata.get("job_id")
        if isinstance(job_id, int) and not isinstance(job_id, bool):
            diagnostic["job_id"] = job_id
    catalog = PUBLIC_ERROR_CATALOG.get(code, {})
    logger.info(
        "public_error_response",
        request_id=reference,
        code=code,
        status_code=status_code,
        method=request.method,
        route=route_template,
        retryable=catalog.get("retryable", False) if retryable is None else retryable,
        support_required=catalog.get("support_required", False)
        if support_required is None
        else support_required,
        **diagnostic,
    )
    response = JSONResponse(
        status_code=status_code,
        content={
            "detail": public_error_detail(
                code=code,
                reference=reference,
                status_code=status_code,
                public_context=public_context,
                fields=fields,
                retryable=retryable,
                support_required=support_required,
            )
        },
        headers=headers,
    )
    response.headers[REQUEST_ID_HEADER] = reference
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    reference = request_reference(request)
    logger.error(
        "unhandled_application_error",
        method=request.method,
        path=request.url.path,
        request_id=reference,
        error_type=type(exc).__name__,
        exception_frames=safe_exception_frames(exc),
    )
    return _error_response(
        request,
        status_code=500,
        code="unexpected_error",
        support_required=True,
        reference=reference,
    )


# --- Configuração do Rate Limiter ---
app.state.limiter = limiter
app.add_middleware(FailClosedSlowAPIMiddleware)
app.add_middleware(
    RequestBodyLimitMiddleware,
    default_max_bytes=1024 * 1024,
    path_limits={
        ("POST", "/api/v1/contact"): 16 * 1024,
        ("POST", "/api/v1/webhooks/clerk"): 256 * 1024,
        ("POST", "/api/v1/client-errors"): 4 * 1024,
        ("POST", "/api/v1/imports/validate"): 8 * 1024 * 1024,
        ("POST", "/api/v1/imports/commit"): 8 * 1024 * 1024,
    },
)

# --- Configuração de CORS ---
# Nota: Em produção, deves restringir isto aos domínios reais
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=[REQUEST_ID_HEADER],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    reference = request_reference(request)
    request.state.request_reference = reference
    with structlog.contextvars.bound_contextvars(request_id=reference):
        response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = reference
    return response


async def rate_limit_error_handler(request: Request, exc: RateLimitExceeded):
    return _error_response(
        request,
        status_code=429,
        code="too_many_requests",
        retryable=True,
        headers={"Retry-After": "60"},
    )


app.add_exception_handler(RateLimitExceeded, rate_limit_error_handler)


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    code = detail.get("code") or {
        400: "bad_request",
        401: "authentication_required",
        403: "access_forbidden",
        404: "resource_not_found",
        409: "conflict",
        422: "validation_error",
        429: "too_many_requests",
    }.get(exc.status_code, "unexpected_error")
    catalog = PUBLIC_ERROR_CATALOG.get(code, {})
    context = {
        key: detail[key]
        for key in (
            "foundation_status",
            "current_version",
            "terms_version",
            "dpa_version",
            "privacy_version",
        )
        if key in detail
    }
    headers = {
        key: value
        for key, value in (exc.headers or {}).items()
        if key.lower() in {"www-authenticate", "retry-after"}
    }
    return _error_response(
        request,
        status_code=exc.status_code,
        code=code,
        public_context=context,
        retryable=catalog.get("retryable"),
        headers=headers or None,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    fields = {}
    for item in exc.errors():
        location = item.get("loc") or ()
        field_name = ".".join(
            str(part) for part in location if part not in {"body", "query", "path", "header"}
        )
        if field_name:
            fields[field_name] = "Valor inválido."
    return _error_response(
        request,
        status_code=422,
        code="validation_error",
        fields=fields,
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    status_code = status_code_for_kind(exc.kind, exc.code)
    return _error_response(
        request,
        status_code=status_code,
        code=exc.code,
        public_context=exc.public_context or _legacy_public_context(exc.code, exc.metadata),
        fields=exc.public_fields
        or (exc.metadata.get("fields") if isinstance(exc.metadata.get("fields"), dict) else None),
        retryable=exc.public_retryable,
        support_required=exc.public_support_required,
        diagnostic_metadata=exc.diagnostic_metadata,
    )


# --- Security Headers ---
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ==========================================
# ROTAS (ROUTERS)
# ==========================================

# 1. Incluir todas as rotas da API v1 (Centralização)
app.include_router(api_router, prefix=settings.API_V1_STR)


# 2. Rota Raiz (Boas vindas simples)
# Mantemos esta rota fora do /api/v1 apenas para testes rápidos de conectividade
@app.get("/", tags=["Root"])
def root():
    return {
        "status": "online",
        "version": settings.APP_VERSION,
        "system": "Cronos",
    }


@app.get("/health/live", include_in_schema=False)
@limiter.exempt
async def live():
    return {
        "status": "ok",
        "revision": settings.RAILWAY_GIT_COMMIT_SHA or settings.DEPLOYED_REVISION or "unknown",
    }


@app.get("/health/ready", include_in_schema=False)
@limiter.exempt
async def ready(request: Request):
    from app.api.v1.endpoints.health import readiness

    async with SessionLocal() as db:
        return await readiness(request, db)

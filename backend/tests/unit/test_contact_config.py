import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings

BASE = {
    "DATABASE_URL": "postgresql+asyncpg://user:password@localhost:5432/cronos_test_db",
    "FRONTEND_URL": "http://localhost:5173",
    "CLERK_AUTHORIZED_PARTIES": "http://localhost:5173",
}
PRODUCTION = {
    **BASE,
    "ENVIRONMENT": "production",
    "FRONTEND_URL": "https://cronos.pt",
    "CORS_ORIGINS": "https://cronos.pt",
    "CLERK_AUTHORIZED_PARTIES": "https://cronos.pt",
    "CLERK_SECRET_KEY": "clerk-secret",
    "CLERK_WEBHOOK_SECRET": "webhook-secret",
    "CELERY_BROKER_URL": "redis://redis:6379/0",
    "RESEND_API_KEY": "resend-secret",
    "TURNSTILE_SECRET_KEY": "turnstile-secret",
    "TRUSTED_PROXY_IPS": "10.0.0.0/8",
}


def make_settings(**changes):
    return Settings(**(BASE | changes))


@pytest.mark.parametrize("secret", ["RESEND_API_KEY", "TURNSTILE_SECRET_KEY"])
def test_production_requires_contact_secrets(secret):
    values = PRODUCTION | {secret: None}
    with pytest.raises(ValidationError, match=secret):
        Settings(**values)


def test_contact_secrets_use_secret_str():
    configured = Settings(**PRODUCTION)
    assert isinstance(configured.RESEND_API_KEY, SecretStr)
    assert isinstance(configured.TURNSTILE_SECRET_KEY, SecretStr)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("CONTACT_EMAIL_TIMEOUT_SECONDS", 0),
        ("CONTACT_EMAIL_TIMEOUT_SECONDS", 31),
        ("TURNSTILE_TIMEOUT_SECONDS", 0),
        ("TURNSTILE_TIMEOUT_SECONDS", 31),
        ("TURNSTILE_ALLOWED_HOSTNAMES", " , "),
    ],
)
def test_contact_configuration_bounds_are_enforced(field, value):
    with pytest.raises(ValidationError):
        make_settings(**{field: value})


def test_invalid_trusted_proxy_network_prevents_startup():
    with pytest.raises(ValidationError, match="not-a-network"):
        make_settings(TRUSTED_PROXY_IPS="not-a-network")


def test_production_requires_explicit_trusted_proxy_network():
    with pytest.raises(ValidationError, match="TRUSTED_PROXY_IPS"):
        Settings(**(PRODUCTION | {"TRUSTED_PROXY_IPS": ""}))


@pytest.mark.parametrize("network", ["0.0.0.0/0", "::/0"])
def test_production_rejects_universal_trusted_proxy_network(network):
    with pytest.raises(ValidationError, match="entire address space"):
        Settings(**(PRODUCTION | {"TRUSTED_PROXY_IPS": network}))

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings

BASE = {
    "DATABASE_URL": "postgresql+asyncpg://user:password@localhost:5432/cronos_test_db",
    "FRONTEND_URL": "http://localhost:5173",
    "CLERK_AUTHORIZED_PARTIES": "http://localhost:5173",
}


def make_settings(**changes):
    return Settings(**(BASE | changes))


def test_local_settings_allow_missing_contact_password():
    assert make_settings().CONTACT_SMTP_PASSWORD is None


def test_production_requires_contact_password():
    with pytest.raises(ValidationError, match="CONTACT_SMTP_PASSWORD"):
        make_settings(ENVIRONMENT="production", FRONTEND_URL="https://app.cronos.pt", CLERK_AUTHORIZED_PARTIES="https://app.cronos.pt")


def test_contact_password_is_secret():
    assert isinstance(make_settings(CONTACT_SMTP_PASSWORD="secret").CONTACT_SMTP_PASSWORD, SecretStr)


@pytest.mark.parametrize(("field", "value"), [("CONTACT_SMTP_PORT", 0), ("CONTACT_SMTP_PORT", 65536), ("CONTACT_SMTP_TIMEOUT_SECONDS", 0), ("CONTACT_SMTP_TIMEOUT_SECONDS", 31)])
def test_contact_connection_bounds_are_enforced(field, value):
    with pytest.raises(ValidationError):
        make_settings(**{field: value})

import pytest
from pydantic import ValidationError

from app.config import Settings

BASE = {
    "DATABASE_URL": "postgresql://user:pass@localhost/test_db",
    "SECRET_KEY": "test",
}


def test_authorized_parties_default_to_normalized_frontend_origin():
    configured = Settings(**BASE, FRONTEND_URL="HTTP://LOCALHOST:5173/")
    assert configured.FRONTEND_URL == "http://localhost:5173"
    assert configured.CLERK_AUTHORIZED_PARTIES_LIST == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_authorized_parties_accept_multiple_exact_origins():
    configured = Settings(
        **BASE,
        FRONTEND_URL="https://app.example.com",
        CLERK_AUTHORIZED_PARTIES="https://app.example.com, https://preview.example.com:444",
    )
    assert configured.CLERK_AUTHORIZED_PARTIES_LIST == [
        "https://app.example.com",
        "https://preview.example.com:444",
    ]


@pytest.mark.parametrize("clock_skew_ms", [-1, 60_001])
def test_clerk_clock_skew_must_be_bounded(clock_skew_ms):
    with pytest.raises(ValidationError, match="CLERK_CLOCK_SKEW_MS"):
        Settings(
            **BASE,
            FRONTEND_URL="https://app.example.com",
            CLERK_CLOCK_SKEW_MS=clock_skew_ms,
        )


@pytest.mark.parametrize("timeout_seconds", [0, 31])
def test_clerk_access_timeout_must_be_bounded(timeout_seconds):
    with pytest.raises(ValidationError, match="CLERK_ACCESS_TIMEOUT_SECONDS"):
        Settings(
            **BASE,
            FRONTEND_URL="https://app.example.com",
            CLERK_ACCESS_TIMEOUT_SECONDS=timeout_seconds,
        )


@pytest.mark.parametrize(
    "parties",
    [
        "https://*.example.com",
        "https://app.example.com/path",
        "https://app.example.com?x=1",
        "https://other.example.com",
    ],
)
def test_invalid_or_mismatched_authorized_parties_fail_startup(parties):
    with pytest.raises(ValidationError):
        Settings(
            **BASE,
            FRONTEND_URL="https://app.example.com",
            CLERK_AUTHORIZED_PARTIES=parties,
        )

import httpx
import pytest

from app.contact.turnstile_verifier import CloudflareTurnstileVerifier
from app.core.exceptions import AppError


async def verify_with_payload(payload, *, status=200):
    async def handler(request):
        assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
        assert b"secret=secret" in await request.aread()
        return httpx.Response(status, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = CloudflareTurnstileVerifier(
            client,
            secret_key="secret",
            allowed_hostnames={"cronos.pt", "www.cronos.pt"},
            timeout_seconds=5,
        )
        await verifier.verify("token", remote_ip="192.0.2.10")


@pytest.mark.asyncio
async def test_accepts_expected_action_and_hostname():
    await verify_with_payload({"success": True, "action": "contact", "hostname": "cronos.pt"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"success": False, "action": "contact", "hostname": "cronos.pt"},
        {"success": True, "action": "login", "hostname": "cronos.pt"},
        {"success": True, "action": "contact", "hostname": "attacker.example"},
    ],
)
async def test_rejects_invalid_challenge_shape(payload):
    with pytest.raises(AppError) as exc_info:
        await verify_with_payload(payload)
    assert exc_info.value.kind == "bad_request"


@pytest.mark.asyncio
async def test_network_failure_is_unavailable():
    async def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = CloudflareTurnstileVerifier(
            client,
            secret_key="secret",
            allowed_hostnames={"cronos.pt"},
            timeout_seconds=5,
        )
        with pytest.raises(AppError) as exc_info:
            await verifier.verify("token", remote_ip=None)
    assert exc_info.value.kind == "unavailable"


@pytest.mark.asyncio
async def test_invalid_provider_json_is_unavailable():
    async def handler(request):
        return httpx.Response(200, text="not-json")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = CloudflareTurnstileVerifier(
            client,
            secret_key="secret",
            allowed_hostnames={"cronos.pt"},
            timeout_seconds=5,
        )
        with pytest.raises(AppError) as exc_info:
            await verifier.verify("token", remote_ip=None)
    assert exc_info.value.kind == "unavailable"

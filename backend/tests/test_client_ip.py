from types import SimpleNamespace

from app.config import settings
from app.core.client_ip import get_client_ip


def request(peer, headers=None):
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers or {})


def test_untrusted_peer_cannot_spoof_forwarded_headers(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", "100.0.0.0/8")
    assert get_client_ip(request("192.0.2.10", {"x-real-ip": "203.0.113.8"})) == "192.0.2.10"


def test_trusted_railway_proxy_uses_x_real_ip(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", "100.0.0.0/8")
    assert get_client_ip(request("100.64.0.10", {"x-real-ip": "203.0.113.8"})) == "203.0.113.8"


def test_invalid_real_ip_fails_closed_to_peer(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", "100.0.0.0/8")
    assert get_client_ip(request("100.64.0.10", {"x-real-ip": "not-an-ip"})) == "100.64.0.10"


def test_trusted_proxy_chain_selects_first_untrusted_hop(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", "100.0.0.0/8")
    headers = {"x-forwarded-for": "203.0.113.8, 100.64.0.11"}
    assert get_client_ip(request("100.64.0.10", headers)) == "203.0.113.8"

"""Trusted-proxy client IP resolution."""

from ipaddress import ip_address

from fastapi import Request

from app.config import settings


def get_client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    peer = request.client.host
    try:
        peer_address = ip_address(peer)
    except ValueError:
        return None
    if not any(peer_address in network for network in settings.TRUSTED_PROXY_NETWORKS):
        return str(peer_address)

    railway_real_ip = request.headers.get("x-real-ip", "").strip()
    if railway_real_ip:
        try:
            return str(ip_address(railway_real_ip))
        except ValueError:
            return str(peer_address)

    forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",")]
    chain = [value for value in forwarded if value]
    for value in reversed(chain):
        try:
            candidate = ip_address(value)
        except ValueError:
            return str(peer_address)
        if not any(candidate in network for network in settings.TRUSTED_PROXY_NETWORKS):
            return str(candidate)
    return str(peer_address)


def trusted_remote_address(request: Request) -> str:
    return get_client_ip(request) or "unknown"

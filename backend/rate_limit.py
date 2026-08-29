"""
Shared slowapi Limiter instance — see ARCHITECTURE.md D3.

Lives in its own module so both main.py (which registers it on the app)
and routers/chat.py (which decorates endpoints with it) can import it
without a circular import.

Key function: trusted-proxy-aware client IP (H1 in the deployment-readiness
pass). `get_remote_address` alone reads `request.client.host`, which behind
any reverse proxy / load balancer is the *proxy's* IP, not the visitor's —
every real client then shares one rate-limit bucket, which is effectively no
rate limiting at all for a public deploy fronted by a proxy.

`X-Forwarded-For` (or `X-Real-IP`) *would* carry the real client IP, but
trusting it unconditionally is worse than not rate-limiting at all: any
direct caller can set that header to whatever they like and either evade the
limit entirely (spoof a fresh IP per request) or frame another client's IP.
So the header is only honored when the *directly connecting peer* — the
thing slowapi would otherwise trust as `request.client.host` — is in a
configured set of trusted proxies. With nothing configured, this behaves
exactly like plain `get_remote_address`.
"""
import ipaddress
import os
from typing import List

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

# Trusted proxy IPs/CIDRs. Empty by default, so forwarded headers are ignored.
def _parse_trusted_proxies(raw: str) -> List["ipaddress._BaseNetwork"]:
    networks = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return networks


TRUSTED_PROXY_IPS = _parse_trusted_proxies(os.getenv("TRUSTED_PROXY_IPS", ""))


def _is_trusted_proxy(peer_ip: str) -> bool:
    if not TRUSTED_PROXY_IPS:
        return False
    try:
        addr = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    return any(addr in network for network in TRUSTED_PROXY_IPS)


def get_client_ip(request: Request) -> str:
    """
    slowapi key_func: the directly connecting peer's IP, UNLESS that peer is
    a configured trusted proxy — in which case the client IP it forwarded
    (X-Forwarded-For's left-most/original entry, falling back to
    X-Real-IP) is used instead. Never trusts either header from an
    untrusted (or unconfigured) peer.
    """
    peer_ip = get_remote_address(request)

    if not _is_trusted_proxy(peer_ip):
        return peer_ip

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # The left-most address is the client reported by the trusted proxy.
        client_ip = forwarded_for.split(",")[0].strip()
        if client_ip:
            return client_ip

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    return peer_ip


limiter = Limiter(key_func=get_client_ip)

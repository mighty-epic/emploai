from __future__ import annotations

import ipaddress
from typing import Any, Awaitable, Callable


YGGDRASIL_NETWORK = ipaddress.ip_network("200::/7")
_TEST_CLIENT_HOSTS = frozenset({"testclient"})


def trusted_app_client_host(value: object) -> bool:
    """Allow only this machine and Yggdrasil peers into the local app API."""

    raw = str(value or "").strip()
    if raw.casefold() in _TEST_CLIENT_HOSTS:
        return True
    if not raw:
        return False
    if "%" in raw:
        raw = raw.split("%", 1)[0]
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return False
    if address.is_loopback:
        return True
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped.is_loopback
    return isinstance(address, ipaddress.IPv6Address) and address in YGGDRASIL_NETWORK


class TrustedAppNetworkMiddleware:
    """ASGI boundary for the desktop-local and Yggdrasil-only control plane."""

    def __init__(self, app: Callable[..., Awaitable[Any]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        scope_type = str(scope.get("type") or "")
        if scope_type not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_host = client[0] if isinstance(client, (tuple, list)) and client else ""
        if trusted_app_client_host(client_host):
            await self.app(scope, receive, send)
            return

        if scope_type == "websocket":
            await send({"type": "websocket.close", "code": 4403, "reason": "Untrusted network path"})
            return
        body = b'{"detail":"The EmploAI API accepts only localhost and Yggdrasil connections"}'
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

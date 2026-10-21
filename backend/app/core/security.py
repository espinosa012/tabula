"""Request guard that keeps the local API reachable only from its own UI.

The app has no authentication, so any web page open in the user's browser
could otherwise drive the API (CSRF) or reach it through DNS rebinding. The
guard rejects requests whose Host header is not a local name and requests
that a browser marks as coming from another origin.
"""
import os
from typing import Iterable, Optional, Set
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost", "::1")
WILDCARD_BIND_HOSTS = ("", "0.0.0.0", "::")


def _hostname(netloc: str) -> Optional[str]:
    """Extract the lowercase hostname from a 'host[:port]' string."""
    try:
        name = urlsplit(f"//{netloc}").hostname
    except ValueError:
        return None
    return name.lower() if name else None


def allowed_hosts_from_env() -> Set[str]:
    """Local names plus the bind HOST and any extra ALLOWED_HOSTS (comma-separated)."""
    hosts = set(DEFAULT_ALLOWED_HOSTS)
    bind_host = os.environ.get("HOST", "").strip().lower()
    if bind_host not in WILDCARD_BIND_HOSTS:
        hosts.add(bind_host.strip("[]"))
    for extra in os.environ.get("ALLOWED_HOSTS", "").split(","):
        extra = extra.strip().lower()
        if extra:
            hosts.add(extra.strip("[]"))
    return hosts


class LocalRequestGuard:
    """ASGI middleware enforcing a local Host header and same-origin browser requests."""

    def __init__(self, app, allowed_hosts: Optional[Iterable[str]] = None):
        self.app = app
        self.allowed_hosts = (
            {h.lower() for h in allowed_hosts} if allowed_hosts is not None else allowed_hosts_from_env()
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        reason = self._reject_reason(headers, scope.get("path", ""))
        if reason:
            response = JSONResponse({"detail": reason}, status_code=403)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _reject_reason(self, headers, path: str) -> Optional[str]:
        host_header = headers.get("host", "")
        if _hostname(host_header) not in self.allowed_hosts:
            return "Host not allowed."

        # Browsers send Origin on cross-origin fetches and on every form/fetch POST.
        origin = headers.get("origin")
        if origin is not None:
            parsed = urlsplit(origin) if origin != "null" else None
            if not parsed or parsed.netloc.lower() != host_header.lower():
                return "Cross-origin requests are not allowed."

        # Covers no-cors API requests (<img>, <script>) that omit Origin. Static
        # pages stay reachable from external links.
        if path.startswith("/api") and headers.get("sec-fetch-site") == "cross-site":
            return "Cross-site requests are not allowed."
        return None

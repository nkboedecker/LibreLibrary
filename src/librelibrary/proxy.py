"""Honor the scheme a trusted reverse proxy reports."""

from starlette.types import ASGIApp, Receive, Scope, Send

from librelibrary.api.deps import is_trusted_proxy

_SCHEMES = {
    "http": {"http": "http", "https": "https"},
    "websocket": {"http": "ws", "https": "wss"},
}


class ForwardedProtoMiddleware:
    """Set the request scheme from `X-Forwarded-Proto`, but only from trusted proxies.

    Without this, a server behind a TLS-terminating proxy sees every request as
    plain HTTP, so the redirects it builds point at `http://`.
    """

    def __init__(self, app: ASGIApp, trusted_proxies: list[str]) -> None:
        """Wrap `app`, believing the header only from `trusted_proxies`."""
        self.app = app
        self.trusted_proxies = trusted_proxies

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Replace the scope's scheme when a trusted proxy sent a valid one."""
        if scope["type"] in _SCHEMES:
            client = scope.get("client")
            if client and is_trusted_proxy(client[0], self.trusted_proxies):
                scheme = self._forwarded_scheme(scope)
                if scheme:
                    scope["scheme"] = _SCHEMES[scope["type"]][scheme]
        await self.app(scope, receive, send)

    @staticmethod
    def _forwarded_scheme(scope: Scope) -> str | None:
        """Return the last scheme a proxy appended, if it is one we know."""
        for name, value in scope["headers"]:
            if name == b"x-forwarded-proto":
                last = value.decode("latin-1").split(",")[-1].strip().lower()
                return last if last in ("http", "https") else None
        return None

import hmac

from unlockops.settings import settings


class TokenAuth:
    """Protect every MCP HTTP request, including tool discovery."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            supplied = headers.get(b"authorization", b"").decode("latin1")
            if not settings.mcp_token or not hmac.compare_digest(supplied, "Bearer " + settings.mcp_token):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
                return
            if scope.get("path") == "/health":
                await send({"type": "http.response.start", "status": 200,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"status":"UP"}'})
                return
        await self.app(scope, receive, send)

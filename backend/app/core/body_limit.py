"""Enforce limits on bytes actually received, including chunked multipart uploads."""
import json

from starlette.formparsers import MultiPartException


class BodyLimitMiddleware:
    def __init__(self, app, upload_bytes, source_bytes):
        self.app = app
        self.upload_bytes = upload_bytes + 1024 * 1024
        self.source_bytes = source_bytes + 1024 * 1024

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        limit = self.upload_bytes if path == "/api/v1/monthly-runs" else (
            self.source_bytes if path == "/api/v1/source-files" else 1024 * 1024)
        response_body = json.dumps({
            "type": "urn:datastage:problem:request_too_large", "title": "REQUEST_TOO_LARGE",
            "status": 413, "detail": "La solicitud supera el tamaño permitido", "instance": path,
        }).encode()
        seen, exceeded, started, body_sent = 0, False, False, False

        async def limited_receive():
            nonlocal seen, exceeded
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    exceeded = True
                    # Starlette's multipart parser closes its spool files on this exception.
                    raise MultiPartException("Request body limit exceeded")
            return message

        async def limited_send(message):
            nonlocal started, body_sent
            if exceeded:
                if message["type"] == "http.response.start":
                    started = True
                    await send({"type": "http.response.start", "status": 413, "headers": [
                        *[(key, value) for key, value in message.get("headers", [])
                          if key.lower().startswith(b"access-control-") or key.lower() == b"vary"],
                        (b"content-type", b"application/problem+json"),
                        (b"content-length", str(len(response_body)).encode()),
                        (b"cache-control", b"no-store")]})
                elif message["type"] == "http.response.body" and not body_sent:
                    body_sent = True
                    await send({"type": "http.response.body", "body": response_body, "more_body": False})
            else:
                if message["type"] == "http.response.start":
                    started = True
                await send(message)

        try:
            await self.app(scope, limited_receive, limited_send)
        except MultiPartException:
            if not started:
                exceeded = True
                await limited_send({"type": "http.response.start"})
                await limited_send({"type": "http.response.body"})
            else:
                raise

"""Bound request bodies before multipart parsing, including chunked requests."""

from __future__ import annotations
from starlette.responses import JSONResponse


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in (
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        ):
            return await self.app(scope, receive, send)
        chunks = []
        length = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            block = message.get("body", b"")
            length += len(block)
            if length > self.max_bytes:
                response = JSONResponse(
                    {"detail": "请求体超过9MiB上限（包含分块和文件封装）"},
                    status_code=413,
                )
                await response(scope, receive, send)
                return
            chunks.append(block)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        del chunks
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

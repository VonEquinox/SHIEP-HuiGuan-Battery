from __future__ import annotations
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.exc import IntegrityError
from .db import initialize
from .body_limit import RequestBodyLimitMiddleware
from .jobs import JobSupervisor
from .config import APP_ROOT
from .api_core import router as core
from .api_data import router as data
from .api_ops import router as ops


@asynccontextmanager
async def lifespan(app):
    initialize()
    supervisor = JobSupervisor()
    if os.environ.get("BATTERY_DISABLE_WORKER") != "1":
        supervisor.start()
    app.state.supervisor = supervisor
    try:
        yield
    finally:
        supervisor.stop()


app = FastAPI(title="慧管电池 · 新平台 API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
)


app.add_middleware(RequestBodyLimitMiddleware, max_bytes=9 * 1024 * 1024)


@app.middleware("http")
async def headers(request: Request, call_next):
    length = request.headers.get("content-length")
    if length:
        try:
            large = int(length) > 9 * 1024 * 1024
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length"}, 400)
        if large:
            return JSONResponse({"detail": "请求体上限为9MiB"}, 413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = (
        "no-store" if request.url.path.startswith("/api") else "no-cache"
    )
    return response


@app.exception_handler(IntegrityError)
async def constraint(request, error):
    return JSONResponse(
        {"detail": "数据约束冲突，对象可能已存在或正被使用"}, status_code=409
    )


app.include_router(core)
app.include_router(data)
app.include_router(ops)
dist = APP_ROOT / "frontend/dist"
if (dist / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="static")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/") or path == "api":
        return JSONResponse({"detail": "接口不存在"}, 404)
    if (dist / "index.html").is_file():
        return FileResponse(dist / "index.html")
    return JSONResponse({"detail": "前端尚未构建。运行 ./manage.sh build"}, 503)

from __future__ import annotations
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
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
from .api_carbon import router as carbon
from .api_dispatch import router as dispatch
from .api_v2 import router as v2
from .api_agent import router as agent
from .api_inspection import router as inspection
from .api_evolution import router as evolution


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


app = FastAPI(title="慧管电池 · 新平台 API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"]
    + [h.strip() for h in os.environ.get("BATTERY_ALLOWED_HOSTS", "").split(",") if h.strip()],
)


app.add_middleware(RequestBodyLimitMiddleware, max_bytes=9 * 1024 * 1024)


@app.middleware("http")
async def headers(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
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
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = (
        "no-store" if request.url.path.startswith("/api") else "no-cache"
    )
    return response


def v2_error(request, status, detail, code=None, missing_fields=None):
    message = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
    return JSONResponse({"request_id": getattr(request.state, "request_id", uuid.uuid4().hex),
        "code": code or {401: "unauthenticated", 403: "forbidden", 404: "not_found", 409: "conflict", 422: "invalid_request"}.get(status, "request_failed"),
        "message": message, "missing_fields": missing_fields or [], "retryable": status in (429, 503), "detail": detail}, status_code=status)


@app.exception_handler(HTTPException)
async def http_error(request, error):
    if request.url.path.startswith("/api/v2"):
        return v2_error(request, error.status_code, error.detail)
    return JSONResponse({"detail": error.detail}, status_code=error.status_code, headers=error.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    if request.url.path.startswith("/api/v2"):
        return v2_error(request, 422, "请求格式或必填字段无效", missing_fields=[".".join(map(str, e["loc"])) for e in error.errors()])
    return JSONResponse({"detail": [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in error.errors()]}, status_code=422)


@app.exception_handler(IntegrityError)
async def constraint(request, error):
    if request.url.path.startswith("/api/v2"):
        return v2_error(request, 409, "数据约束冲突，对象可能已存在或正被使用")
    return JSONResponse(
        {"detail": "数据约束冲突，对象可能已存在或正被使用"}, status_code=409
    )


app.include_router(core)
app.include_router(data)
app.include_router(ops)
app.include_router(carbon)
app.include_router(dispatch)
app.include_router(v2)
app.include_router(agent)
app.include_router(inspection)
app.include_router(evolution)
dist = APP_ROOT / "frontend/dist"


@app.get("/assets/{asset_id:int}", include_in_schema=False)
def asset_frontend(asset_id: int):
    # Asset detail URLs share the V1 prefix with Vite's compiled resources.
    # Register the numeric SPA route first so StaticFiles cannot consume it.
    if (dist / "index.html").is_file():
        return FileResponse(dist / "index.html")
    return JSONResponse({"detail": "前端尚未构建。运行 ./manage.sh build"}, 503)


if (dist / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="static")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/") or path == "api":
        return JSONResponse({"detail": "接口不存在"}, 404)
    if (dist / "index.html").is_file():
        return FileResponse(dist / "index.html")
    return JSONResponse({"detail": "前端尚未构建。运行 ./manage.sh build"}, 503)

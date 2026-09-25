from __future__ import annotations
import hashlib
import secrets
import time
from urllib.parse import urlparse
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, Request
from .db import tx, one, execute, insert, now, audit
from .config import ROLES

hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(24))


def password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise HTTPException(422, "密码长度须为 12–128 个字符")
    return hasher.hash(password)


def verify(password, stored):
    try:
        return hasher.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def origin_check(request: Request):
    origin = request.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme not in (
            "http",
            "https",
        ) or parsed.netloc != request.headers.get("host"):
            raise HTTPException(403, "请求来源不匹配")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "禁止跨站修改")


def current_user(request: Request):
    token = request.cookies.get("hg_session", "")
    with tx() as c:
        session = one(
            c,
            """SELECT u.id,u.username,u.display_name,u.role,u.version,s.csrf
            FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=:h AND s.expires_at>:t AND u.active=1""",
            {"h": digest(token), "t": time.time()},
        )
    if not session:
        raise HTTPException(401, "请先登录")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin_check(request)
        if not secrets.compare_digest(
            request.headers.get("x-csrf-token", ""), session["csrf"]
        ):
            raise HTTPException(403, "CSRF 校验失败，请刷新后重试")
    return session


def allow(*roles):
    def dependency(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "当前角色没有此操作权限")
        return user

    return dependency


def create_user(c, username, display_name, password, role):
    if (
        role not in ROLES
        or not username
        or len(username) > 64
        or not display_name.strip()
    ):
        raise HTTPException(422, "用户信息无效")
    if one(c, "SELECT id FROM users WHERE username=:u", {"u": username}):
        raise HTTPException(409, "用户名已存在")
    return insert(
        c,
        "users",
        {
            "username": username,
            "display_name": display_name,
            "password_hash": password_hash(password),
            "role": role,
            "created_at": now(),
        },
    )


def login(request, username, password):
    origin_check(request)
    if len(username) > 64 or not 1 <= len(password) <= 128:
        raise HTTPException(401, "账号或密码错误")
    key = digest(
        username.lower() + "|" + (request.client.host if request.client else "local")
    )
    with tx() as c:
        limited = one(c, "SELECT * FROM login_attempts WHERE key=:k", {"k": key})
        if limited and limited["failures"] >= 8 and limited["until_at"] > time.time():
            raise HTTPException(429, "登录失败次数过多，请 5 分钟后重试")
        user = one(
            c, "SELECT * FROM users WHERE username=:u AND active=1", {"u": username}
        )
    ok = verify(password, user["password_hash"] if user else DUMMY_HASH)
    if not ok or not user:
        with tx() as c:
            count = (
                limited["failures"] + 1
                if limited and limited["until_at"] > time.time()
                else 1
            )
            execute(
                c,
                """INSERT INTO login_attempts(key,failures,until_at) VALUES(:k,:n,:t)
                ON CONFLICT(key) DO UPDATE SET failures=:n,until_at=:t""",
                {"k": key, "n": count, "t": time.time() + 300},
            )
            audit(c, None, "login_failed", "auth", username)
        raise HTTPException(401, "账号或密码错误")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    with tx() as c:
        execute(c, "DELETE FROM login_attempts WHERE key=:k", {"k": key})
        execute(c, "DELETE FROM sessions WHERE expires_at<=:t", {"t": time.time()})
        insert(
            c,
            "sessions",
            {
                "token_hash": digest(token),
                "user_id": user["id"],
                "csrf": csrf,
                "expires_at": time.time() + 28800,
            },
        )
        audit(c, user["id"], "login", "auth", user["id"])
    public = {k: user[k] for k in ("id", "username", "display_name", "role", "version")}
    return token, {**public, "csrf": csrf}

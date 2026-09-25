from __future__ import annotations
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from . import schemas as S
from .db import tx, rows, one, execute, insert, now, js, obj, audit
from .security import (
    current_user,
    allow,
    login,
    digest,
    create_user,
    password_hash,
    verify,
)
from .services import require, public, seed_demo, demo_bind

router = APIRouter(prefix="/api")


@router.get("/status")
def status():
    with tx() as c:
        ready = bool(one(c, "SELECT id FROM users LIMIT 1"))
    return {
        "application": "慧管电池",
        "version": "1.0.0",
        "initialized": ready,
        "mode": "experimental_and_simulated",
        "production_bms": False,
    }


@router.post("/auth/login")
def auth_login(data: S.Login, request: Request, response: Response):
    token, user = login(request, data.username, data.password)
    response.set_cookie(
        "hg_session",
        token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=28800,
        path="/",
    )
    return user


@router.get("/auth/me")
def me(user=Depends(current_user)):
    return user


@router.post("/auth/logout")
def logout(request: Request, response: Response, user=Depends(current_user)):
    with tx() as c:
        execute(
            c,
            "DELETE FROM sessions WHERE token_hash=:h",
            {"h": digest(request.cookies.get("hg_session", ""))},
        )
        audit(c, user["id"], "logout", "auth", user["id"])
    response.delete_cookie("hg_session", path="/")
    return {"ok": True}


def asset_health(c, asset):
    p = one(
        c,
        """SELECT p.*,s.ordinal,s.cell_id,s.sample_key,m.name model_name FROM predictions p
        JOIN samples s ON s.id=p.sample_id JOIN models m ON m.id=p.model_id
        WHERE p.asset_id=:i AND p.installation_id=:n ORDER BY s.ordinal DESC,p.id DESC LIMIT 1""",
        {"i": asset["id"], "n": asset["installation_id"]},
    )
    if not p:
        return {"state": "unknown", "prediction": None}
    policy = one(c, "SELECT * FROM policies WHERE active=1 ORDER BY id DESC LIMIT 1")
    stale = (
        datetime.now(timezone.utc) - datetime.fromisoformat(p["created_at"])
    ).total_seconds() > (policy["stale_seconds"] if policy else 86400)
    state = (
        "stale"
        if stale
        else (
            "review"
            if p["applicability"] != "within_observed_range"
            or p["provenance"] == "declared_unverified"
            else (
                "attention"
                if p["soh"] < (policy["threshold"] if policy else 0.85)
                else "normal"
            )
        )
    )
    return {"state": state, "prediction": p}


def aggregate_health(c, asset):
    if asset["kind"] == "cell":
        return None
    descendants = rows(
        c,
        """WITH RECURSIVE tree AS (
        SELECT * FROM assets WHERE id=:i AND active=1
        UNION ALL SELECT a.* FROM assets a JOIN tree t ON a.parent_id=t.id WHERE a.active=1)
        SELECT * FROM tree WHERE kind='cell' """,
        {"i": asset["id"]},
    )
    states = {k: 0 for k in ("normal", "attention", "review", "stale", "unknown")}
    available = []
    for cell in descendants:
        h = asset_health(c, cell)
        states[h["state"]] += 1
        if h["prediction"] and h["state"] != "stale":
            available.append(
                {
                    "asset_id": cell["id"],
                    "name": cell["name"],
                    "soh": h["prediction"]["soh"],
                    "prediction_id": h["prediction"]["id"],
                    "state": h["state"],
                }
            )
    available.sort(key=lambda p: p["soh"])
    return {
        "total_cells": len(descendants),
        "fresh_prediction_cells": len(available),
        "coverage": len(available) / len(descendants) if descendants else 0,
        "states": states,
        "lowest_estimated_cells": available[:5],
        "not_measured_pack_soh": True,
    }


@router.get("/dashboard")
def dashboard(user=Depends(current_user)):
    with tx() as c:
        assets = rows(c, "SELECT * FROM assets WHERE active=1 ORDER BY id")
        cells = [a for a in assets if a["kind"] == "cell"]
        states = {k: 0 for k in ("normal", "attention", "review", "stale", "unknown")}
        recent = []
        for cell in cells:
            h = asset_health(c, cell)
            states[h["state"]] += 1
            if h["prediction"]:
                recent.append(
                    {
                        **h["prediction"],
                        "asset_name": cell["name"],
                        "asset_code": cell["code"],
                        "state": h["state"],
                    }
                )
        return {
            "assets": len(assets),
            "cells": len(cells),
            "cabinet_count": sum(a["kind"] == "cabinet" for a in assets),
            "datasets": one(c, "SELECT count(*) n FROM datasets")["n"],
            "models": one(c, "SELECT count(*) n FROM models WHERE status='enabled'")[
                "n"
            ],
            "open_alerts": one(
                c, "SELECT count(*) n FROM alerts WHERE status!='RESOLVED'"
            )["n"],
            "active_orders": one(
                c,
                "SELECT count(*) n FROM orders WHERE status NOT IN ('CLOSED','CANCELLED')",
            )["n"],
            "completed_orders": one(
                c, "SELECT count(*) n FROM orders WHERE status='CLOSED'"
            )["n"],
            "queued_jobs": one(
                c, "SELECT count(*) n FROM jobs WHERE status IN ('queued','running')"
            )["n"],
            "coverage": (
                sum(v for k, v in states.items() if k not in ("unknown", "stale"))
                / len(cells)
                if cells
                else 0
            ),
            "health_states": states,
            "recent_predictions": recent[:12],
            "recent_alerts": rows(
                c,
                "SELECT a.*,s.name asset_name FROM alerts a JOIN assets s ON s.id=a.asset_id ORDER BY a.id DESC LIMIT 6",
            ),
            "activity": rows(
                c,
                "SELECT a.*,u.display_name actor FROM audit a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 10",
            ),
            "provenance": {
                "asset_fleet": "simulated",
                "experimental_data": "source_versioned",
                "production_connected": False,
            },
        }


@router.get("/assets")
def assets(user=Depends(current_user)):
    with tx() as c:
        result = rows(
            c,
            """SELECT a.*,b.dataset_id,b.cell_id source_cell_id,b.scenario_id FROM assets a
            LEFT JOIN bindings b ON a.id=b.asset_id WHERE a.active=1 ORDER BY a.id""",
        )
        for a in result:
            if a["kind"] == "cell":
                a["health"] = asset_health(c, a)
        return result


@router.post("/assets", status_code=201)
def add_asset(data: S.AssetCreate, user=Depends(allow("admin", "dispatcher"))):
    values = data.model_dump()
    with tx() as c:
        if one(c, "SELECT id FROM assets WHERE code=:c", {"c": data.code}):
            raise HTTPException(409, "资产编号已存在")
        parents = {"cabinet": "site", "module": "cabinet", "cell": "module"}
        if data.kind == "site" and data.parent_id is not None:
            raise HTTPException(422, "站点不能有父节点")
        if data.kind != "site":
            parent = require(c, "assets", data.parent_id)
            if not parent["active"] or parent["kind"] != parents[data.kind]:
                raise HTTPException(422, "资产层级不合法")
        values.update(
            installation_id=str(uuid.uuid4()), provenance="simulated", created_at=now()
        )
        identifier = insert(c, "assets", values)
        audit(c, user["id"], "asset_create", "asset", identifier)
        return require(c, "assets", identifier)


@router.put("/assets/{identifier}")
def edit_asset(
    identifier: int, data: S.AssetUpdate, user=Depends(allow("admin", "dispatcher"))
):
    with tx() as c:
        a = require(c, "assets", identifier)
        if a["version"] != data.version:
            raise HTTPException(409, "资产已经更新，请刷新")
        execute(
            c,
            """UPDATE assets SET name=:name,latitude=:latitude,longitude=:longitude,location=:location,
            version=version+1 WHERE id=:id AND version=:version""",
            dict(data.model_dump(), id=identifier),
        )
        audit(c, user["id"], "asset_update", "asset", identifier)
        return require(c, "assets", identifier)


@router.post("/assets/{identifier}/retire")
def retire_asset(
    identifier: int, data: S.VersionAction, user=Depends(allow("admin", "dispatcher"))
):
    with tx() as c:
        a = require(c, "assets", identifier)
        if a["version"] != data.version:
            raise HTTPException(409, "版本冲突")
        if one(
            c,
            "SELECT id FROM assets WHERE parent_id=:i AND active=1",
            {"i": identifier},
        ):
            raise HTTPException(409, "请先退役子资产")
        if one(
            c,
            "SELECT id FROM orders WHERE asset_id=:i AND status NOT IN ('CLOSED','CANCELLED')",
            {"i": identifier},
        ):
            raise HTTPException(409, "资产仍有关联未完成工单")
        execute(
            c,
            "UPDATE assets SET active=0,version=version+1 WHERE id=:i",
            {"i": identifier},
        )
        audit(c, user["id"], "asset_retire", "asset", identifier, {"note": data.note})
    return {"ok": True}


@router.post("/assets/{identifier}/replace")
def replace_asset(
    identifier: int, data: S.VersionAction, user=Depends(allow("admin", "dispatcher"))
):
    if len(data.note.strip()) < 3:
        raise HTTPException(422, "请提供更换记录")
    with tx() as c:
        a = require(c, "assets", identifier)
        if a["version"] != data.version or a["kind"] != "cell" or not a["active"]:
            raise HTTPException(409, "对象状态或版本不允许更换")
        new_id = str(uuid.uuid4())
        execute(
            c,
            "UPDATE assets SET installation_id=:n,version=version+1 WHERE id=:i",
            {"n": new_id, "i": identifier},
        )
        execute(c, "DELETE FROM bindings WHERE asset_id=:i", {"i": identifier})
        audit(
            c,
            user["id"],
            "installation_replace",
            "asset",
            identifier,
            {"previous": a["installation_id"], "new": new_id, "note": data.note},
        )
        return require(c, "assets", identifier)


@router.post("/assets/{identifier}/binding")
def bind_asset(
    identifier: int,
    data: S.Binding,
    user=Depends(allow("admin", "researcher", "dispatcher")),
):
    with tx() as c:
        a = require(c, "assets", identifier)
        require(c, "datasets", data.dataset_id)
        if a["kind"] != "cell" or not a["active"]:
            raise HTTPException(422, "只能绑定有效电芯槽位")
        if not one(
            c,
            "SELECT id FROM samples WHERE dataset_id=:d AND cell_id=:s",
            {"d": data.dataset_id, "s": data.cell_id},
        ):
            raise HTTPException(422, "数据源电芯不存在")
        previous = one(c, "SELECT * FROM bindings WHERE asset_id=:a", {"a": identifier})
        if previous and (
            previous["dataset_id"] != data.dataset_id
            or previous["cell_id"] != data.cell_id
        ):
            if one(
                c,
                "SELECT id FROM predictions WHERE asset_id=:a AND installation_id=:n",
                {"a": identifier, "n": a["installation_id"]},
            ):
                raise HTTPException(
                    409,
                    "已有预测的安装身份不能绑定另一个电芯；请先登记更换，保留原始历史",
                )
        execute(
            c,
            """INSERT INTO bindings(asset_id,dataset_id,cell_id,scenario_id,created_at) VALUES(:a,:d,:s,'experimental-replay-v1',:t)
            ON CONFLICT(asset_id) DO UPDATE SET dataset_id=excluded.dataset_id,cell_id=excluded.cell_id,created_at=excluded.created_at""",
            {"a": identifier, "d": data.dataset_id, "s": data.cell_id, "t": now()},
        )
        audit(
            c,
            user["id"],
            "explicit_replay_binding",
            "asset",
            identifier,
            data.model_dump(),
        )
    return {"ok": True, "provenance": "experimental_on_simulated_asset"}


@router.get("/assets/{identifier}")
def asset_detail(identifier: int, user=Depends(current_user)):
    with tx() as c:
        a = require(c, "assets", identifier)
        a["health"] = asset_health(c, a)
        a["binding"] = one(
            c, "SELECT * FROM bindings WHERE asset_id=:a", {"a": identifier}
        )
        a["aggregate"] = aggregate_health(c, a)
        a["history"] = rows(
            c,
            """SELECT p.*,s.ordinal,s.sample_key,m.name model_name FROM predictions p
            JOIN samples s ON s.id=p.sample_id JOIN models m ON m.id=p.model_id
            WHERE p.asset_id=:a ORDER BY p.id DESC LIMIT 200""",
            {"a": identifier},
        )
        a["events"] = rows(
            c,
            "SELECT * FROM health_events WHERE asset_id=:a ORDER BY id DESC LIMIT 50",
            {"a": identifier},
        )
        a["children"] = rows(
            c,
            "SELECT id,name,kind,code FROM assets WHERE parent_id=:a AND active=1",
            {"a": identifier},
        )
        return a


@router.post("/demo/seed")
def demo_seed(user=Depends(allow("admin", "dispatcher"))):
    with tx() as c:
        return seed_demo(c, user["id"])


@router.post("/demo/bind/{dataset_id}")
def bind_demo(
    dataset_id: int, user=Depends(allow("admin", "dispatcher", "researcher"))
):
    with tx() as c:
        return {"bound_slots": demo_bind(c, dataset_id, user["id"])}


@router.get("/users")
def get_users(user=Depends(allow("admin", "dispatcher"))):
    with tx() as c:
        return rows(
            c,
            "SELECT id,username,display_name,role,active,created_at,version FROM users ORDER BY id",
        )


@router.post("/users", status_code=201)
def add_user(data: S.UserCreate, user=Depends(allow("admin"))):
    with tx() as c:
        identifier = create_user(c, **data.model_dump())
        audit(c, user["id"], "user_create", "user", identifier, {"role": data.role})
        return {"id": identifier}


@router.put("/users/{identifier}")
def change_user(identifier: int, data: S.UserUpdate, user=Depends(allow("admin"))):
    with tx() as c:
        old = require(c, "users", identifier)
        if old["version"] != data.version:
            raise HTTPException(409, "用户版本冲突")
        if (
            old["role"] == "admin"
            and old["active"]
            and (data.role != "admin" or not data.active)
        ):
            if (
                one(c, "SELECT count(*) n FROM users WHERE active=1 AND role='admin'")[
                    "n"
                ]
                <= 1
            ):
                raise HTTPException(409, "不能移除最后一个管理员")
        if old["role"] == "technician" and (
            data.role != "technician" or not data.active
        ):
            if one(
                c,
                "SELECT id FROM orders WHERE assignee_id=:i AND status NOT IN ('CLOSED','CANCELLED')",
                {"i": identifier},
            ):
                raise HTTPException(409, "请先处理或转派该人员的活动工单")
        execute(
            c,
            "UPDATE users SET role=:r,active=:a,version=version+1 WHERE id=:i",
            {"r": data.role, "a": int(data.active), "i": identifier},
        )
        execute(c, "DELETE FROM sessions WHERE user_id=:i", {"i": identifier})
        audit(
            c,
            user["id"],
            "user_update",
            "user",
            identifier,
            {"role": data.role, "active": data.active},
        )
    return {"ok": True}


@router.post("/users/{identifier}/password")
def change_password(
    identifier: int, data: S.PasswordUpdate, user=Depends(current_user)
):
    if identifier != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "只能修改自己的密码")
    with tx() as c:
        target = require(c, "users", identifier)
        if identifier == user["id"] and (
            not data.current_password
            or not verify(data.current_password, target["password_hash"])
        ):
            raise HTTPException(403, "当前密码不正确")
        execute(
            c,
            "UPDATE users SET password_hash=:p,version=version+1 WHERE id=:i",
            {"p": password_hash(data.new_password), "i": identifier},
        )
        execute(c, "DELETE FROM sessions WHERE user_id=:i", {"i": identifier})
        audit(
            c,
            user["id"],
            "password_reset" if identifier != user["id"] else "password_change",
            "user",
            identifier,
        )
    return {"ok": True, "all_sessions_revoked": True}


@router.get("/notifications")
def notifications(user=Depends(current_user)):
    with tx() as c:
        return rows(
            c,
            "SELECT * FROM notifications WHERE user_id=:u ORDER BY id DESC LIMIT 100",
            {"u": user["id"]},
        )


@router.post("/notifications/{identifier}/read")
def read_notification(identifier: int, user=Depends(current_user)):
    with tx() as c:
        n = require(c, "notifications", identifier)
        if n["user_id"] != user["id"]:
            raise HTTPException(403, "不是当前用户的通知")
        execute(
            c,
            "UPDATE notifications SET read_at=:t WHERE id=:i",
            {"t": now(), "i": identifier},
        )
    return {"ok": True}


@router.get("/audit")
def audit_log(
    action: str = "",
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(allow("admin", "researcher", "dispatcher")),
):
    with tx() as c:
        params = {"q": f"%{action}%", "o": offset, "l": limit}
        return {
            "items": rows(
                c,
                """SELECT a.*,u.display_name actor FROM audit a LEFT JOIN users u ON u.id=a.actor_id
            WHERE a.action LIKE :q ORDER BY a.id DESC LIMIT :l OFFSET :o""",
                params,
            ),
            "total": one(
                c, "SELECT count(*) n FROM audit WHERE action LIKE :q", params
            )["n"],
        }

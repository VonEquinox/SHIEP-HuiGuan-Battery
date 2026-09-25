from __future__ import annotations
import hashlib
import io
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from . import schemas as S
from .config import RUNTIME
from .db import tx, rows, one, execute, insert, js, obj, now, audit, notify
from .security import current_user, allow
from .services import require, public, recommendations, demo_event

router = APIRouter(prefix="/api")


def order_access(order, user, write=False):
    if user["role"] == "technician" and order["assignee_id"] != user["id"]:
        raise HTTPException(403, "只能访问本人获派的工单")
    if write and user["role"] not in ("admin", "dispatcher", "technician"):
        raise HTTPException(403, "无工单操作权限")


@router.get("/policies")
def policies(user=Depends(current_user)):
    with tx() as c:
        return rows(c, "SELECT * FROM policies ORDER BY id DESC")


@router.post("/policies", status_code=201)
def create_policy(data: S.PolicyCreate, user=Depends(allow("admin", "researcher"))):
    with tx() as c:
        execute(c, "UPDATE policies SET active=0 WHERE active=1")
        identifier = insert(
            c,
            "policies",
            {
                **data.model_dump(),
                "active": 1,
                "created_at": now(),
                "created_by": user["id"],
            },
        )
        audit(
            c,
            user["id"],
            "policy_version_create",
            "policy",
            identifier,
            data.model_dump(),
        )
    return {
        "id": identifier,
        "scope": "simulation_maintenance_review_not_safety_control",
    }


@router.get("/health-events")
def events(user=Depends(current_user)):
    with tx() as c:
        return [
            public(e, ("evidence",))
            for e in rows(
                c,
                "SELECT e.*,a.name asset_name FROM health_events e JOIN assets a ON a.id=e.asset_id ORDER BY e.id DESC LIMIT 200",
            )
        ]


@router.post("/demo/events")
def demo_inject(data: S.DemoEvent, user=Depends(allow("admin", "dispatcher"))):
    with tx() as c:
        return {"alert_id": demo_event(c, data.asset_id, data.scenario, user["id"])}


@router.get("/alerts")
def alerts(status: str = "", user=Depends(current_user)):
    with tx() as c:
        return rows(
            c,
            """SELECT a.*,s.name asset_name,s.code asset_code,e.provenance,e.scenario_id,e.prediction_id,o.id order_id
        FROM alerts a JOIN assets s ON s.id=a.asset_id JOIN health_events e ON e.id=a.event_id
        LEFT JOIN orders o ON o.alert_id=a.id"""
            + (" WHERE a.status=:s" if status else "")
            + " ORDER BY a.id DESC LIMIT 300",
            {"s": status},
        )


@router.post("/alerts/{identifier}/transition")
def alert_transition(
    identifier: int, data: S.AlertAction, user=Depends(allow("admin", "dispatcher"))
):
    with tx() as c:
        a = require(c, "alerts", identifier)
        if a["version"] != data.version:
            raise HTTPException(409, "告警已改变，请刷新后再操作")
        transitions = {
            ("OPEN", "acknowledge"): "ACKNOWLEDGED",
            ("OPEN", "resolve"): "RESOLVED",
            ("ACKNOWLEDGED", "resolve"): "RESOLVED",
            ("RESOLVED", "reopen"): "OPEN",
        }
        target = transitions.get((a["status"], data.action))
        if not target:
            raise HTTPException(409, "不允许此告警状态转换")
        if data.action != "acknowledge" and len(data.note.strip()) < 3:
            raise HTTPException(422, "必须记录原因")
        if target == "OPEN" and one(
            c,
            "SELECT id FROM alerts WHERE dedup_key=:k AND status IN ('OPEN','ACKNOWLEDGED') AND id!=:i",
            {"k": a["dedup_key"], "i": identifier},
        ):
            raise HTTPException(409, "相同事件已有活动告警")
        execute(
            c,
            "UPDATE alerts SET status=:s,updated_at=:t,version=version+1 WHERE id=:i AND version=:v",
            {"s": target, "t": now(), "i": identifier, "v": data.version},
        )
        audit(
            c,
            user["id"],
            "alert_" + data.action,
            "alert",
            identifier,
            {"note": data.note},
        )
        return require(c, "alerts", identifier)


@router.post("/alerts/{identifier}/work-order", status_code=201)
def alert_to_order(identifier: int, user=Depends(allow("admin", "dispatcher"))):
    with tx() as c:
        a = require(c, "alerts", identifier)
        existing = one(c, "SELECT * FROM orders WHERE alert_id=:i", {"i": identifier})
        if existing:
            return existing
        if a["status"] == "RESOLVED":
            raise HTTPException(409, "已解除告警不能新建工单")
        asset = require(c, "assets", a["asset_id"])
        order = insert(
            c,
            "orders",
            {
                "alert_id": identifier,
                "asset_id": asset["id"],
                "title": asset["name"] + " · 健康复核",
                "status": "CREATED",
                "required_skill": "battery",
                "created_by": user["id"],
                "created_at": now(),
                "updated_at": now(),
            },
        )
        insert(
            c,
            "order_events",
            {
                "order_id": order,
                "from_status": None,
                "to_status": "CREATED",
                "actor_id": user["id"],
                "note": "由告警生成；不是物理设备控制命令",
                "created_at": now(),
            },
        )
        audit(c, user["id"], "order_create", "order", order, {"alert_id": identifier})
        return require(c, "orders", order)


@router.get("/orders")
def orders(status: str = "", user=Depends(current_user)):
    with tx() as c:
        predicates = []
        params = {}
        if user["role"] == "technician":
            predicates.append("o.assignee_id=:u")
            params["u"] = user["id"]
        if status:
            predicates.append("o.status=:s")
            params["s"] = status
        return rows(
            c,
            """SELECT o.*,a.name asset_name,a.code asset_code,u.display_name assignee_name
            FROM orders o JOIN assets a ON a.id=o.asset_id LEFT JOIN users u ON u.id=o.assignee_id"""
            + (" WHERE " + " AND ".join(predicates) if predicates else "")
            + " ORDER BY o.id DESC LIMIT 300",
            params,
        )


@router.get("/orders/{identifier}")
def order_detail(identifier: int, user=Depends(current_user)):
    with tx() as c:
        o = require(c, "orders", identifier)
        order_access(o, user)
        o["events"] = rows(
            c,
            """SELECT e.*,u.display_name actor FROM order_events e JOIN users u ON u.id=e.actor_id
            WHERE e.order_id=:i ORDER BY e.id""",
            {"i": identifier},
        )
        o["attachments"] = rows(
            c,
            "SELECT id,file_name,mime,size,sha256,created_at,created_by FROM attachments WHERE order_id=:i",
            {"i": identifier},
        )
        o["asset"] = require(c, "assets", o["asset_id"])
        o["alert"] = require(c, "alerts", o["alert_id"])
        o["source_event"] = public(
            require(c, "health_events", o["alert"]["event_id"]), ("evidence",)
        )
        o["recommendations"] = (
            recommendations(c, o) if user["role"] in ("admin", "dispatcher") else []
        )
        o["feedback"] = rows(
            c, "SELECT * FROM feedback WHERE order_id=:i ORDER BY id", {"i": identifier}
        )
        return o


@router.get("/orders/{identifier}/recommendations")
def recommend(identifier: int, user=Depends(allow("admin", "dispatcher"))):
    with tx() as c:
        return recommendations(c, require(c, "orders", identifier))


@router.post("/orders/{identifier}/transition")
def transition(
    identifier: int,
    data: S.Transition,
    user=Depends(allow("admin", "dispatcher", "technician")),
):
    with tx() as c:
        order = require(c, "orders", identifier)
        order_access(order, user, True)
        if order["version"] != data.version:
            raise HTTPException(409, "工单版本冲突，请重新加载")
        role = user["role"]
        action = data.action
        before = order["status"]
        target = None
        values = {"id": identifier, "version": data.version, "t": now()}
        changes = []
        if action == "assign":
            if role not in ("admin", "dispatcher"):
                raise HTTPException(403, "仅调度员可派单")
            if before not in ("CREATED", "ASSIGNED"):
                raise HTTPException(409, "当前状态不允许派单")
            eligible = {
                p["user_id"] for p in recommendations(c, order) if p["eligible"]
            }
            if data.assignee_id not in eligible:
                raise HTTPException(422, "人员未值班、技能不匹配或工作量已满")
            target = "ASSIGNED"
            changes.append("assignee_id=:assignee")
            values["assignee"] = data.assignee_id
        elif action in ("accept", "start", "resolve", "reject"):
            if order["assignee_id"] != user["id"] or role != "technician":
                raise HTTPException(403, "必须由获派维修人员本人操作")
            mapping = {
                ("ASSIGNED", "accept"): "ACCEPTED",
                ("ACCEPTED", "start"): "IN_PROGRESS",
                ("IN_PROGRESS", "resolve"): "RESOLVED",
                ("ASSIGNED", "reject"): "CREATED",
                ("ACCEPTED", "reject"): "CREATED",
            }
            target = mapping.get((before, action))
            if action in ("resolve", "reject") and len(data.note.strip()) < 5:
                raise HTTPException(422, "请填写至少5字处理结果或退回原因")
            if action == "resolve":
                start = one(
                    c,
                    "SELECT created_at FROM order_events WHERE order_id=:i AND to_status='IN_PROGRESS' ORDER BY id DESC LIMIT 1",
                    {"i": identifier},
                )
                if not start or not one(
                    c,
                    "SELECT id FROM attachments WHERE order_id=:i AND created_at>=:t AND created_by=:u",
                    {"i": identifier, "t": start["created_at"], "u": user["id"]},
                ):
                    raise HTTPException(
                        422,
                        "提交前须由本人上传本次开始处理之后的证据，不能沿用旧处置附件",
                    )
                changes += [
                    "resolution=:note",
                    "resolved_by=:actor",
                    "verified_by=NULL",
                ]
                values.update(note=data.note, actor=user["id"])
            if action == "reject":
                changes.append("assignee_id=NULL")
        elif action in ("verify", "close", "reopen", "cancel"):
            if role not in ("admin", "dispatcher"):
                raise HTTPException(403, "仅调度或管理员可验收、关闭、重开、取消")
            if action == "verify":
                if order["resolved_by"] == user["id"]:
                    raise HTTPException(403, "不能验收自己提交的处理结果")
                if before == "RESOLVED":
                    target = "VERIFIED"
                    changes.append("verified_by=:verifier")
                    values["verifier"] = user["id"]
            elif action == "close" and before == "VERIFIED":
                target = "CLOSED"
            elif action == "reopen" and before in ("RESOLVED", "VERIFIED", "CLOSED"):
                target = "CREATED"
                changes += [
                    "assignee_id=NULL",
                    "resolution=NULL",
                    "resolved_by=NULL",
                    "verified_by=NULL",
                ]
            elif action == "cancel" and before not in ("CLOSED", "CANCELLED"):
                target = "CANCELLED"
            if len(data.note.strip()) < 3:
                raise HTTPException(422, "请填写操作记录")
        if target is None:
            raise HTTPException(409, "不允许此工单状态转换")
        changes += ["status=:status", "updated_at=:t", "version=version+1"]
        values["status"] = target
        changed = execute(
            c,
            "UPDATE orders SET "
            + ",".join(changes)
            + " WHERE id=:id AND version=:version",
            values,
        )
        if changed.rowcount != 1:
            raise HTTPException(409, "并发修改冲突")
        insert(
            c,
            "order_events",
            {
                "order_id": identifier,
                "from_status": before,
                "to_status": target,
                "actor_id": user["id"],
                "note": data.note.strip() or action,
                "created_at": now(),
            },
        )
        audit(
            c,
            user["id"],
            "order_" + action,
            "order",
            identifier,
            {"from": before, "to": target, "note": data.note},
        )
        affected = {order["created_by"], user["id"]}
        if data.assignee_id:
            affected.add(data.assignee_id)
        if order["assignee_id"]:
            affected.add(order["assignee_id"])
        for uid in affected:
            notify(
                c,
                uid,
                f"工单 #{identifier} · {target}",
                data.note or "状态已更新",
                f"/operations?order={identifier}",
            )
        return require(c, "orders", identifier)


@router.post("/orders/{identifier}/attachments", status_code=201)
async def upload_attachment(
    identifier: int,
    file: UploadFile = File(...),
    user=Depends(allow("admin", "dispatcher", "technician")),
):
    with tx() as c:
        o = require(c, "orders", identifier)
        order_access(o, user, True)
        if o["status"] in ("CLOSED", "CANCELLED"):
            raise HTTPException(409, "已结束工单禁止修改证据")
    contents = await file.read(5 * 1024 * 1024 + 1)
    if not contents or len(contents) > 5 * 1024 * 1024:
        raise HTTPException(413, "证据文件须为1字节至5MiB")
    name = file.filename or ""
    if len(name) > 160 or "/" in name or "\\" in name or "\x00" in name:
        raise HTTPException(422, "文件名不合法")
    suffix = Path(name).suffix.lower()
    mime = None
    if suffix == ".txt":
        try:
            text = contents.decode("utf-8")
            if "\x00" in text:
                raise ValueError()
        except (UnicodeError, ValueError):
            raise HTTPException(415, "文本必须为UTF-8且不含二进制内容")
        mime = "text/plain"
    elif suffix in (".png", ".jpg", ".jpeg"):
        try:
            with Image.open(io.BytesIO(contents)) as image:
                if image.width * image.height > 16000000 or image.format not in (
                    "PNG",
                    "JPEG",
                ):
                    raise ValueError()
                if (suffix == ".png") != (image.format == "PNG"):
                    raise ValueError()
                image.verify()
            mime = "image/png" if suffix == ".png" else "image/jpeg"
        except (
            UnidentifiedImageError,
            ValueError,
            OSError,
            Image.DecompressionBombError,
        ):
            raise HTTPException(415, "图片类型、内容或尺寸不合法")
    else:
        raise HTTPException(415, "证据仅支持PNG、JPEG、UTF-8文本；不接受可执行内容")
    storage = uuid.uuid4().hex + suffix
    path = RUNTIME / "attachments" / storage
    try:
        path.write_bytes(contents)
        path.chmod(0o600)
        with tx() as c:
            o = require(c, "orders", identifier)
            order_access(o, user, True)
            if o["status"] in ("CLOSED", "CANCELLED"):
                raise HTTPException(409, "工单状态已改变")
            count = one(
                c,
                "SELECT count(*) n FROM attachments WHERE order_id=:i",
                {"i": identifier},
            )["n"]
            if count >= 20:
                raise HTTPException(413, "单个工单最多20个附件")
            aid = insert(
                c,
                "attachments",
                {
                    "order_id": identifier,
                    "file_name": name,
                    "storage_name": storage,
                    "mime": mime,
                    "size": len(contents),
                    "sha256": hashlib.sha256(contents).hexdigest(),
                    "created_by": user["id"],
                    "created_at": now(),
                },
            )
            audit(
                c,
                user["id"],
                "evidence_upload",
                "order",
                identifier,
                {"attachment_id": aid},
            )
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {"id": aid}


@router.get("/attachments/{identifier}")
def download_attachment(
    identifier: int, user=Depends(allow("admin", "dispatcher", "technician"))
):
    with tx() as c:
        a = require(c, "attachments", identifier)
        o = require(c, "orders", a["order_id"])
        order_access(o, user)
    path = RUNTIME / "attachments" / a["storage_name"]
    if (
        path.parent.resolve() != (RUNTIME / "attachments").resolve()
        or not path.is_file()
    ):
        raise HTTPException(404, "附件不可用")
    return FileResponse(
        path,
        filename=a["file_name"],
        media_type=a["mime"],
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/personnel")
def people(user=Depends(current_user)):
    with tx() as c:
        result = rows(
            c,
            "SELECT p.*,u.display_name,u.username,u.active FROM personnel p JOIN users u ON u.id=p.user_id ORDER BY p.id",
        )
        for p in result:
            p["skills"] = obj(p["skills"], [])
            p["workload"] = one(
                c,
                "SELECT count(*) n FROM orders WHERE assignee_id=:i AND status NOT IN ('CLOSED','CANCELLED')",
                {"i": p["user_id"]},
            )["n"]
        return result


@router.post("/personnel")
def save_person(data: S.PersonnelUpdate, user=Depends(allow("admin", "dispatcher"))):
    if not data.skills or any(
        s not in ("battery", "electrical", "sensor", "inspection") for s in data.skills
    ):
        raise HTTPException(422, "技能标签无效")
    with tx() as c:
        u = require(c, "users", data.user_id)
        if u["role"] != "technician" or not u["active"]:
            raise HTTPException(422, "必须绑定有效维修人员账号")
        execute(
            c,
            """INSERT INTO personnel(user_id,skills,on_call,latitude,longitude,max_workload) VALUES(:u,:s,:o,:lat,:lon,:w)
            ON CONFLICT(user_id) DO UPDATE SET skills=:s,on_call=:o,latitude=:lat,longitude=:lon,max_workload=:w,version=version+1""",
            {
                "u": data.user_id,
                "s": js(sorted(set(data.skills))),
                "o": int(data.on_call),
                "lat": data.latitude,
                "lon": data.longitude,
                "w": data.max_workload,
            },
        )
        audit(
            c,
            user["id"],
            "personnel_update",
            "user",
            data.user_id,
            {"skills": data.skills, "on_call": data.on_call},
        )
    return {"ok": True}


@router.post("/feedback", status_code=201)
def feedback(
    data: S.FeedbackCreate, user=Depends(allow("admin", "researcher", "technician"))
):
    try:
        measured = datetime.fromisoformat(data.measured_at.replace("Z", "+00:00"))
        if measured.tzinfo is None or measured > datetime.now(timezone.utc) + timedelta(
            minutes=5
        ):
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "测量时间必须含时区，且不能在未来")
    with tx() as c:
        p = require(c, "predictions", data.prediction_id)
        if data.order_id:
            o = require(c, "orders", data.order_id)
            order_access(o, user)
            if o["asset_id"] != p["asset_id"]:
                raise HTTPException(422, "工单资产与预测资产不一致")
            event = one(
                c,
                "SELECT e.installation_id FROM alerts a JOIN health_events e ON e.id=a.event_id WHERE a.id=:a",
                {"a": o["alert_id"]},
            )
            if event and event["installation_id"] != p["installation_id"]:
                raise HTTPException(422, "预测与工单对应不同安装批次，不能混合反馈")
        elif user["role"] == "technician":
            raise HTTPException(403, "维修人员反馈必须关联本人工单")
        identifier = insert(
            c,
            "feedback",
            {
                **data.model_dump(),
                "unit": "SOH_ratio",
                "created_by": user["id"],
                "created_at": now(),
            },
        )
        audit(
            c,
            user["id"],
            "feedback_append",
            "prediction",
            p["id"],
            {
                "feedback_id": identifier,
                "provenance": data.provenance,
                "training_admission": False,
            },
        )
        return {
            "id": identifier,
            "training_admission": False,
            "original_prediction_unchanged": True,
        }


@router.get("/feedback")
def feedback_list(user=Depends(current_user)):
    with tx() as c:
        where = " WHERE f.created_by=:u" if user["role"] == "technician" else ""
        return rows(
            c,
            "SELECT f.*,u.display_name actor FROM feedback f JOIN users u ON u.id=f.created_by"
            + where
            + " ORDER BY f.id DESC LIMIT 200",
            {"u": user["id"]},
        )

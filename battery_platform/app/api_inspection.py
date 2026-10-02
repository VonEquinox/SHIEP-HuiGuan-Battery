from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .contracts import v2 as S
from .db import audit, execute, insert, js, now, obj, one, rows, tx
from .services import public, require
from .api_ops import order_access
from .api_v2 import authenticated, roles, response, fingerprint, timestamp, replay, remember, session_access, test_catalog, sign_qr, verify_qr, save_evidence_version
from .api_agent import create_run, REPORT_JSON, PROPOSAL_JSON

router = APIRouter(prefix="/api/v2")
OBSERVATION_JSON = ("measurements", "observed_symptoms", "performed_actions", "confirmed_hypotheses", "excluded_hypotheses", "unresolved_items", "attachment_ids", "candidate_facts", "assertion_targets", "comparison_context")


def inspection_access(c, identifier, user, write=False):
    order = require(c, "orders", identifier)
    order_access(order, user, write)
    if write and order["status"] in ("CREATED", "ASSIGNED", "RESOLVED", "VERIFIED", "CLOSED", "CANCELLED"):
        raise HTTPException(409, "检查证据仅可在接单或执行期间提交")
    proposal = one(c, "SELECT * FROM work_proposals WHERE order_id=:o AND status='APPROVED'", {"o": identifier})
    if not proposal:
        raise HTTPException(409, "此工单没有 V2 已批准检查集合，沿用原工单流程")
    assets = rows(c, """SELECT oa.*,a.name,a.code,a.kind,a.installation_id current_installation_id,a.active
                 FROM order_assets oa JOIN assets a ON a.id=oa.asset_id WHERE oa.order_id=:o ORDER BY oa.asset_id""", {"o": identifier})
    if write and any(not asset["active"] or asset["installation_id"] != asset["current_installation_id"] for asset in assets):
        raise HTTPException(409, "工单安装身份已变更，请重新检查任务范围")
    return order, proposal, assets


@router.get("/orders/{identifier}/inspection")
def get_inspection(identifier: int, request: Request, user=Depends(authenticated)):
    with tx() as c:
        order, proposal, assets = inspection_access(c, identifier, user)
        rounds = [public(v, ("authorized_tests", "required_tests")) for v in rows(c, "SELECT * FROM inspection_rounds WHERE order_id=:o ORDER BY round", {"o": identifier})]
        catalog = test_catalog()
        allowed_tests = [{**catalog[t], "authorized": True} for t in obj(proposal["allowed_tests"], [])]
        current_round = next((v["round"] for v in rounds if v["status"] == "OPEN"), None)
        observations = [public(v, OBSERVATION_JSON) for v in rows(c, "SELECT * FROM inspection_observations WHERE order_id=:o ORDER BY id", {"o": identifier})]
        reports = [public(v, REPORT_JSON) for v in rows(c, "SELECT * FROM agent_reports WHERE session_id=:s ORDER BY id", {"s": proposal["session_id"]})]
        return response(request, order=order, proposal=public(proposal, PROPOSAL_JSON), assets=assets, installation_id=assets[0]["installation_id"] if len(assets) == 1 else None,
                        current_round=current_round, max_rounds=proposal["max_rounds"], allowed_tests=allowed_tests, rounds=rounds,
                        observations=observations, reports=reports, attachments=rows(c, "SELECT id,file_name,mime,size,created_at,created_by FROM attachments WHERE order_id=:o ORDER BY id", {"o": identifier}),
                        independent_acceptance_required=True)


def qualification_check(c, user, test):
    if user["role"] != "technician":
        return
    person = one(c, "SELECT skills FROM personnel WHERE user_id=:u", {"u": user["id"]})
    skills = set(obj(person["skills"], [])) if person else set()
    required = set(test.get("required_qualifications", [test.get("required_skill", "battery")]))
    if not required.issubset(skills):
        raise HTTPException(403, "当前技术员缺少此项检查所需资格")


@router.post("/orders/{identifier}/observations", status_code=201)
def add_observation(identifier: int, data: S.ObservationCreate, request: Request, user=Depends(roles("admin", "dispatcher", "technician"))):
    from .jobs import enqueue
    # An absent optional comparison context must preserve pre-migration retry
    # hashes; adding grouping metadata is an explicit new submission instead.
    body = data.model_dump(exclude={"comparison_context"} if data.comparison_context is None else set())
    key = request.headers.get("idempotency-key") or data.client_submission_id
    with tx() as c:
        previous = replay(c, user, f"observation:{identifier}", key, body)
        if previous:
            return response(request, **previous)
        # The submission UUID also remains globally unique for this author/order.
        old = one(c, "SELECT * FROM inspection_observations WHERE order_id=:o AND author_id=:u AND client_submission_id=:s", {"o": identifier, "u": user["id"], "s": data.client_submission_id})
        if old:
            if old["request_hash"] != fingerprint(body):
                raise HTTPException(409, "重复提交 UUID 的内容不同，请合并草稿")
            return response(request, observation_id=old["id"], extraction_status=old["extraction_status"], replayed=True)
        order, proposal, assets = inspection_access(c, identifier, user, True)
        if order["version"] != data.order_version:
            raise HTTPException(409, "工单版本已变化，请刷新并合并草稿")
        round_row = one(c, "SELECT * FROM inspection_rounds WHERE order_id=:o AND round=:r", {"o": identifier, "r": data.round})
        if not round_row or round_row["status"] != "OPEN" or data.round > proposal["max_rounds"]:
            raise HTTPException(409, "本轮未授权、已提交或超出轮次预算")
        if data.test_id not in obj(round_row["authorized_tests"], []):
            raise HTTPException(403, "检查不在本工单已授权测试集合内，需要新增提案")
        matching = [asset for asset in assets if asset["installation_id"] == data.installation_id and (data.asset_id is None or asset["asset_id"] == data.asset_id)]
        if len(matching) != 1:
            raise HTTPException(403, "测量安装身份或资产不属于此工单")
        test = test_catalog()[data.test_id]
        qualification_check(c, user, test)
        if test.get("needs_new_authorization"):
            raise HTTPException(403, "此项检查需要单独授权，不可由原测试集合扩大")
        measured = timestamp(data.measured_at)
        if measured < order["created_at"]:
            raise HTTPException(422, "现场测量时间早于工单授权；历史记录应作为来源证据登记")
        if data.result == "observed" and not (data.measurements or data.observed_symptoms or data.free_text.strip()):
            raise HTTPException(422, "缺少本次观察内容；未测得请记录 inconclusive/failed/refused")
        permitted_units = set(test.get("units", []))
        for measurement in data.measurements:
            if permitted_units and measurement.unit not in permitted_units:
                raise HTTPException(422, "测量单位与授权检查模板不兼容")
        if len(set(data.attachment_ids)) != len(data.attachment_ids):
            raise HTTPException(422, "附件不能重复")
        for attachment_id in data.attachment_ids:
            attachment = require(c, "attachments", attachment_id)
            if attachment["order_id"] != identifier:
                raise HTTPException(403, "附件不属于当前工单")
        values = {"order_id": identifier, "session_id": proposal["session_id"], "asset_id": matching[0]["asset_id"], "installation_id": data.installation_id,
                  "round": data.round, "test_id": data.test_id, "measured_at": measured, "available_at": now(), "instrument_id": data.instrument_id,
                  "calibration_status": data.calibration_status, "free_text": data.free_text, "result": data.result,
                  "candidate_facts": "[]", "extraction_status": "queued", "author_id": user["id"], "provenance": data.provenance,
                  "client_submission_id": data.client_submission_id, "request_hash": fingerprint(body)}
        for field in OBSERVATION_JSON:
            if field != "candidate_facts":
                values[field] = js(body.get(field))
        if data.comparison_context is not None:
            person = one(c, "SELECT * FROM personnel WHERE user_id=:u", {"u": user["id"]})
            minimum = sorted(set(test.get("required_qualifications", [])))
            qualified = bool(person) and set(minimum).issubset(obj(person["skills"], []))
            values["comparison_context"] = js({**body["comparison_context"], "declaration_trust": "reported",
                "qualification_evidence": {"author_id": user["id"], "verified": qualified, "required_qualifications": minimum,
                                           "personnel_id": person["id"] if person else None, "personnel_version": person["version"] if person else None},
                "authorization_ref": {"order_id": identifier, "proposal_id": proposal["id"], "proposal_version": proposal["version"],
                                      "round_id": round_row["id"], "test_id": data.test_id}})
        observation_id = insert(c, "inspection_observations", values)
        insert(c, "inspection_observation_versions", {"observation_id": observation_id, "version": 1, "content": js(values), "author_id": user["id"], "note": "original submission", "created_at": now()})
        job_id = enqueue(c, "feedback_extract", {"observation_id": observation_id, "observation_version": 1}, user, "extract-observation-" + fingerprint([identifier, data.client_submission_id]))
        run = create_run(c, {"asset_id": proposal_asset(c, proposal), "installation_id": require(c, "agent_reports", proposal["report_id"])["installation_id"],
                     "visible_cutoff": now(), "session_id": proposal["session_id"], "round": data.round}, user, "observation-reassess-" + str(observation_id))
        audit(c, user["id"], "inspection_observation_create", "inspection_observation", observation_id, {"author_from_session": True, "test_id": data.test_id, "result": data.result})
        result = {"observation_id": observation_id, "extraction_status": "queued", "extraction_job_id": job_id, "reassessment_job_id": run["job_id"], "job_id": run["job_id"], "run_id": run["run_id"], "session_id": proposal["session_id"]}
        return response(request, **remember(c, user, f"observation:{identifier}", key, body, result))


def proposal_asset(c, proposal):
    return require(c, "agent_reports", proposal["report_id"])["asset_id"]


@router.post("/orders/{identifier}/rounds/{round_number}/submit")
def submit_round(identifier: int, round_number: int, data: S.RoundSubmit, request: Request, user=Depends(roles("admin", "dispatcher", "technician"))):
    body = data.model_dump()
    key = request.headers.get("idempotency-key") or data.client_submission_id
    with tx() as c:
        previous = replay(c, user, f"round-submit:{identifier}:{round_number}", key, body)
        if previous:
            return response(request, **previous)
        order, proposal, assets = inspection_access(c, identifier, user, True)
        if order["version"] != data.order_version:
            raise HTTPException(409, "工单版本冲突，请刷新")
        if data.installation_id not in {asset["installation_id"] for asset in assets}:
            raise HTTPException(403, "安装身份不属于工单")
        round_row = one(c, "SELECT * FROM inspection_rounds WHERE order_id=:o AND round=:r", {"o": identifier, "r": round_number})
        if not round_row or round_row["status"] != "OPEN":
            raise HTTPException(409, "本轮不可重复提交或未获授权")
        observations = rows(c, "SELECT * FROM inspection_observations WHERE order_id=:o AND round=:r", {"o": identifier, "r": round_number})
        missing = []
        required = set(obj(round_row["required_tests"], []))
        completed = {v["test_id"] for v in observations}
        if not observations:
            missing.append("observations")
        for test_id in sorted(required - completed):
            missing.append("test:" + test_id)
        catalog = test_catalog()
        for observation in observations:
            if observation["result"] == "observed" and obj(observation["measurements"], []):
                if observation["instrument_id"] == "not_recorded":
                    missing.append(f"observation:{observation['id']}.instrument_id")
                if observation["calibration_status"] == "expired":
                    missing.append(f"observation:{observation['id']}.valid_calibration")
            if catalog[observation["test_id"]].get("requires_attachment") and not obj(observation["attachment_ids"], []):
                missing.append(f"observation:{observation['id']}.attachment_ids")
        if missing:
            raise HTTPException(422, {"code": "MISSING_ROUND_FIELDS", "message": "本轮信息不完整", "missing_fields": missing, "retryable": False})
        execute(c, "UPDATE inspection_rounds SET status='SUBMITTED',submitted_at=:t,submitted_by=:u,version=version+1 WHERE id=:i", {"t": now(), "u": user["id"], "i": round_row["id"]})
        # Deliberately preserve the V1 order state and its independent verification.
        execute(c, "UPDATE orders SET version=version+1,updated_at=:t WHERE id=:i", {"t": now(), "i": identifier})
        run = create_run(c, {"asset_id": proposal_asset(c, proposal), "installation_id": require(c, "agent_reports", proposal["report_id"])["installation_id"],
                           "visible_cutoff": now(), "session_id": proposal["session_id"], "round": round_number}, user, f"round-submit-reassess-{identifier}-{round_number}")
        audit(c, user["id"], "inspection_round_submit", "inspection_round", round_row["id"], {"order_id": identifier, "not_final_acceptance": True})
        result = {"round_id": round_row["id"], "round": round_number, "status": "SUBMITTED", "order_version": order["version"] + 1, **run}
        return response(request, **remember(c, user, f"round-submit:{identifier}:{round_number}", key, body, result))


@router.post("/observations/{identifier}/facts")
def correct_facts(identifier: int, data: S.FactsCorrection, request: Request, user=Depends(roles("admin", "dispatcher", "technician"))):
    from .jobs import enqueue
    with tx() as c:
        observation = require(c, "inspection_observations", identifier)
        order, proposal, assets = inspection_access(c, observation["order_id"], user, True)
        if user["role"] == "technician" and observation["author_id"] != user["id"]:
            raise HTTPException(403, "技术员只能修正本人提交的结构化抽取")
        if observation["version"] != data.version:
            raise HTTPException(409, "观察已更新，请合并版本")
        for fact in data.candidate_facts:
            if not set(fact).issubset({"fact_id", "claim", "span", "source_text", "trust", "kind", "measurement", "author_id", "extraction_model", "source_field", "source_index"}) or not isinstance(fact.get("claim"), str) or not 1 <= len(fact["claim"]) <= 2000:
                raise HTTPException(422, "候选事实字段或长度无效")
            span = fact.get("span")
            if span is not None:
                start, end = span.get("start"), span.get("end")
                if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(observation["free_text"]):
                    raise HTTPException(422, "原文位置无效")
                if fact.get("source_text") != observation["free_text"][start:end]:
                    raise HTTPException(422, "候选事实原文不匹配")
            elif fact.get("measurement") not in obj(observation["measurements"], []):
                field, index = fact.get("source_field"), fact.get("source_index")
                values = obj(observation.get(field), []) if field in {"excluded_hypotheses", "unresolved_items", "confirmed_hypotheses"} else []
                if type(index) is not int or not 0 <= index < len(values):
                    raise HTTPException(422, "候选事实必须关联原文位置、本次已提交测量或结构化断言")
            if fact.get("trust", "reported") not in ("reported", "measurement_supported", "contradicted"):
                raise HTTPException(403, "独立核实状态由服务端验收决定")
            if fact.get("trust") == "measurement_supported" and (fact.get("measurement") not in obj(observation["measurements"], []) or observation["calibration_status"] != "calibrated" or observation["result"] != "observed"):
                raise HTTPException(422, "测量支持状态需要本次有效且可追溯的测量")
            fact["author_id"] = str(user["id"])
            fact["extraction_model"] = "human-correction"
        execute(c, "UPDATE inspection_observations SET candidate_facts=:f,extraction_status='corrected',version=version+1 WHERE id=:i", {"f": js(data.candidate_facts), "i": identifier})
        updated = public(require(c, "inspection_observations", identifier), OBSERVATION_JSON)
        insert(c, "inspection_observation_versions", {"observation_id": identifier, "version": data.version + 1, "content": js(updated), "author_id": user["id"], "note": data.note, "created_at": now()})
        job_id = enqueue(c, "feedback_extract", {"observation_id": identifier, "observation_version": data.version + 1, "preserve_corrected_facts": True}, user, f"extract-correction-{identifier}-{data.version + 1}")
        audit(c, user["id"], "inspection_facts_correct", "inspection_observation", identifier, {"raw_text_preserved": True, "version": data.version + 1})
        return response(request, observation=updated, job_id=job_id)


@router.post("/diagnostic-sessions/{identifier}/feedback", status_code=201)
def diagnostic_feedback(identifier: int, data: S.DiagnosticFeedback, request: Request, user=Depends(roles("admin", "researcher", "dispatcher", "technician"))):
    from .jobs import enqueue
    body = data.model_dump()
    key = request.headers.get("idempotency-key") or data.client_submission_id
    with tx() as c:
        previous = replay(c, user, f"diagnostic-feedback:{identifier}", key, body)
        if previous:
            return response(request, **previous)
        session_access(c, identifier, user)
        report = require(c, "agent_reports", data.report_id)
        if report["session_id"] != identifier:
            raise HTTPException(403, "反馈报告不属于当前诊断")
        if data.order_id:
            order, proposal, _ = inspection_access(c, data.order_id, user)
            if proposal["session_id"] != identifier:
                raise HTTPException(403, "工单不属于当前诊断")
        elif user["role"] == "technician":
            raise HTTPException(403, "现场反馈必须关联本人获派工单")
        targets = set(data.assertion_targets)
        report_body = obj(report["report"])
        valid_targets = {f"r{report['report_version']}.{field}[{index}]" for field in ("facts", "hypotheses") for index in range(len(report_body.get(field, [])))}
        if not targets.issubset(valid_targets):
            raise HTTPException(422, "断言目标不属于所选报告版本")
        old = one(c, "SELECT * FROM diagnostic_feedback WHERE author_id=:u AND session_id=:s AND client_submission_id=:k", {"u": user["id"], "s": identifier, "k": data.client_submission_id})
        if old:
            if old["request_hash"] != fingerprint(body):
                raise HTTPException(409, "重复反馈 UUID 内容冲突")
            return response(request, feedback_id=old["id"], extraction_status=old["extraction_status"], replayed=True)
        values = {"session_id": identifier, "report_id": data.report_id, "order_id": data.order_id, "free_text": data.free_text,
                  "provenance": data.provenance, "candidate_facts": "[]", "extraction_status": "queued", "author_id": user["id"], "available_at": now(),
                  "client_submission_id": data.client_submission_id, "request_hash": fingerprint(body)}
        for field in ("assertion_targets", "confirmed_hypotheses", "excluded_hypotheses", "unresolved_items"):
            values[field] = js(body[field])
        feedback_id = insert(c, "diagnostic_feedback", values)
        save_evidence_version(c, "diagnostic_feedback", feedback_id, user["id"], "original feedback submission")
        job_id = enqueue(c, "feedback_extract", {"feedback_id": feedback_id, "feedback_version": 1}, user, f"extract-feedback-{feedback_id}")
        audit(c, user["id"], "diagnostic_feedback_create", "diagnostic_feedback", feedback_id, {"assertion_targets": data.assertion_targets})
        result = {"feedback_id": feedback_id, "extraction_status": "queued", "extraction_job_id": job_id, "job_id": job_id}
        return response(request, **remember(c, user, f"diagnostic-feedback:{identifier}", key, body, result))


@router.get("/orders/{identifier}/qr")
def order_qr(identifier: int, request: Request, asset_id: int | None = None, user=Depends(roles("admin", "dispatcher"))):
    with tx() as c:
        order, proposal, assets = inspection_access(c, identifier, user)
        selected = [asset for asset in assets if asset_id is None or asset["asset_id"] == asset_id]
        if len(selected) != 1:
            raise HTTPException(422, "群组工单须指定扫码资产")
        asset = selected[0]
        if asset["installation_id"] != asset["current_installation_id"]:
            raise HTTPException(409, "安装身份已经变化")
        payload = {"order_id": identifier, "asset_id": asset["asset_id"], "installation_id": asset["installation_id"], "expires_at": __import__("time").time() + 900}
        return response(request, **payload, token=sign_qr(payload))


@router.post("/orders/{identifier}/qr/verify")
def qr_verify(identifier: int, data: S.QRVerify, request: Request, user=Depends(roles("admin", "dispatcher", "technician"))):
    payload = verify_qr(data.token)
    with tx() as c:
        order, proposal, assets = inspection_access(c, identifier, user)
        if payload.get("order_id") != identifier or not any(asset["asset_id"] == payload.get("asset_id") and asset["installation_id"] == payload.get("installation_id") and asset["installation_id"] == asset["current_installation_id"] for asset in assets):
            raise HTTPException(403, "二维码工单、资产或当前安装身份不匹配")
        audit(c, user["id"], "inspection_qr_verify", "order", identifier, {"asset_id": payload["asset_id"]})
        return response(request, verified=True, **payload)

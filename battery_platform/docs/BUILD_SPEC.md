# 慧管电池 / Greenfield v1 acceptance contract

## Product and deliverable

An independent, runnable Chinese-language battery-health and maintenance web
application: real experimental model/data management, plus explicitly simulated
industrial assets and people with a REAL server-persisted workflow. This is not
a BMS/EMS control system, and must never issue physical shutdown/replacement
commands. Health models are research candidates, not certified safety systems.
Do not spend this task improving model architecture or looking at legacy code.

User-authorized modules: dashboard; site/cabinet/module/cell assets and fixed
locations; datasets and quality; models, training, evaluation, inference and
lineage; health assessments/events; alerts and deduplication; personnel and
explainable assignment; work-order lifecycle, evidence and verification; true
value feedback; users/roles; notifications and audit; deployment and tests.

## Architecture decision

Modular FastAPI backend, Python 3.12, SQLAlchemy 2.x and SQLite WAL for the
single-machine delivery. Use explicit transactions, foreign keys and version
checks. SQLite is not advertised as a horizontally scaled industrial database.
React + TypeScript + Vite frontend, Chinese UI, restrained polished engineering
console, responsive desktop/mobile. Seven top-level workspaces: 总览, 资产,
数据, 模型, 健康, 告警与工单, 系统. Personnel can be a tab in the last two.
Do not make a generic giant JSON editor or leave buttons as placeholders.

Persist jobs in DB. Heavy ML executes out of the request process using a bounded
single-compute worker/subprocess, with cancellation/timeout/error logs and
restart reconciliation. Do not use fake timers for progress. Prefer a simple
local worker over Redis/Celery infrastructure for this delivery. Package the
frontend as same-origin static assets for a one-command local release.

Isolated API environment lives here. ML subprocess uses the existing
`model_lab/.venv/bin/python`, without installing into that environment, imports
new bridge code here and existing frozen inference modules read-only. Model
assets remain in their original locations. ML unavailable => explicit failed
or unavailable status, never silently replace hybrid with a fast branch.

## Real source integration

Existing verified feature view:
`model_lab/reports/round2/cv_physical/view_bundle.npz` has 2404 x 71 current /
reference arrays, log_window_ratio, soh, cell, protocol, holdout. Import only
the 2058 non-holdout rows and 21 development cells. Immutable source-row index
is a sample identity, NOT a guessed physical cycle number. Recover cycle
identity only if the raw bundle metadata explicitly maps it. Do not expose or
score protected suffix-5 cells. Store hashes, dataset/schema version and units.

Frozen hybrid:
`model_lab/reports/round3/champion_hybrid_v2_streaming/manifest.json`;
`model_lab/modeling/frozen_hybrid_streaming.py:FrozenStreamingHybrid`;
method `predict_components(current, reference, log_window_ratio, progress=...)`.
Input shape N x 71; output soh, extra_trees_soh, tabicl_soh. Use actual frozen
weights and full 2058-row context. MPS allocation watermarks remain 0.7/0.5.
Frozen ExtraTrees branch is a SECOND, explicitly named selectable fast model:
`model_lab/modeling/frozen_et.py:load_champion,predict_soh,outside_training_range`.
Its joblib is in the same frozen package. Verify hashes before any deserialization.
Default inference can use fast ET only when the UI explicitly selects it.

Register existing nested and TabICL development evaluation reports as historical
development evidence, not new platform test scores or SOTA. Frozen weights were
trained on development cells: prediction on them is in-sample execution/replay,
NOT independent validation. No unlabeled "accuracy" or RUL. Show the 3.7-4.1V
partial-CC observation and initial reference requirement, schema and applicable
population. Inadequate inputs return insufficient_data/incompatible_model.

## Functional acceptance

1. Authentication: first-run bootstrap creates a user via local CLI (no embedded
   default password/backdoor). Salted password hash; opaque expiring server-side
   session, HttpOnly SameSite cookie; Origin/CSRF protection for mutations.
   Roles admin, researcher, dispatcher, technician, viewer enforced at endpoints.
   Technician may update ONLY assigned orders; self-verification is forbidden.
   Login failure/rate limit and logout/session invalidation are tested.
2. Dashboard: counts/charts derived from DB; explicit experimental/simulated
   badges, pending jobs and invalid/stale/unknown health are visible. Clicking
   indicators navigates to filtered underlying objects; no random chart values.
3. Assets: CRUD hierarchy site > cabinet > module > cell, validation against
   cycles/invalid parents, fixed coordinates, room/rack location and installation
   identity. Asset health summaries include coverage and worst-cell evidence,
   never equate mean cell SOH with a measured cabinet SOH. Include an offline
   location view with coordinates and honest schematic/geographic labels, no
   paid map service required. Persisted DEMO bindings explicitly associate
   experimental source cells with simulated assets; not physical fleet telemetry.
4. Data center: actual XJTU development import, quality/schema/source details,
   cell/sample pagination, charts and CSV export. Bounded CSV feature upload is
   permitted for declared compatible schema; hash/version input, validate shape,
   finite required fields, declared optional labels and physical IDs. Reject
   arbitrary serialized models and path traversal. Imported provenance remains
   declared/unverified until checked. No deleting a dataset used by a model/job.
5. Model center: real registrations, model details, hashes/availability, immutable
   training/evaluation/inference jobs and progress/errors. Add bounded real ET
   training on compatible DEVELOPMENT data with cell-grouped train/validation
   and train-only transforms. Store all selections/seeds/split identities,
   artifacts, metrics and sample predictions. Evaluate a registered model on
   compatible samples, report overlap/in-sample vs held-out within-platform
   accurately. Protected original holdouts unavailable. Model enable/retire is
   role-controlled; old predictions remain bound to original version.
6. Health: real inference jobs, previous input snapshot/hash and model version;
   SOH units as percentage points; raw outside-training-range diagnostics and
   branch disagreement NOT calibrated confidence. Show insufficient/outdated/
   domain-mismatch explicitly. Distinguish slow SOH maintenance assessment from
   rapid sensor alarm rules, and do not infer a failure mechanism from SOH alone.
   Configurable versioned demo health policy can open a health event -> alert,
   with an evidence snapshot; sample repeats cannot create duplicate alerts.
   Implement thresholds/persistence/cooldown and ack/resolve lifecycle sensibly.
7. Operations: alert-to-order linking and idempotent creation; order version
   checks; CREATED -> ASSIGNED -> ACCEPTED -> IN_PROGRESS -> RESOLVED -> VERIFIED
   -> CLOSED, plus explicitly allowed rejection/reopen/cancel. Every transition
   records actor/time/note and required evidence. Resolve requires outcome text;
   verification is done by a different authorized user, never the technician.
   Store safe bounded evidence attachments on server, not localStorage, validate
   magic/type/path and access control. Closing an order does not arbitrarily set
   an asset healthy or overwrite original SOH/alerts.
8. Personnel: persisted skill tags, on-call state, fixed declared location and
   workload computed from orders. Recommend eligible people by hard skills /
   availability first, then deterministic distance/workload ranking, showing
   each reason. Do not invent AI scores or choose ineligible/off-duty people.
   Dispatcher chooses assignee; no external messages sent. In-app notifications
   with unread/mark-read actions, not fake SMS/email delivery.
9. Feedback: append-only measured-capacity/SOH observations with measurement
   time, unit, provenance and author. Link to prediction/order without mutating
   predictions. A simulated repair is NOT true measured data or automatically
   admitted training data. Replacing a cell creates new installation identity /
   reference history; ordinary maintenance never resets SOH to 100%.
10. System: users/roles, audit with filtering; no last-admin removal; no arbitrary
    role escalation. Read-only observers work. Data separation survives reload,
    backend restart and concurrent repeated requests.
11. Demo: deterministic fixture site/cabinets/personnel, explicitly SIMULATED;
    EXPERIMENTAL signal replay can generate actual predictions and persist an
    operational demo. Synthetic failure injection must use a separate labelled
    scenario path, not contaminate real model metrics. Provide guided scenario
    operation buttons and reproducible CLI to drive one full end-to-end case.
12. Delivery: locked dependencies, scripts for setup/dev/build/serve/test/backup,
    README Chinese quickstart and CLI help, architecture/API/data dictionary,
    security & model limitations, acceptance report. No public/cloud deploy.
    Local default port 8787 (override supported). Test with isolated temp DB.

## Verification gate

Run backend tests for real auth/RBAC/CSRF, hierarchy, data import, job errors,
deduplication/idempotency, valid/invalid and concurrent transitions, attachment
access, independent verification, feedback provenance, persistence and protected
holdout exclusions. Use the real model bridge on a bounded development subset;
unit fakes must be clearly confined to tests. Smoke actual hybrid once on a tiny
query batch under the retained MPS guard; CPU fallback is not a false success.
Run frontend typecheck, production build and browser Playwright acceptance on
the same API. Include a full login -> model job -> alert -> assignment ->
technician resolve -> different-user verify -> close -> reload case. Inspect
screenshots and console errors at desktop and narrow viewport. Report actual
results and remaining limitations; do not infer completion from file counts.

## Official documentation consulted by host (2026-09-25)

- https://fastapi.tiangolo.com/tutorial/background-tasks/ (heavy jobs outside requests)
- https://docs.sqlalchemy.org/en/20/dialects/sqlite.html (transactions/foreign keys/concurrency)
- https://playwright.dev/docs/test-webserver (browser acceptance with managed server)
- https://vite.dev/guide/ (frontend build/runtime prerequisites)

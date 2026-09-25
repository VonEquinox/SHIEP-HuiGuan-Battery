# Greenfield application boundaries

The user explicitly authorized a complete greenfield application on 2026-09-25.
Write only in `battery_platform/`. Do not inspect, copy, modify, or migrate the
legacy application, SQL or previous product requirements. They are not inputs.
Read the root model laboratory only for verified model/data integration.
Do not modify `model_lab/` code, data, artifacts, test splits, dependencies or
historical experiment results. Do not score its three protected XJTU holdouts.
The earlier model-lab-only work boundary applies to that research task; this
new authorization permits this independent application directory.

No commits/pushes, paid services, external data uploads, .env/credentials/SSH
inspection, public server binding, or system-wide package changes. New local
dependencies and runtime files stay here; preserve at least 70 GiB disk free.
Do not disable MPS allocation limits. Use one model compute process at a time.
Loopback-only application/test servers may run during acceptance; stop all
processes you start before returning, with documented commands to launch.

Build real persistent behavior, not a mockup. Experimental dataset/predictions
and simulated assets/people are different provenance fields. A simulation is
allowed only with an explicit scenario ID and label. Never fabricate model
scores, BMS connections, sample counts, certainty, RUL or safety capabilities.
Use server-side authorization and state transitions. Never accept a client
prediction as a model result, nor load a user-uploaded pickle/model artifact.

Follow `docs/BUILD_SPEC.md`. Maintain `docs/PROGRESS.md` as a checked acceptance
matrix, with actual commands/evidence and outstanding gaps. Every visible
control must work, be deliberately disabled with explanation, or be removed.

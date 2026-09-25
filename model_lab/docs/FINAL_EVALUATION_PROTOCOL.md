# Frozen final evaluation protocol

Written 2026-09-25 before any model score on the three XJTU heldout cells.
The fixed half-log-space ensemble of TabICLv2 and ExtraTrees was selected by
the previously registered rule in ROUND3_TABICL_PROTOCOL.md. Its development
cell-macro MAE is 0.5858972199 pp. This protocol does not select another model.

Independent review amendment, still before final scoring: the original
three-query isolation check is insufficient evidence for the actual frozen
256-row path. Require verify_frozen_query_isolation.py to exercise all three
frozen seeds, 520 interleaved development/NASA input rows and chunk boundaries,
singleton probes, subdivision to 32 rows, reversed order, perturbations of
other query rows and repeated calls. Use no heldout XJTU input or query label.
The allowed log-prediction difference remains 1e-4, fixed before this check.
This extends execution evidence, not the model or model-selection recipe.

## Freeze and review gate

The active package is reports/round3/champion_hybrid_v2_streaming. It contains the immutable
21-development-cell context (2058 rows), the already frozen three-seed forest,
the publisher checkpoint identity, preprocessing and code hashes. Three
TabICL seeds each use the same public pretrained checkpoint, eight views and
the fixed full-development context. The forest branch is three seeds with
300 trees each, min_samples_leaf=1, selected from development only. Average
log predictions within each branch, then average the two branches equally.
There is no additional reference correction, learned ensemble weight or
inference-time fitting on a query label. Other experimental candidates are
not promoted because of final test scores.

Resource implementation amendment before any final score: v1 is preserved but
its native full-context cache construction was interrupted before prediction.
The first serial-cache attempt hit the deliberately retained MPS memory cap.
Version 2 retains exactly the same forest, all 2058 context rows, all 214
features, pretrained weights, eight views per seed, three seeds, normalization
and half-log mixture. It holds one view's cache at a time and caps independent
feature/row batching at 16/64; it does not truncate attention sequences.
The adapter matched the original 675 fold-0/seed-0 development predictions
within 4.48e-8 log-SOH before this amendment. Require the actual v2 frozen
interface's 520-row, three-seed isolation check to pass, including raw
preprocessing invariance and each 256-row chunk. Keep high/low MPS allocation
watermarks 0.7/0.5; never disable the memory limit. Retain all failed attempts.

The evaluator requires a separate host acceptance receipt, written only after
independent read-only code review and host metric/hash verification. It must
bind the exact package manifest, this protocol and evaluator source hashes.
Review acceptance concerns execution and leakage checks, not a guarantee of
universal accuracy or SOTA. Missing or stale acceptance prevents scoring.

## One-time scored populations

Primary final test: Batch-4/R3_battery-5, Batch-5/RW_battery-5 and
Batch-6/Sim_satellite_battery-5 from the unchanged 71D view. Their existing
QC/label co-residence is acknowledged; no prior model result was used for
selection. Use all eligible rows defined by the existing parser. Do not
change a quality threshold, capacity definition or denominator after scores.
Predict from current/reference/observed partial-charge ratio only, save the
prediction arrays and hash, THEN retrieve truth for metric computation.

Secondary stress test: the already audited NASA view (946 rows, 23 cells),
with current integrated-negative-current-to-first-2.7V labels relative to the
first eligible calibration. The earlier ET-only NASA result is already
known, so this is not a pristine unseen-source model-selection experiment.
No NASA target fitted the selected model. Report the source/protocol shift
separately from XJTU RPT-relative SOH, never pool their primary metrics.
All exclusions remain the original audit decisions. Out-of-training-range
flags are diagnostic and do not remove difficult rows.

The selected hybrid prediction is primary. Its frozen ET and TabICL branch
predictions are prespecified diagnostics on the same rows, not options for
choosing a post-test winner. Reproduce the earlier NASA ET predictions to
numeric tolerance; disagreement is an implementation failure to investigate,
not permission to pick a favorable output. A failed or interrupted run keeps
its manifest/artifacts and cannot be overwritten or silently restarted.

## Report and stop

Report each cell's n, MAE and RMSE in SOH percentage points; primary macro MAE
is the arithmetic mean of per-cell MAEs. Also give pooled metrics explicitly
labelled as cycle-weighted. Only three independent final XJTU cells means
limited inference about deployment populations; thousands of cycles do not
create thousands of independent batteries. Show predicted and true ranges,
input shift, saved hashes, actual runtime/device and all failure states.
Keep the selected recipe unchanged regardless of which branch is best on
these final cells. This test is not a matched published benchmark and cannot
establish battery-wide SOTA. After scoring, no further tuning on these three
cells is authorized by this protocol; any new development needs new external
holdouts or an explicitly new protocol. Do not claim zero overfitting or
production BMS safety based on this experiment.

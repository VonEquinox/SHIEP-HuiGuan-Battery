# Round 3 implementation checkpoint (2026-09-25)

The nested runner is implemented against the existing 71D view and frozen
three outer folds. The dated protocol amendment added the conditional anchored
RBF kernel before any real round-3 outer score. Eight methods, three fixed
configurations each, and at most 240 fits are scheduled. Inner validation
chooses configuration and neural update count; every outer refit starts from
scratch on outer training cells. Holdout rows are removed on load and the
three heldout cells remain unscored. Prior adaptive exposure of all 21
development cells and co-resident holdout labels remains documented.

Implementation: `scripts/train_nested_cv.py`,
`modeling/anchored_conditional.py`, `modeling/conditional_kernel.py`,
`scripts/smoke_nested_cv.py`, and `tests/test_nested_cv.py`. The runner saves
its input/code hashes, split manifest, train-only scalers and embedding bins,
inner checkpoints, refit artifacts, stage events, all predictions and failures,
seed-level and ensemble scores, per-cell/batch errors, and descriptive paired
cell-bootstrap intervals in fresh `reports/round3/nested/`. The anchored
candidate has 4,096 active parameters at 71D; the smoke recorded 30,049 for
matched MLP, 222,696 for embedded TabM, 10,276 for context FiLM, and 3,748
active of 10,276 total for no-context FiLM. The kernel and classic regressors
have no neural parameter count. Anchored component contributions and drop-term
outer diagnostics are reported without selection on those scores.

Verification command:

```sh
PYTHONDONTWRITEBYTECODE=1 model_lab/.venv/bin/python -m pytest -q model_lab/tests
```

The most recent completed suite reported 42 passed, one existing numeric-bin
warning. Synthetic end-to-end smoke command:

```sh
PYTHONDONTWRITEBYTECODE=1 model_lab/.venv/bin/python -m model_lab.scripts.smoke_nested_cv
```

Its eight-method result is in `reports/round3/smoke_kernel/summary.json`:
all methods completed inner selection and outer refit on synthetic cells with
ten updates and one seed. These synthetic errors are not battery evidence.

This provider reports `torch.backends.mps.is_available() == False`; no real
round-3 matrix was launched here. The host MPS command, from repository root,
is:

```sh
PYTHONDONTWRITEBYTECODE=1 model_lab/.venv/bin/python -m model_lab.scripts.train_nested_cv --device mps
```

It requires `reports/round3/nested/` to be absent and fails before fitting if
MPS is unavailable. Run it interactively and wait for completion. Do not run
the command twice into the same output directory. The output will be adaptive
development evidence, not independent SOTA proof. The existing bundle was
not regenerated; missing/short/interior temperature behavior remains a known
parser issue for a separately versioned data phase. The three heldout cells
must remain unscored pending independent review.

## 2026-09-25 measured outcome

Host ran the real MPS matrix (180 inner fits, 60 refits, 263.538 seconds,
zero failures) and independently recomputed all eight CSV metrics and hashes
in `reports/round3/nested/host_metric_verification.json`. Equal-cell geometric
ensemble MAE was 0.65754618 pp for ExtraTrees, 0.79118003 for embedded TabM,
and 0.87020338 for matched MLP. All conditional candidates were worse under
the fixed budget. These are adaptively exposed development-cell scores.

`ROUND3_EXTERNAL_PROTOCOL.md` froze ExtraTrees before NASA prediction. Its
successful CPU-reloadable 21-cell artifact is `reports/round3/champion_v3/`.
Raw NASA audit found 34 distinct cells among 38 MAT members, 946 eligible
later 2.7V-integrated samples in 23 cells, and six terminal-only paired
discharges excluded from primary scoring. Frozen zero-shot NASA cell-macro
MAE was 4.94788433 pp; all eligible inputs had a feature outside the XJTU
training range. See `reports/round3/nasa_audit/summary.json` and
`reports/round3/nasa_transfer/summary.json` for counts, exclusions, per-cell
errors and hashes. The NASA operational-discharge task is different from
XJTU RPT-relative SOH; no NASA label was used to fit or tune the champion.
The full test suite passed 49 tests. XJTU holdout labels remain unscored.

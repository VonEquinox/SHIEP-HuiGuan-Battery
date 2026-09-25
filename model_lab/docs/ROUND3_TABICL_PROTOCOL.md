# Modern prior and reference calibration follow-up

2026-09-25, before any TabICL battery prediction. This is a separate adaptive
development experiment, not an extension or rewrite of the closed 240-fit
round-3 nested comparison. Its purpose is to cover an actually public 2026
tabular foundation baseline and test reference calibration without adding a
trainable neural conditioning network. The NASA ET transfer result is already
known (4.94788433 pp); NASA is not used to select or fit any recipe here.

## Public source and fixed settings

Use official tabicl 2.2.0, published 2026-09-02. Code and public weights are
marked BSD-3-Clause by the publishers. Use only the official public file
`jingang/TabICL/tabicl-regressor-v2-20260212.ckpt`, publisher SHA256
`0db9cb538f114e79026bf08f45f41ad8dd7ad2de2aaca9a5ca8cd3bd9748ae7a`.
Limit download to 256 MiB, three attempts, retain at least 70 GiB free. All
cache/weights remain under model_lab/data/raw/tabicl. No account, credentials,
external inference service, or battery-data upload. After downloading, disable
implicit authentication, telemetry and automatic model download.

Use fixed n_estimators=8, default none/power normalizations, Latin feature
shuffling, batch_size=1, kv_cache='repr', float32, no AMP/FA3, four CPU threads,
seeds 0/1/2. MPS is requested explicitly. The regressor uses publisher pretrained
weights and in-context fitting, not new gradient training by this project.
It accepts no sample_weight in fit: the full training-cycle context is used,
so its training context is not equal-cell weighted. This limitation is reported;
the primary evaluation is still equal-cell MAE. No context resampling, feature
selection, fine-tuning, hyperparameter grid or best-seed selection is allowed.

## Split, leakage gate and bounded candidates

Reuse the same fixed three outer folds and 71D observations. Fit imputation
and scaling on each outer training set only. All methods use matched inputs
[x,reference,x-reference,log_window_ratio], 214 columns. No final-XJTU-holdout
rows, capacities, age or battery IDs enter the predictor. TabICL receives log
SOH from outer training cells only; its internal target/feature preprocessing
must use only that context. Since its recipe is fixed, no inner selection is
needed. Total TabICL fits: three folds times three seeds = nine, plus a bounded
synthetic/query-isolation check. Every failure remains visible. Never alter a
setting in response to outer scores to seek a win.

Before scoring each fit, compare predictions of fixed query rows alone, in a
batch, and with other query rows perturbed. With the fixed training cache,
their log predictions must agree within 1e-4. Otherwise stop and mark this
batched online-causal protocol unverified, rather than silently score a
transductive model. This is an implementation check, not a universal proof.

Prespecify four follow-up predictions plus the unchanged ET comparator:

1. Official TabICLv2 mean log prediction, exponentiated.
2. The same TabICL prediction minus its prediction at [r,r,0,0], then exp.
3. Existing frozen outer ExtraTrees prediction minus its prediction at
   [r,r,0,0], then exp. No tree is retrained for this diagnostic.
4. Equal geometric mean of uncalibrated TabICL and the existing outer ET
   prediction. Weight is fixed at one half, not fitted to validation errors.
5. Unchanged existing outer ET prediction, for exact consistency checking.

Reference calibration uses the known identity SOH(reference)=1 and no current
or future capacity. For a frozen predictor f with context c, it forms
H(x;c)-H(c;c). Identity is exact but improved accuracy is a hypothesis. This
does not establish global architectural novelty. Calibration diagnostics use
the ET configurations already selected by the earlier inner protocol; they
are not an equally retuned anchored-tree search.

## Reporting, selection and stopping

Write the manifest before predictions, including input/fold/model/package/code
hashes, recipes, and source history. Save every outer row, seed, prediction,
timing and query-isolation result. Report each seed's 21-cell macro MAE, its
mean/SD, separate geometric ensemble score, per-cell/batch/worst-cell results
and descriptive paired cell-bootstrap differences. Old adaptive exposures are
not erased by this additional experiment. Do not call these public benchmark
SOTA scores.

After all scheduled complete predictions, the current candidate for final
freeze is the smallest equal-cell geometric-ensemble development MAE among
these five fixed recipes. A numerical tie within 1e-6 pp prefers, in order,
unchanged ET, calibrated ET, TabICL, calibrated TabICL, then equal mixture.
Incomplete or query-isolation-failing candidates are ineligible; their failure
is not silently removed. This is candidate selection on development data.
The three XJTU holdouts remain unscored until the chosen full-development
recipe and inference package are frozen and independently audited. Once that
test is scored, no model/recipe may be changed on the basis of its errors.

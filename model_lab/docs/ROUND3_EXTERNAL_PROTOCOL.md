# Round 3 external transfer protocol (2026-09-25, before NASA predictions)

## Frozen champion and existing exposure

The completed 240-fit nested development matrix used 21 XJTU cells and three
previously exposed development folds. Independent CSV recomputation passed in
`reports/round3/nested/host_metric_verification.json`. Equal-cell geometric
ensemble MAE favors matched-input ExtraTrees (0.65754618 SOH pp), followed by
embedded TabM (0.79118003) and matched MLP (0.87020338). Conditional FiLM,
kernel and anchored candidates performed worse under this budget. This selects
an existing tree method, not a novel architecture. No XJTU suffix-5 holdout
has been model-scored; their labels are co-resident in prior audit files and
must remain unscored in this phase.

The final development-only champion is three ExtraTrees regressors with seeds
0, 1 and 2, 300 trees each, matched inputs `[x,reference,x-reference,
log(q_window/q_reference)]`, equal-cell sample weights and `min_samples_leaf=1`:
the mode of inner-selected leaves 1,1,3, with larger leaf breaking ties.
Use the existing fixed 71D `cv_physical/view_bundle.npz`, no raw XJTU rebuild.
Fit imputation and StandardScaler on current/reference observations from the
21 development cells only; fit log-target mean and SD on those cells only.
Each tree predicts standardized log SOH; exponentiate the mean of its three
log predictions. Save model, scaler, code/input/feature/task hashes and a
bounded numpy 71D current/reference/ratio -> positive finite SOH inference
function. Inference exposes neither RUL nor calibrated risk claims. CPU reload
and developmental-data prediction are execution checks, not an unbiased score.

## NASA source, lineage and pairing

Use only existing `data/raw/nasa_pcoe/battery_data_set.zip`, SHA-256
`82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e`.
The six nested ZIPs contain MAT cells and README files. Verify bounded ZIP
member sizes, aggregate expanded size, paths, CRC and MATLAB-file type before
reading. Read cells sequentially with per-member memory bounds; retain every
archive/member and byte hash. Deduplicate same physical battery ID only when
MAT bytes agree; conflicting hashes for one ID halt scoring and require an
explicit lineage decision. Keep all duplicate archive references in audit.

Count every distinct cell and every operation. An operation must have a valid
MAT date-vector start time; array order and timestamp order must agree or the
ambiguous region is excluded and reported. For each discharge, consume the
latest chronologically preceding charge with no intervening discharge or
reuse; impedance between them is allowed. Superseded charges and unpaired
discharges are counted. A cell's first eligible charge/discharge pair with a
valid 3.7-4.1 V prefix and standardized 2.7 V discharge capacity is its
initial calibration; score only later eligible pairs. This is a NASA-specific
operational calibration, not an XJTU RPT label.

Convert NASA charge `Time` seconds to minutes; map measured voltage/current/
temperature to the existing `build_cc_window` observation and use exactly its
fixed 3.7-4.1 V, first-crossing cutoff, visible current-CV and voltage-reversal
quality checks. The 71D view is `curve_features` (16 log charge increments,
16 charge fractions, 16 log time increments, 16 relative temperatures, five
summaries) followed by absolute temperature and current interpolated at the
3.7 V lower boundary, for both current and initial reference. Missing/short
temperature is represented as missing with explicit masks; parser changes are
versioned for NASA and do not alter the existing XJTU bundle. Inputs contain
no discharge measurements, capacity, life, cycle age, ID, or post-cutoff
signals. Record operation indices, timestamps, source hashes, cutoff indices,
pair/reference indices, and every exclusion reason.

## Capacity truth and decision gate

NASA README describes discharge `Capacity` as Ah to 2.7 V, while individual
protocols terminate at 2.0-2.7 V. Independently integrate measured negative
current over strictly increasing seconds, with trapezoid and interpolation at
the **first real downward 2.7 V crossing**. A discharge that ends above 2.7 V
is `protocol_terminal_capacity_not_standard_2.7`, with terminal integrated Ah
retained as a separate numerical quantity, never relabeled 2.7 V truth.
Start-at/below-2.7, missing crossing, non-finite signals, nonpositive Ah, or
ambiguous time/order are explicit statuses. Use the integrated 2.7 V capacity,
not the published `Capacity` summary, as the primary NASA truth; compare
summary Capacity to integrated 2.7 V and terminal Ah in an audit table without
changing inclusion based on agreement or prediction error. No label-derived
threshold is tuned. The first valid integrated-2.7 capacity is the within-cell
denominator; report SOH as later/initial integrated-2.7 capacity.

Produce the complete raw/quality/lineage audit before any external model
prediction. If timestamps, identity, charge pairing, label integration or
71D feature alignment remain materially ambiguous, stop after that audit and
report why. Otherwise run the frozen champion once on eligible NASA rows:
save per-row predictions, true SOH, per-cell and cell-macro MAE in percentage
points, counts, prediction range and out-of-training-feature-range diagnostics.
Do not fit, select, threshold or calibrate on NASA labels; no NASA fine-tuning.
The result is a NASA source/protocol transfer stress test, not same-benchmark
SOTA. Three XJTU heldouts remain unscored until independent host review.

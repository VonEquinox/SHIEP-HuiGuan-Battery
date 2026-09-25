# Round 3: bounded nested development comparison

Written before round-3 model scores. This phase reuses the immutable 71D
`reports/round2/cv_physical/view_bundle.npz` and the three outer cell folds in
`reports/round2/cv_physical/preregistration.json`. Do not rebuild the raw bundle,
add sources, or score any of the three suffix-5 heldout cells. The holdout labels
are already co-resident in old audit/bundle files and were inspected for quality;
this exposure cannot be undone. They have not been model-scored. Old outer
development labels and scores informed this candidate set, so round-3 outer
predictions are unseen within each fit, not independent discovery evidence.

## Candidates and budget

All candidates receive identical 71D current/reference observations. Direct
models also receive their difference and observed log partial-charge ratio.
There is no age, cell identifier, diagnostic capacity, or fixed unit charge-ratio
coefficient in any candidate. Seven methods, exactly three configurations each:

| Method | Three fixed configurations |
| --- | --- |
| Ridge on matched inputs | alpha 0.1, 10, 1000 |
| ExtraTrees on matched inputs | min leaf 1, 3, 7; 300 trees |
| Existing matched MLP | width 96; learning rate 0.0005, 0.002, 0.006 |
| Official numeric-embedded TabM direct baseline | width 96, 8 members, 16 quantile bins; same three learning rates |
| Existing FiLM reference potential with context | width 32, 4 members; same three learning rates |
| Same FiLM without context | width 32, 4 members; same three learning rates |
| Anchored conditional residual | width 24, bilinear rank 4; same three learning rates |

The anchored model predicts log SOH as
`delta @ beta + sum_j[(delta @ U)_j * (reference @ V)_j] +
0.1 * [h(current, reference) - h(reference, reference)]`, with
`delta=current-reference`. Its bilinear and residual terms change the slope
with reference context; the prediction is exactly zero when current equals
reference. The bilinear factors and residual are shrunk (weight decay 0.01 and
explicit 0.01 mean-squared contribution penalty); no monotonicity is imposed.
The ratio remains an available matched input for direct baselines, but this
anchored model has no fixed ratio coefficient. Parameter counts are recorded
per neural fit. The context/no-context FiLM comparison is the primary
conditioning ablation; anchored linear and nonlinear terms will be reported
separately as component diagnostics without another model search.

## Nested selection

For each frozen outer fold, choose the inner validation cells deterministically:
one lexicographically hash-ranked cell per available batch from that fold's
training cells, SHA-256 of `round3-inner-2047|fold|cell`. All other outer-training
cells are inner training. Assert disjoint physical cells and complete coverage.
Fit median imputation, standardization, target mean/scale, and TabM embedding
knots only on inner training cells. Score each configuration on the same inner
cells by the equal-cell mean absolute SOH percentage-point error, averaging
three fixed seeds (0,1,2) for stochastic methods. Ridge uses one deterministic
fit. No seed is discarded or selected. Tie-break by smaller configuration
index. For each neural seed/config, choose its best inner checkpoint every five
full-batch updates, maximum 500, patience 60 updates; tie-break to earlier
epoch. Select the configuration by mean of the three seed-level cell-macro
inner scores. Refit each seed of the selected configuration from scratch on all
outer training cells for its fixed inner-selected epoch count. Refit all
transforms and knots on those cells. Deterministic Ridge and seeded ExtraTrees
also refit on all outer training cells. Predict outer cells once; outer labels
never choose parameters, epoch, preprocessing, or checkpoint.

Neural loss is equal-cell weighted squared log-SOH error with training-only
target scale. AdamW, gradient clip 5, four CPU threads, no minibatches. The
fixed learning-rate grid is shared across neural methods. Record train/inner
and refit-train/outer gaps. Each stage logs wall time, seed, config, epoch,
status and failures; no failed run is silently dropped. Maximum scheduled
fits: 9 Ridge inner + 3 Ridge refits, 27 ExtraTrees inner + 9 refits, and
135 neural inner + 45 neural refits = 228 fits total. No replacement runs,
config additions, or score-driven budget expansion.

## Reporting and stopping

Primary score: mean of per-cell MAE over all 21 outer development cells,
computed from one prediction per cell/cycle/seed; never mean unequal fold
scores. Report the mean and SD across seed-level 21-cell scores, and separately
the geometric three-seed prediction ensemble. Report per-cell and per-batch
MAE, worst cells, paired cell-bootstrap 95% intervals versus matched MLP and
ExtraTrees (descriptive only after prior adaptation), complete selection and
epoch records, all failures, and train/inner/outer gaps. Save hashes of input,
fold manifest, code and model files; fit artifacts and prediction rows stay in
fresh `reports/round3/nested/`. Tests must cover label perturbation isolation,
train-only scaling/knots, cell disjointness, aggregation, and reference identity.
Stop after these seven methods and three configurations, subject to any dated
pre-score amendment below. No final holdout
prediction or SOTA claim in this phase. External NASA/HUST/MATR expansion is
separate; HUST/MATR LFP at max 3.6 V does not fit this 3.7-4.1 V task, and
lifetime benchmarks and prior inter-cell difference work do not establish
current-SOH novelty.

## Pre-score amendment, 2026-09-25

No real round-3 outer predictions existed when this amendment was written;
the only execution was a labeled synthetic smoke. Add an eighth, deterministic
conditional anchored RBF kernel candidate. For context `c=reference`, let
`psi(x,c)=phi([x,c])-phi([c,c])`, where `phi` is the RBF feature map. Its
kernel is the four-term inner product of these anchored differences. Fit
weighted kernel ridge to log SOH divided by a train-only standard deviation,
with **zero output mean** so identity at `x=c` remains exact. Three fixed
`(alpha,gamma)` configurations are `(0.01,0.25/142)`, `(0.1,1/142)`, and
`(1,4/142)`. The same inner-cell selection, outer refit, metric and holdout
rules apply. This adds 9 inner fits and 3 refits, giving a 240-fit cap. No
additional candidate or configuration will be added after real outer scoring.

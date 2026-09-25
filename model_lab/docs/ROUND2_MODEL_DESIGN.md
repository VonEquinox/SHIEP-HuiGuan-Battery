# Reference-consistent partial-charge SOH estimation

The primary task is measured RPT discharge capacity relative to an initial valid calibration, observed through a preceding fixed 3.7–4.1 V partial CC charge. It is not arbitrary-operation SOH or early-life RUL. The 55-cell inventory is not the independent labeled population: only cells with repeated valid diagnostics provide primary scored samples. Input masks and incomplete-window exclusions must be retained.

## Candidate structure

Let q(x) be incremental Ah observed within the fixed charge window and r an earlier calibrated reference. Define log(SOH(x|r)) = log(q(x)/q(r)) + g(x) - g(r). g is a shared scalar learned correction (MLP, official TabM ensemble, or a kernel potential). Initial residual output is zero. This is a testable inductive bias, not a proven physical law or global novelty claim. No artificial monotonic capacity constraint is imposed.

This construction exactly gives identity at the reference, reciprocal predictions upon reversal and multiplicative consistency when changing references. Geometric averaging of potential ensemble predictions preserves those identities; arithmetic averaging does not generally do so. Learned g is not claimed to identify a unique electrochemical degradation mechanism.

For training-cell errors e, sum over i<j of (e_i-e_j)^2 = n times sum of (e_i-mean(e))^2. Equal-cell centered residual loss therefore implements a normalized all-pair objective with O(N) work, without pretending the pairs are independent batteries. The main loss remains anchored log-SOH regression. Train-only target scaling and preprocessing are mandatory.

## Comparison and budget, fixed before scores

3 group-stratified development folds with random_state 2047; group=physical cell, stratum=batch. Filename suffix -5 holdouts remain excluded from all optimization and architecture selection. Primary metric = equal-cell MAE in SOH percentage points. Report RMSE, all seeds, per-cell errors, and failures. A training batch may contain many cycles but must weight cells equally.

Compare partial-charge ratio, Ridge, histogram gradient boosting, ExtraTrees, SVR, official TabM, current-only MLP, matched-information MLP, shared-potential MLP/TabM and a difference-kernel analogue. Ablate the partial-charge physical prior. Use three fixed hyperparameter configurations per candidate and three optimization seeds for stochastic methods. Maximum 150 epochs, validation every 5 epochs, patience 30; full configuration/fold/version manifest is written before fitting. No other-source or public-benchmark SOTA claim follows from this development protocol.

## Literature relationship

BatLiNet already uses intra/inter-cell differences; difference learning alone is not new. TabM is an official strong tabular ensemble architecture; its Kaggle applications are not battery-specific evidence. PBT and BatteryMFormer address early lifetime and trajectory prediction respectively; their scores cannot be compared to current SOH without exact task/split alignment. Future dense raw-cycle self-supervision and condition-aware forecasting are distinct experiments, not implemented features of this model.

## Development iteration B, before any holdout evaluation

The first 237 grouped-CV fits finished without failed runs. Best raw flattened-view candidate was an ExtraTrees ensemble, with development cell-macro MAE 0.91248 pp. The fixed partial-charge ratio itself had very large errors; it is not an adequate physical equality. Several neural fits reached the 150-update cap, so the next bounded comparison allows 500 updates with 60-update patience for every neural candidate. All previous results remain available, and this is explicitly adaptive development, not a new independent test.

Second view uses 16 voltage-local charge increments, charge fractions and time increments plus relative temperature and observed current summaries. This retains where charge accumulates instead of reducing the curve to a single integral. Absolute lower-boundary temperature is recovered from the same pre-cutoff raw segment, since a relative-temperature-only representation discards environmental information. No labels, future signals, cycle age or cell IDs enter the feature map. All competing models receive this view; improvements cannot automatically be attributed to a novel architecture.

Add the official piecewise-linear numeric embeddings from rtdl-num-embeddings, with knots fitted strictly on each training fold, to a stronger TabM baseline. The corresponding shared-reference model learns a linear potential plus an ensemble residual rather than imposing a unit coefficient on the partial-charge ratio. Also include CatBoost as a stronger tree baseline. Three configurations and three seeds remain the bounded rule. Reference identities remain exact at inference; originality and superiority remain unproven.

## Development iteration C: absolute-capacity supervision (before any test)

Iteration B completed 261 fits: matched MLP 0.63948 pp, ExtraTrees 0.65244 pp, embedded TabM 0.65484 pp, plain TabM 0.69455 pp, embedded shared potential 0.70427 pp cell-macro development MAE. These are adaptive CV scores, not final test results.

Relative-only training leaves the shared scalar potential weakly constrained across cells. A new ablation uses measured absolute discharge capacity and measured initial-reference capacity as additional TRAINING LABELS, never as features. Fit a common log-capacity function F(x) and predict log SOH=F(x)-F(reference). Compare absolute-only, relative-only and relative+0.25*absolute losses with the identical official TabM backbone, same 71 pre-cutoff observed features and same folds. Reference-capacity moments use one reference per training cell; loss weights remain equal-cell. Three learning rates, three seeds, 500 updates and 60-update patience are fixed before scores. This does not establish that capacity/SOH multitask learning is globally novel. It tests whether physically redundant but differently scaled supervision improves calibration on held-out cells.

Separately obtain the publicly linked NASA PCoE original archive with a 2 GiB download cap, CRC validation and source attribution. It is an independent source for a later cross-source stress test, not an excuse to merge incompatible diagnostic conditions or declare universal BMS validity.

## Development iteration D: calibration context, not a global scalar mapping

The global shared potential assumes a single partial-charge observation can identify absolute health independently of cell-specific calibration. This is stronger than necessary. Counterexample: observations x=a+h with a cell-specific offset a and initial reference r=a+1 yield h=1+x-r. No universal scalar g can satisfy g(x)-g(r)=log(1+x-r) for all x,r: using x=.8,r=1,z=1.2 gives pairwise ratios .8,.8 but direct ratio .6, not .64. The different pairs correspond to different calibration contexts, so forcing cross-context transitivity is inappropriate.

Replace g(x)-g(r) by H(x; c)-H(r; c), where c is the fixed initial reference for that physical cell. Exact identity and composition hold for a FIXED calibration context, without asserting equivalence across unrelated cells. Implement both an official TabM on matched conditional inputs and a compact FiLM/BatchEnsemble-style potential whose multiplicative and nonlinear modulation changes the mapping rather than adding a cancelling offset. Compare FiLM with/without reference conditioning and conditional TabM with/without absolute-capacity auxiliary supervision. Same data, folds, 3 learning rates, 3 seeds, 500 updates/patience60; no holdout access. This combines established components and a task-specific constraint; global novelty remains unproven.

NASA original archive is now downloaded and ZIP CRC verified: 209,708,670 bytes, SHA256 82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e. It contains six nested official archives. Do not call these six archives six independent experimental populations before resolving overlapping cell identities.

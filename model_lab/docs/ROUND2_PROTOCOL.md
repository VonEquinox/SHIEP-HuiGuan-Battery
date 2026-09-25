# Round 2: from smoke experiment to defensible battery research

## Diagnosis and scope

The first run used only 3 training cells and one validation cell, author-derived capacity provenance was unknown, and the anchor/history candidate did not beat the simple MLP. This cannot establish architecture superiority. Current scope is model/data research only; implementation and training are authorized by the user's latest instruction.

## Phase A: raw source audit and reproducible measured-label view

Read all 55 physical XJTU files sequentially with a bounded-memory parser. Audit cycle-level descriptions, physical cycle indices, sampled time/current/voltage/temperature, reference performance tests (RPT), regular-use vs diagnostic capacity, zero/missing values, time resets, interruptions, and reference capacity. Exclude Temperature_Compensation_Data.mat from physical-cell counts. Compute no interpolated SOH labels for primary evaluation. Retain raw paths/hashes and label provenance. Do not infer that the last logged cycle equals EOL.

Primary first task: estimate measured diagnostic discharge capacity from a preceding, explicitly bounded charging observation in that diagnostic cycle. A fixed voltage-window input and an entire-charge input are different tasks. Only time/current/voltage/temperature data up to the observation cutoff may enter inputs. No same-cycle full discharge capacity, future diagnostic value, whole-life per-cell normalization, test labels, or final cycle life in inputs. Preserve initial calibration assumptions explicitly. Save compact numeric arrays (no pickle/object arrays) and a manifest rather than every original time point in memory.

## Phase B: methods and hypotheses

Compare strong tabular baselines, official TabM or transparently named adaptations, simple curve neural models and an anchored residual candidate. A current-state path should remain independently useful; early-reference and history branches must justify incremental predictive value, with zero-initialized residual correction and branch ablation instead of an untested additive fusion. History must have real timestamps/cycle gaps, masks, and no post-cutoff access. Do not claim a neural architecture is original merely because it combines modules.

## Evaluation preregistration

Physical-cell grouping is mandatory; group/condition-balanced error is the primary metric. Freeze a multi-cell holdout before model selection, preserve the previously held-out 2C_battery-5, keep 2C_battery-4 in development, and record all historical exposures. Develop with grouped cross-validation and at least 3 optimization seeds. For protocol-shift results use leave-one-protocol-out and label it development if used to select architecture. No held-out test curve selection or target-based input exclusions. Model comparisons use identical observations, labels and splits. Save per-cell errors, paired differences, mean/std and failure cases; bootstrap at the cell rather than cycle level.

SOTA requires matching a public benchmark's exact task, dataset version, observation cutoff, label, split and metric plus runnable published baselines. A lower number on our custom protocol is not SOTA. BatteryLife/PBT early lifetime and PINN4SOH current health are separate comparison lanes.

## Acceptance artifacts

Raw audit JSON/CSV, compact input arrays and metadata, frozen split manifest, source/model references with exact versions, implementation tests, training/validation predictions and checkpoints, independent metric recomputation, and an explicit outstanding-work list. Keep the old reports intact. Evaluate the frozen test only after the candidate-selection rule is committed to a local immutable manifest (no git commit required).

## Raw audit amendment before any model scores

All 55 files were parsed. They contain 2,618 explicitly described diagnostic cycles and 25,024 routine cycles. Several batches have only one explicitly described diagnostic per cell; these cells can supply an initial reference but not longitudinal labels for the strict diagnostic-only task. Do not call all 55 cells training cases in that task. Routine full-discharge operational-capacity estimation is a separate task and cannot be silently relabelled standardized diagnostic SOH.

The first parser incorrectly required voltage samples exactly at 3.7 and 4.1 V and rejected any tiny voltage reversal. Correct the boundaries using real bracketing samples from the same positive-current, monotonic-time segment, and a chronological first-passage voltage representation. Observation ends at the first real sample crossing 4.1 V; all subsequent samples are excluded. The CC criterion is visible-window current coefficient of variation <= 0.1, with a maximum permitted voltage reversal of 0.05 V; these are declared engineering quality checks, not optimized label-based filters. Missing temperature is represented by NaN and a mask, never invented 25 C measurements. Integrate raw current before resampling. First valid diagnostic with a usable window establishes reference time; report any delayed calibration. Independently integrate negative-current discharge for label audit. Keep previous audit artifacts as evidence of the discovered bug.

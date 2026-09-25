# Implementation contract (v0)

This document fixes the first runnable model surface. It is a research implementation, not a claim of published novelty or state-of-the-art performance.

## Data view

The primary task is SOH at a declared prediction time. A row may use only a completed fixed physical charging prefix and at most the preceding 32 physical cycles. Features are neutral until the source schema proves their units. Candidate raw features are voltage, current, temperature when available, elapsed time, partial Ah/capacity normalized by a declared nominal or early-observed reference, and an availability mask. No same-cycle full discharge, end-of-life, future capacity, or whole-life normalized time is permitted.

The first three observed capacity cycles can be used as a warm-up reference only when the source documents them as observed and the run records that choice. Otherwise nominal capacity is used and the SOH definition states the difference. Rows before warm-up are ineligible rather than padded with a guessed value.

Capacity labels retain the source value and provenance: `measured_RPT`, `actual_full_discharge`, `interpolated`, or `unknown`. Primary SOH metrics use only confirmed comparable measured capacity; interpolated labels are auxiliary and separately reported. Capacity recovery is not removed.

## Models and fair comparison

The candidate CADA-Net v0 is a small causal model: shared multi-scale encoders for current and anchored reference views, explicit current/reference differences, causal dilated history aggregation, a slow history mean/slope, condition masking/gating, and a quality-aware fusion head. It is a hypothesis and is not described as a proven original contribution. The feature-only version is used when only author-derived statistics are available.

The first comparison uses the same available inputs and split for Dummy/Ridge (or ElasticNet), HistGradientBoosting/ExtraTrees, MLP, CPMLP-like baseline, and CADA v0. A current-only control is included. Each model has the same pre-registered bounded budget and at least three seeds for the development comparison; smoke runs may use fewer epochs and are labelled smoke, never final evidence. TabM is `not_run` unless a compatible package is actually installed.

Primary metrics are per-cell macro MAE and RMSE in percentage points, with protocol-level error when protocol metadata is verified. No test labels are used for selection or ensemble weights. RUL is `not_run` until endpoint and censoring are source-verified. Early-life log-life is separate and only uses eligible horizons (20/50/100 cycles).

## Required tests and artifacts

- physical-cell split has no intersection;
- train-only scaler statistics;
- perturbing future cycles cannot change a past prefix input;
- target capacity never appears in SOH features;
- masked/padded values do not alter a valid prediction;
- missing fields fail explicitly or use a recorded mask;
- save/load predictions agree;
- loss backpropagates on CPU and MPS when available.

Each run records source/data/split hashes, environment versions, seed, config, weight hash, train/validation curves, and a traceable per-sample prediction CSV. Test evaluation is a single frozen step after development selection.

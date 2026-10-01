# V2 independent Carbon / economic implementation

This document records the implementation of sections 9 and 14.3 of the
implementation plan. The module is intentionally independent of Agent runs,
Skills, natural-language reports, and dispatch objectives. It accepts only
versioned structured scenario, factor, activity, and policy records.

## Delivered files

- `app/carbon/schemas.py`: closed Pydantic input contracts for functional units,
  activities, state transitions, factors, cash flows, policy rules, scenarios,
  solve requests, and ledger requests. Extra fields are rejected. Source URLs,
  units, gas scope, geography, validity, provenance, and synthetic scenario IDs
  are mandatory where applicable.
- `app/carbon/engine.py`: deterministic activity multiplication; exact finite
  state probability recursion; expected inverse efficiency (`E[D/eta]`),
  replacement resets, explicit unmet service, renewal recursion, Bertsimas--Sim
  support, common-error comparative benefit, NPV, policy eligibility, finite
  Pareto enumeration, epsilon constraints, Gamma scans, and bounded sensitivity.
- `app/carbon/storage.py`: immutable input snapshots, short publication
  transactions, activity lineage, ledger idempotency/reversals, and formal
  export filtering.
- `app/carbon/jobs.py`: the existing job worker extension. Snapshots are taken in
  a transaction; solve computation runs outside the DB write transaction;
  publication checks cancellation, scenario revision, factor/policy hashes, and
  job state before inserting a result.
- `app/api_carbon.py`: `/api/v2/carbon/factors`, `/policy-benefits`,
  `/scenarios`, `/scenarios/{id}/solve`, `/results/{id}`, `/ledger`, reversal,
  and formal export routes. Writer role checks are server-side.
- `app/migrations/003_carbon.sql`: factor, policy, scenario, result, activity,
  and ledger tables. Reversal rows are constrained to one correction per entry.
- `tests/test_v2_carbon.py`: 21 deterministic checks covering golden arithmetic,
  unit/gas/boundary/source rejection, shared uncertainty cancellation, negative
  benefit, Gamma endpoints, state and renewal recursion, replacement capacity,
  no auxiliary double count, eligibility/cap/cash separation, Pareto and
  sensitivity breakpoints, cancellation, immutable publication, API role and
  idempotency, ledger reversals, and formal export exclusion.

## Exact calculation and accounting choices

Physical carbon remains kg CO2 or kg CO2e and is never currency-discounted.
Operating NPV, eligible policy cash, realized cash, and internal shadow value
are separate fields. An ineligible or insufficient-evidence policy rule adds no
cash. Shadow value is labelled an internal scenario value and cannot establish a
credit. Negative comparative benefits remain negative.

For a fixed activity inventory, Gamma support sorts absolute affine coefficients
and takes complete coefficients plus the fractional next coefficient. A shared
uncertainty key is one dimension, so repeated use of the same electricity factor
can cancel in a comparative benefit. Gamma is checked against the number of
shared dimensions and is never rendered as a confidence level.

State transitions are row-stochastic and distributions are checked after every
period. Available states advance age; replacement edges require a separate
age-zero new cohort distribution. Unavailable service is reported as unmet
energy or explicit standby energy. The engine never rewrites an old battery's
health as 100%. Settled accounting requires settled, non-unverified activity
records; projected model inventories cannot be promoted by changing a label.

Formal exports exclude synthetic, unverified, projected, unreviewed, invalid,
inconsistent reversal rows, and repeated claims on actual source records.
Recomputing Gamma cannot book another ledger row for the same scenario revision.
Grouping keeps activity, product-footprint, and
comparative-avoided claims separate, with boundary, period, gas scope, and
provenance retained. A formal export is still not a third-party verification or
credit issuance.

## Deliberate limits

The current robustness calculation is exact for affine coefficients and fixed
inventories. Efficiency and transition uncertainty must be supplied as explicit
separately labelled scenarios; they are not silently folded into Gamma. The
candidate solver enumerates finite candidates and does not implement integer
module-combination optimization. Sensitivity computes exact affine switch
breakpoints for one uncertainty source at a time with all other sources at
nominal, subject to a bounded work budget.

The existing V2 prediction profile exposes SOH and marks lifetime/efficiency
heads unsupported for current XJTU data. Therefore a client applicability flag
cannot turn an SOH output into a validated life or efficiency transition model.
The carbon snapshot rejects `validated_model` state inputs until a registered
prediction-to-transition adapter with supported `rul`/risk and `efficiency`
heads has been validated. Explicit measured or user-scenario transitions remain
available, and ordinary measured electricity accounting never requires a model.

## Verification

```text
cd battery_platform
../.venv/bin/python -m pytest tests/test_v2_carbon.py -q --disable-warnings
21 passed
```

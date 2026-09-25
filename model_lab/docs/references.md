# Audited implementation references

These references are read-only implementation context. They do not create samples, labels, or claims of novelty for this project. URLs and observed commit identifiers are recorded before use.

| Role | URL | Pinned source state | Use and limits |
| --- | --- | --- | --- |
| BatteryLife standardization and CPMLP reference | https://github.com/Ruifeng-Tan/BatteryLife | `main` at audit time; exact commit recorded in `data/derived/reference_commits.json` | Static comparison only. CPMLP is an explicitly implemented baseline here; its reported KDD task numbers are not comparable to this SOH task. |
| CPMLP source | https://raw.githubusercontent.com/Ruifeng-Tan/BatteryLife/main/models/CPMLP.py | `main` blob retrieved at audit time | Inspect architecture and masking behavior. This project implements and tests an explicit mask; it does not claim upstream code has leakage. |
| TabM | https://github.com/yandex-research/tabm | `main` at audit time; exact commit recorded in `data/derived/reference_commits.json` | Optional strong tabular baseline if a compatible package can be installed. No name-only reimplementation. |
| XJTU preprocessing reference | https://github.com/wang-fujin/Battery-dataset-preprocessing-code-library | `main` at audit time; exact commit recorded in `data/derived/reference_commits.json` | Static audit of source-derived capacity processing. `relative_time_min` is minutes; test-capacity cycles can be interpolated/extrapolated. |
| XJTU PINN4SOH reference | https://github.com/wang-fujin/PINN4SOH | `main` at audit time; exact commit recorded in `data/derived/reference_commits.json` | Static comparison only. Its full-cell scaling and capacity filtering are not copied; this project uses train-cell-only scalers and preserves raw recovery. |
| BatteryML comparison | https://github.com/microsoft/BatteryML | `main` at audit time; exact commit recorded in `data/derived/reference_commits.json` | Public comparison/reference only; no duplicate sample import. |

## Rules extracted from the source audit

- Capacity provenance is a first-class field. A row is never called measured merely because it has a numeric capacity. Use `measured_RPT`, `actual_full_discharge`, or `interpolated` only when the source evidence supports it; otherwise use `unknown`.
- `relative_time_min` is converted to seconds by a recorded transformation, without changing the source field.
- Author-derived CSVs without a physical cycle identifier retain `row_index` as derived order only. It cannot establish real RUL.
- No full-lifecycle scaler, test-label-driven outlier deletion, or source-wide 3-sigma capacity deletion is permitted. Scalers are fitted on training cells only.
- The source helper `get_CC_value` has a 3.9 A threshold and is protocol-specific; it is not reused for HUST or other protocols without an explicit protocol configuration.
- Capacity recovery is preserved. No bidirectional filtering or future-aware smoothing is allowed in prefix features.

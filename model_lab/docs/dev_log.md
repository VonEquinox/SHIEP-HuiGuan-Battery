# Development log

## Round 2 host implementation and audit checkpoint

- Full original XJTU files were read sequentially. The initial parser's exact-voltage-boundary bug incorrectly rejected valid charge windows. Host fixed real-sample bracketing, first-passage chronology, pre-resampling raw-current integration and missing-temperature masking; 8 parser/regression tests passed before reprocessing.
- Reprocessing completed all 55 physical cells in 221.90 seconds: 2,618 diagnostic and 25,024 routine cycles; 2,458 valid input windows and 2,404 scored diagnostic rows. Of 55 physical cells, only 24 have longitudinal usable diagnostic labels for this deliberately strict task; the remaining cells are not silently included as training examples.
- The bundle contains 21 development cells and 3 untouched scored holdouts (Batch4/5/6 suffix -5); the previous Batch1 suffix -5 is still protected but has no scored longitudinal diagnostic samples. No model has scored a holdout.
- Added shared reference-potential MLP/TabM, a matched-information baseline and a difference-kernel analogue, with exact reference identities and a linear-time within-cell pair objective. Design and bounded grouped-CV budget are recorded before model scores in ROUND2_MODEL_DESIGN.md. Global novelty/SOTA is not claimed.
- Installed official tabm 0.0.3 and catboost 1.2.8 in the isolated environment; existing torch retained. Exact environment exported to locks/round2-freeze.txt.

## 2026-09-25

- Started isolated `model_lab/` work in a clean checkout.
- Verified host: Apple arm64, 16 GiB unified memory, 10 logical CPUs, approximately 172 GiB available before downloads, `uv 0.11.25`, system Python 3.14.6.
- Read the project data contract. The legacy `SeversonBattery.mat` has unverified lineage and is not accepted as a new trusted source.
- Created the source registry, user requirements, README, and this log. Data statuses remain pending until official metadata and checksums are fetched.
- Planned next actions: create Python 3.12 environment, install pinned scientific/test packages and arm64-compatible PyTorch, query Zenodo record metadata, then execute bounded resumable XJTU download and inspection.
- Official XJTU metadata was fetched: record 10963339, V1, CC BY 4.0, one 2,438,769,934-byte ZIP, MD5 `a635cef9678e0de21f9d5c1f78a4342c`.
- The managed XJTU download stopped at a stable partial 2,273,312,768 bytes. Partial SHA-256 is `c45d5bd698b65fe99e2facccb3f684924b1124337ccba4c3d1cd565718c93ccf`; it is not treated as a valid archive and was not extracted. No download was replayed after the stop.
- GitHub API fixed author-derived paths at PINN4SOH commit `cc3cc5053caf38f04e0665f7f88cb109144d035e`. Five 2C CSVs were downloaded to `data/derived/author/PINN4SOH/xjtu/`; their combined size is 607,594 bytes and each SHA-256 is recorded in `reports/dev_run/config.json`.
- Reworked the parser contract to require an explicit allowlist, reject target-derived fields and duplicate physical cell IDs, cache per-cell arrays, keep train-only imputation masks, and preserve `label_provenance`.
- `model_lab/.venv` uses Python 3.12.12, torch 2.14.0, CPU fallback because MPS is built but unavailable. A real forward/backward/SGD step succeeded on CPU.
- Ran one bounded real development comparison on 5 derived cells (3 train / 1 validation / 1 frozen test), seed 0, 3 epochs, batch 32, four CPU threads. All eight requested model slots produced validation outputs; test labels were not evaluated and unknown derived capacity is not primary measured SOH evidence. See `reports/dev_run/summary.json`.
- Fixed-contract tests now pass: 11 passed. No formal model claim, RUL, raw-curve training, TabM, ablations, or hyperparameter search was run.

## Evidence files

- Runtime events: `data/derived/runtime_events.jsonl`
- Download events: `data/derived/download_events.jsonl`
- Registry snapshot: `data_sources.json`
- Candidate split: `data/derived/cell_split_candidate.json` (created only after source cells are verified)

No model training is claimed in this stage.

## Host verification checkpoint

XJTU full archive downloaded, official MD5 verified, safely extracted; 55 cell files plus one temperature-compensation file. One raw cell structure inspected. 30-epoch, one-seed development run executed on host MPS after train-only target scaling and best-checkpoint reporting fixes. All 8 prediction reports recomputed and 7 saved model artifacts reloaded. 15 unit tests passed. CADA-v0 has not beaten the best MLP baseline. Full raw-data modeling, HUST/MATR, external tests and ablations remain pending. See HOST_REVIEW.md.

## 2026-09-25 round-3 external checkpoint

- Host completed and independently verified the fixed eight-method nested matrix: 180 inner fits, 60 outer refits, zero failures. Equal-cell geometric ensemble MAE was 0.65754618 pp for ExtraTrees, the best current development candidate; new conditional models did not beat it.
- Froze ExtraTrees at 300 trees per seed (0, 1, 2), `min_samples_leaf=1` by outer-fold mode, on all 21 development cells. CPU reload reproduced predictions exactly. The successful model and hash manifest are in `reports/round3/champion_v3/`; two earlier failed dtype-reload attempts remain in `champion/` and `champion_v2/` for provenance.
- Audited NASA PCoE archive without model scoring first: 38 MAT members, 34 distinct cells, four byte-identical duplicate members, 7,565 operations, 977 eligible charge/discharge pairs, 946 later integrated-2.7V samples across 23 cells. Six paired discharges lacked a real 2.7V crossing; 11 cells had no later eligible sample. No MAT cell failed parsing.
- Frozen zero-shot ET NASA transfer: 23-cell macro MAE 4.94788433 pp and pooled MAE 4.13638987 pp on the 946 samples. Every row had at least one feature outside the XJTU training range. This is source/protocol transfer evidence, not an XJTU benchmark result. All three XJTU holdouts remain unscored.
- `PYTHONDONTWRITEBYTECODE=1 model_lab/.venv/bin/python -m pytest -q model_lab/tests`: 49 passed, one existing numeric-bin warning. Raw audit and predictions are retained in `reports/round3/nasa_audit/` and `reports/round3/nasa_transfer/`.

# Model lab user requirements

## Boundaries

- Work only in `model_lab/`; do not modify legacy source code, SQL, requirements documents, existing weights, or frontend/backend behaviour.
- Do not commit or push from this task.
- Keep newly downloaded data, caches, and virtual environments out of version control.
- Do not read `.env`, API keys, SSH configuration, or transmit local machine information.
- New model structure must be treated as a hypothesis until independently compared with strong baselines under a fair compute/data budget. Do not present assembled paper terminology as proven novelty.

## Scientific requirements

- Start with SOH and early-life prediction. Add RUL only when the endpoint definition and ground truth can be verified source by source.
- Split by physical cell, never by randomly mixing cycles from one cell across train/validation/test.
- Fit normalization and other training statistics on training cells only; record the fitted statistics and schema.
- Keep raw and derived data separate. Preserve source IDs and a trace from each prediction to dataset version, cell, cycle, model version, and input snapshot.
- Do not remove physical capacity recovery. Do not use bidirectional filtering or future information in an early-life feature.
- Use neutral field names until the source documentation verifies voltage, current, temperature, capacity, resistance, SOC, SOH, PCL, or RUL semantics.
- Do not infer `SOH = 1 - PCL`, a capacity baseline, an endpoint, or a unit from a column name alone.

## Data and licensing

- Verify official metadata, latest file list, version, source URL, license, and checksums before downloading.
- Prefer the complete XJTU record at `https://zenodo.org/records/10963339`, then evaluate HUST and MATR if space and access permit.
- Keep this stage bounded to at most 40 GiB of new disk use and retain at least 70 GiB free. Do not download the full KIT corpus.
- Do not use data requiring a contract, email, payment, or non-public credentials.
- Downloader retries are bounded to three and all attempts are logged.

## Reproducibility and reporting

- Every source has a registry entry with source/version/license/status and raw-file SHA-256 when available.
- Every cell split has an immutable candidate file and an identity mapping back to the raw source.
- Reports must state what was actually downloaded and parsed, including blocked or partial sources, byte sizes, fields, units, and unresolved labels.
- Claim only training actually completed and independently verified; do not equate development execution with SOTA or final acceptance.

## Current user authorization: research and iteration round 2

The user explicitly requests broader research, raw-data quality audit, better model/data design, and continued implementation/training toward independently demonstrated SOTA. Changing model architecture and experimental design inside model_lab is authorized. Existing application remains untouched. Research, implement, train, and report actual evidence in bounded stages; no unattended experiments, paid services, external uploads, or changes outside the project. Preserve earlier development/test history rather than resetting it. The previously exposed 2C_battery-4 is development data, and 2C_battery-5 remains a protected held-out cell until a frozen evaluation is authorized by this protocol.

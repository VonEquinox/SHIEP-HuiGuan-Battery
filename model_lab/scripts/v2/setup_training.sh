#!/usr/bin/env sh
set -eu
# Run from repository root. This isolated environment does not replace V1 runtime.
uv venv model_lab/reports/v2/runtime/.venv --python 3.12
uv pip install --python model_lab/reports/v2/runtime/.venv/bin/python -r model_lab/configs/v2_training_requirements.txt

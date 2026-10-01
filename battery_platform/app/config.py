from __future__ import annotations
import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
MODEL_ROOT = REPO_ROOT / "model_lab"
RUNTIME = Path(os.environ.get("BATTERY_RUNTIME", str(APP_ROOT / "runtime"))).resolve()
PORT = int(os.environ.get("BATTERY_PORT", "8787"))
ML_PYTHON = Path(
    os.environ.get("BATTERY_ML_PYTHON", str(REPO_ROOT / ".venv/bin/python")
                   if (REPO_ROOT / ".venv/bin/python").is_file()
                   else str(MODEL_ROOT / ".venv/bin/python"))
).absolute()
SCHEMA = "xjtu_71d_partial_cc_v1"
ROLES = ("admin", "researcher", "dispatcher", "technician", "viewer")
MAX_UPLOAD = 8 * 1024 * 1024
MAX_SAMPLES = 5000
MAX_JOB_ROWS = 256


def prepare_runtime():
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ("jobs", "models", "attachments", "backups"):
        (RUNTIME / name).mkdir(exist_ok=True, mode=0o700)

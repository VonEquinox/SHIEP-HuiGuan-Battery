"""Bounded V2 CLI child with the same global compute lock as the V1 bridge."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import runpy
import sys
import threading
import time


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {"train", "calibrate", "evaluate", "export"}:
        raise SystemExit("Unknown V2 model command")
    parent = int(os.environ.get("BATTERY_PARENT_PID", "0"))
    if parent <= 1:
        raise SystemExit("V2 model worker requires an owning server process")

    def watch_parent():
        while True:
            try:
                os.kill(parent, 0)
            except ProcessLookupError:
                os._exit(70)
            time.sleep(0.25)

    threading.Thread(target=watch_parent, daemon=True).start()
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root.parent))
    module, arguments = sys.argv[1], sys.argv[2:]
    with (root / "runtime/model-compute.lock").open("a+") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                print("等待全局模型计算锁", flush=True)
                time.sleep(0.25)
        try:
            sys.argv = [f"model_lab.scripts.v2.{module}", *arguments]
            runpy.run_module(f"model_lab.scripts.v2.{module}", run_name="__main__")
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


if __name__ == "__main__":
    main()

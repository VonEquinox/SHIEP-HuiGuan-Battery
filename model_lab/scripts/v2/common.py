from __future__ import annotations
import json
from pathlib import Path
import subprocess
import numpy as np
from model_lab.modeling.v2.contracts import sha256_file


def write_json(path,obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False))


def code_version():
    root=Path(__file__).resolve().parents[2]
    return {str(p.relative_to(root)):sha256_file(p) for folder in (root/"modeling"/"v2",root/"scripts"/"v2") for p in sorted(folder.glob("*.py"))}


def subset(arrays,rows,split):
    ix=np.flatnonzero([r["split"]==split for r in rows])
    return {k:v[ix] for k,v in arrays.items()},[rows[i] for i in ix]


def get_model(run):
    from model_lab.modeling.v2.baselines import DomainBaseline
    from model_lab.modeling.v2.multitask import MultiTaskModel
    manifest=json.loads((Path(run)/"run.json").read_text())
    if manifest["family"]=="M1":model=DomainBaseline.from_dict(json.loads((Path(run)/"model.json").read_text()))
    else:model=MultiTaskModel.load(manifest["spec"],Path(run)/"weights.npz",manifest["seed"],manifest["survival_grid"],manifest["label_support"],manifest.get("label_support_by_domain"))
    return manifest,model


def resolve_dataset_path(record):
    path=Path(record["dataset_manifest"])
    if path.exists():return path
    if "model_lab" in path.parts:
        relative=Path(*path.parts[path.parts.index("model_lab"):])
        candidate=Path(__file__).resolve().parents[3]/relative
        if candidate.exists():return candidate
    raise FileNotFoundError("dataset bundle is missing; run V2 ingest/features or restore the tracked development bundle")

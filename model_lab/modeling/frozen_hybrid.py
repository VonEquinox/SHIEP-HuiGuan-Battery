"""Frozen local TabICLv2/ExtraTrees SOH ensemble; no inference-time label fitting.

The immutable *development* context is required by the pretrained regressor.
Only one prior/cache is live at a time to bound memory on the 16-GiB host.
This favors auditable batch research, not a claim of low-latency production BMS.
"""
from __future__ import annotations

import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path

import numpy as np
import torch
from sklearn.preprocessing import StandardScaler

from model_lab.modeling.frozen_et import load_champion, predict_soh, validate_inputs

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_SHA = '0db9cb538f114e79026bf08f45f41ad8dd7ad2de2aaca9a5ca8cd3bd9748ae7a'


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024**2):
            value.update(block)
    return value.hexdigest()


def matched_input(x, r, ratio, artifact):
    x, r, ratio = validate_inputs(x, r, ratio)
    scaler = StandardScaler()
    scaler.mean_ = np.asarray(artifact['mean'])
    scaler.scale_ = np.asarray(artifact['scale'])
    scaler.var_ = scaler.scale_**2
    scaler.n_features_in_ = 71
    if not np.isfinite(scaler.scale_).all() or np.any(scaler.scale_ <= 0):
        raise ValueError('Invalid frozen scaler')
    median = np.asarray(artifact['median'])
    sx = scaler.transform(np.where(np.isfinite(x), x, median)).astype(np.float32)
    sr = scaler.transform(np.where(np.isfinite(r), r, median)).astype(np.float32)
    return np.concatenate((sx, sr, sx-sr, ratio[:, None]), axis=1)


class FrozenHybrid:
    def __init__(self, package: str | Path, device: str = 'mps'):
        self.package = Path(package)
        self.manifest = json.loads((self.package/'manifest.json').read_text())
        m = self.manifest
        if m.get('recipe') != 'tabicl_et_equal' or m.get('et_weight') != .5:
            raise ValueError('Unsupported or modified recipe')
        if m.get('checkpoint_sha256') != CHECKPOINT_SHA:
            raise ValueError('Non-publisher checkpoint')
        if importlib.metadata.version('tabicl') != '2.2.0':
            raise ValueError('Pinned TabICL package required')
        for key, source in (('inference', ROOT/'modeling/frozen_hybrid.py'),
                            ('et_inference', ROOT/'modeling/frozen_et.py')):
            if sha256(source) != m['code_sha256'][key]:
                raise ValueError(f'Inference code changed after freezing: {key}')
        for name, expected in m['package_file_sha256'].items():
            if Path(name).name != name or sha256(self.package/name) != expected:
                raise ValueError(f'Package integrity check failed: {name}')
        self.weight = ROOT/'data/raw/tabicl/tabicl-regressor-v2-20260212.ckpt'
        if sha256(self.weight) != CHECKPOINT_SHA:
            raise ValueError('Pretrained weight integrity check failed')
        self.et = load_champion(self.package/'et_champion.joblib')
        with np.load(self.package/'development_context.npz', allow_pickle=False) as context:
            self.x_context = np.asarray(context['x'], dtype=np.float32)
            self.y_context = np.asarray(context['log_soh'], dtype=np.float64)
            cells = context['cell'].astype(str)
        if self.x_context.shape != (m['train_rows'], 214) or self.y_context.shape != (m['train_rows'],):
            raise ValueError('Context dimensions changed')
        if not np.isfinite(self.x_context).all() or not np.isfinite(self.y_context).all():
            raise ValueError('Invalid immutable context')
        if sorted(set(cells)) != m['train_cell_ids'] or set(cells) & set(m['heldout_cell_ids']):
            raise ValueError('Context cell identity conflict')
        if device not in ('mps', 'cpu') or (device == 'mps' and not torch.backends.mps.is_available()):
            raise ValueError('Requested local device unavailable')
        self.device = device
        os.environ['HF_HOME'] = str(ROOT/'data/raw/tabicl/cache')
        os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['DO_NOT_TRACK'] = '1'

    def predict_components(self, current, reference, log_window_ratio, chunk_rows: int = 256):
        """Inputs are features only. Returns three positive SOH predictions.

        Calls rebuild a deterministic context cache for each seed; no supplied
        query label, capacity or future observation is accepted by this API.
        """
        if not 1 <= chunk_rows <= 512:
            raise ValueError('Bounded query chunk size required')
        from tabicl import TabICLRegressor
        z = matched_input(current, reference, log_window_ratio, self.et)
        forest = predict_soh(current, reference, log_window_ratio, self.et)
        logs = []
        torch.set_num_threads(4)
        for seed in (0, 1, 2):
            prior = TabICLRegressor(n_estimators=8, batch_size=1, kv_cache='repr',
                model_path=str(self.weight), allow_auto_download=False, device=self.device,
                use_amp=False, use_fa3=False, offload_mode='auto',
                disk_offload_dir=str(ROOT/'data/raw/tabicl/offload'), random_state=seed, n_jobs=4)
            try:
                prior.fit(self.x_context, self.y_context)
                parts = [np.asarray(prior.predict(z[j:j+chunk_rows]), dtype=float)
                         for j in range(0, len(z), chunk_rows)]
                logs.append(np.concatenate(parts))
            finally:
                del prior
                gc.collect()
                if self.device == 'mps':
                    torch.mps.empty_cache()
        mean_log = np.mean(logs, axis=0)
        with np.errstate(over='raise', invalid='raise'):
            result = {'soh': np.exp(.5*(mean_log+np.log(forest))),
                      'extra_trees_soh': forest, 'tabicl_soh': np.exp(mean_log)}
        if any(not np.isfinite(value).all() or np.any(value <= 0) for value in result.values()):
            raise ValueError('Invalid ensemble output')
        return result

    def predict(self, current, reference, log_window_ratio):
        return self.predict_components(current, reference, log_window_ratio)['soh']

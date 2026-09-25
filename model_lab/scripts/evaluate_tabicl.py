"""Pinned local TabICLv2 comparison. No holdout scoring or gradient training."""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import shutil
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

from model_lab.scripts.train_nested_cv import (
    ROOT, VIEW, FOLDS, cell_indices, cell_metrics, digest, fit_transform,
    load_development, matched, paired_bootstrap, summarize_predictions,
)

SOURCE = ROOT / 'data/raw/tabicl'
WEIGHT = SOURCE / 'tabicl-regressor-v2-20260212.ckpt'
WEIGHT_SHA = '0db9cb538f114e79026bf08f45f41ad8dd7ad2de2aaca9a5ca8cd3bd9748ae7a'
URL = 'https://huggingface.co/jingang/TabICL/resolve/main/' + WEIGHT.name
PROTOCOL = ROOT / 'docs/ROUND3_TABICL_PROTOCOL.md'
OUT = ROOT / 'reports/round3/tabicl_followup'
PRIOR = ROOT / 'reports/round3/nested'
METHODS = ('extra_trees_matched', 'extra_trees_anchored', 'tabicl',
           'tabicl_anchored', 'tabicl_et_equal')


def offline_environment() -> None:
    os.environ['HF_HOME'] = str(SOURCE / 'cache')
    os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['DO_NOT_TRACK'] = '1'


def prepare_checkpoint() -> dict:
    SOURCE.mkdir(parents=True, exist_ok=True)
    attempts = []
    if WEIGHT.exists():
        if digest(WEIGHT) != WEIGHT_SHA:
            raise ValueError('Existing checkpoint hash mismatch; refusing overwrite')
        record_path = SOURCE/'source_record.json'
        if record_path.exists():
            record = json.loads(record_path.read_text())
            if record.get('sha256') != WEIGHT_SHA:
                raise ValueError('Existing source record conflicts with pinned checkpoint')
            return record
    else:
        if shutil.disk_usage(SOURCE).free < 70 * 1024**3 + 256 * 1024**2:
            raise RuntimeError('Insufficient disk reserve')
        for attempt in range(1, 4):
            temporary = SOURCE / f'{WEIGHT.name}.attempt{attempt}.part'
            if temporary.exists():
                raise FileExistsError(temporary)
            try:
                start = time.monotonic()
                h = hashlib.sha256(); count = 0
                req = urllib.request.Request(URL, headers={'User-Agent': 'BatteryResearch/1.0'})
                with urllib.request.urlopen(req, timeout=45) as response, temporary.open('xb') as f:
                    declared = int(response.headers.get('Content-Length', '0'))
                    if declared > 256 * 1024**2:
                        raise RuntimeError('Download exceeds 256 MiB cap')
                    while block := response.read(1024**2):
                        count += len(block)
                        if count > 256 * 1024**2 or time.monotonic()-start > 300:
                            raise RuntimeError('Bounded download limit reached')
                        h.update(block); f.write(block)
                if declared and count != declared:
                    raise RuntimeError('Incomplete HTTP response')
                if h.hexdigest() != WEIGHT_SHA:
                    raise RuntimeError('Publisher SHA256 mismatch')
                temporary.replace(WEIGHT)
                attempts.append({'attempt': attempt, 'status': 'verified', 'bytes': count})
                break
            except Exception as error:
                attempts.append({'attempt': attempt, 'status': 'failed', 'error': repr(error)})
                (SOURCE/'download_attempts.json').write_text(json.dumps(attempts, indent=2))
        if not WEIGHT.exists():
            raise RuntimeError('All bounded download attempts failed')
    record = {'url': URL, 'publisher_file_page': URL.replace('/resolve/', '/blob/'),
              'sha256': digest(WEIGHT), 'publisher_sha256_verified': True,
              'bytes': WEIGHT.stat().st_size, 'package': importlib.metadata.version('tabicl'),
              'license': 'BSD-3-Clause, publisher code/model pages', 'attempts': attempts,
              'status': 'public_checkpoint_verified', 'external_battery_upload': False}
    (SOURCE/'source_record.json').write_text(json.dumps(record, indent=2))
    return record


def estimator(seed: int):
    from tabicl import TabICLRegressor
    return TabICLRegressor(n_estimators=8, batch_size=1, kv_cache='repr',
        model_path=str(WEIGHT), allow_auto_download=False, device='mps',
        use_amp=False, use_fa3=False, offload_mode='auto',
        disk_offload_dir=str(SOURCE/'offload'), random_state=seed, n_jobs=4)


def query_isolation(model, query: np.ndarray) -> dict:
    probe = np.asarray(query[:3], dtype=np.float32).copy()
    alone = np.array([float(model.predict(probe[i:i+1])[0]) for i in range(len(probe))])
    batch = np.asarray(model.predict(probe), dtype=float)
    changed = probe.copy(); changed[1:] = changed[1:] * 7. + 13.
    perturbed_first = float(model.predict(changed)[0])
    difference = max(float(np.max(np.abs(alone-batch))), abs(perturbed_first-alone[0]))
    if not np.isfinite(difference) or difference > 1e-4:
        raise RuntimeError(f'Query isolation gate failed: {difference}')
    return {'max_log_prediction_difference': difference, 'tolerance': 1e-4,
            'single_vs_batch_and_other_query_perturbation': 'passed'}


def positive_exp(log_prediction: np.ndarray) -> np.ndarray:
    with np.errstate(over='raise', invalid='raise'):
        result = np.exp(np.asarray(log_prediction, dtype=np.float64))
    if not np.isfinite(result).all() or np.any(result <= 0):
        raise ValueError('Invalid SOH prediction')
    return result


def main(args) -> int:
    source = prepare_checkpoint()
    if args.prepare_only:
        print(json.dumps(source, indent=2), flush=True); return 0
    offline_environment()
    if importlib.metadata.version('tabicl') != '2.2.0':
        raise ValueError('Pinned package version changed')
    if not torch.backends.mps.is_available():
        raise RuntimeError('Host MPS required; no battery fit started')
    torch.set_num_threads(4)
    out = Path(args.out)
    if out.exists():
        raise FileExistsError('Fresh result directory required')
    data, held = load_development(VIEW)
    original = json.loads(FOLDS.read_text())
    if sorted(original['heldout_cells']) != held:
        raise ValueError('Holdout identity mismatch')
    from tabicl import TabICLRegressor
    import inspect
    out.mkdir(parents=True)
    manifest = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'fixed-recipe adaptive development follow-up; holdout unscored',
        'package': 'tabicl==2.2.0', 'checkpoint_sha256': WEIGHT_SHA,
        'runner_sha256': digest(Path(__file__)), 'protocol_sha256': digest(PROTOCOL),
        'view_sha256': digest(VIEW), 'folds_sha256': digest(FOLDS),
        'regressor_source_sha256': digest(Path(inspect.getfile(TabICLRegressor))),
        'prior_manifest_sha256': digest(PRIOR/'manifest.json'),
        'folds': original['folds'], 'heldout_cells_unscored': held,
        'methods': METHODS, 'seeds': [0, 1, 2], 'context_fits': 9,
        'n_estimators': 8, 'batch_size': 1, 'kv_cache': 'repr',
        'device': 'mps', 'amp': False, 'sample_weight_supported': False,
        'sample_weight_note': 'Native full-cycle context; macro evaluation remains equal-cell',
        'target': 'log of observed diagnostic capacity ratio',
        'query_gate_tolerance': 1e-4, 'mixture_weight': .5,
        'external_inference_service': False}
    manifest['et_artifact_sha256'] = {
        f'extra_trees_matched-f{fold}-s{seed}.joblib':
        digest(PRIOR/f'extra_trees_matched-f{fold}-s{seed}.joblib')
        for fold in range(3) for seed in (0, 1, 2)}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2))
    rows = []; runs = []; failures = []; start = time.monotonic()
    old = pd.read_csv(PRIOR/'outer_predictions.csv')
    old = old[old.method == 'extra_trees_matched']
    for fold, split in enumerate(original['folds']):
        train = cell_indices(data, split['train_cells'])
        valid = cell_indices(data, split['validation_cells'])
        if set(data.cell[train]) & set(data.cell[valid]):
            raise ValueError('Cell overlap')
        sx, sr, scaler = fit_transform(data, train)
        z = matched(sx, sr, data.log_ratio)
        _, first, inv = np.unique(data.cell[valid], return_index=True, return_inverse=True)
        r0 = sr[valid][first]
        anchor = matched(r0, r0, np.zeros(len(first), dtype=np.float32))
        np.savez(out/f'fold{fold}_context.npz', x=z[train], log_soh=np.log(data.soh[train]),
                 source_rows=data.source_row[train], cell=data.cell[train], **scaler)
        for seed in (0, 1, 2):
            tick = time.monotonic(); model = None
            predictions = {}
            artifact = PRIOR / f'extra_trees_matched-f{fold}-s{seed}.joblib'
            base = joblib.load(artifact)  # trusted artifact produced in this project
            log_et = base['mu'] + base['scale'] * base['model'].predict(z[valid])
            log_et_ref = base['mu'] + base['scale'] * base['model'].predict(anchor)
            predictions['extra_trees_matched'] = positive_exp(log_et)
            predictions['extra_trees_anchored'] = positive_exp(log_et-log_et_ref[inv])
            earlier = old[(old.fold == fold) & (old.seed == seed)].set_index('source_row')
            if not np.allclose(predictions['extra_trees_matched'],
                    earlier.loc[data.source_row[valid], 'pred_soh'].to_numpy(),
                    atol=1e-10, rtol=1e-10):
                raise ValueError('Existing ET predictions did not reproduce')
            run = {'fold': fold, 'seed': seed, 'stage': 'context_fit_and_predict'}
            try:
                model = estimator(seed)
                model.fit(z[train], np.log(data.soh[train]))
                check = query_isolation(model, z[valid])
                log_pred = np.asarray(model.predict(z[valid]), dtype=float)
                log_ref = np.asarray(model.predict(anchor), dtype=float)
                predictions['tabicl'] = positive_exp(log_pred)
                predictions['tabicl_anchored'] = positive_exp(log_pred-log_ref[inv])
                predictions['tabicl_et_equal'] = positive_exp(.5*(log_pred+log_et))
                run.update(status='ok', query_isolation=check,
                           context_rows=len(train), evaluation_rows=len(valid))
            except Exception as error:
                run.update(status='failed', error=repr(error)); failures.append(dict(run))
            finally:
                if model is not None:
                    del model
                gc.collect(); torch.mps.empty_cache()
            for method, pred in predictions.items():
                if len(pred) != len(valid):
                    raise ValueError('Prediction row count mismatch')
                for idx, value in zip(valid, pred):
                    rows.append({'method': method, 'fold': fold, 'seed': seed,
                        'source_row': int(data.source_row[idx]), 'cell': str(data.cell[idx]),
                        'batch': str(data.batch[idx]), 'true_soh': float(data.soh[idx]),
                        'pred_soh': float(value)})
            run['seconds'] = time.monotonic()-tick; runs.append(run)
            print(json.dumps(run), flush=True)
            (out/'runs.json').write_text(json.dumps(runs, indent=2))
            pd.DataFrame(rows).to_csv(out/'outer_predictions.csv', index=False)
    summaries, incomplete = summarize_predictions(rows, data, methods=METHODS)
    # Preserve all candidate outcomes, then apply the preregistered development selection.
    priority = {name: index for index, name in enumerate(METHODS)}
    best = min((s['geometric_ensemble']['cell_mae_pp'] for s in summaries), default=float('inf'))
    near = [s for s in summaries if s['geometric_ensemble']['cell_mae_pp'] <= best+1e-6]
    selected = min(near, key=lambda s: priority[s['method']])['method'] if near else None
    report = {'scope': manifest['scope'], 'seconds': time.monotonic()-start,
        'methods': summaries, 'selected_development_recipe': selected,
        'paired_cell_bootstrap': paired_bootstrap(summaries), 'failed_runs': failures,
        'incomplete_candidates': incomplete, 'context_fits_attempted': len(runs),
        'holdout_model_scores': False}
    (out/'summary.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'stage': 'done', 'selected': selected, 'failures': len(failures),
                      'seconds': report['seconds']}), flush=True)
    return 0 if not failures else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--out', default=str(OUT))
    raise SystemExit(main(parser.parse_args()))

"""One-time, acceptance-gated final XJTU and secondary NASA evaluation."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from model_lab.modeling.frozen_hybrid_streaming import FrozenStreamingHybrid
from model_lab.modeling.frozen_et import outside_training_range
from model_lab.scripts.train_nested_cv import ROOT, VIEW, cell_metrics, digest

PACKAGE = ROOT/'reports/round3/champion_hybrid_v2_streaming'
PROTOCOL = ROOT/'docs/FINAL_EVALUATION_PROTOCOL.md'
ACCEPTANCE = ROOT/'reports/round3/final_review_receipt.json'
NASA = ROOT/'reports/round3/nasa_audit'
OUT = ROOT/'reports/round3/final_evaluation'


def review_gate(receipt: dict, hashes: dict) -> None:
    if receipt.get('status') != 'passed' or not receipt.get('independent_reviewer'):
        raise ValueError('Independent review acceptance is required')
    for key, value in hashes.items():
        if receipt.get(key) != value:
            raise ValueError(f'Stale or missing review binding: {key}')


def metrics(truth, predicted, cells):
    result = cell_metrics(truth, predicted, cells)
    error = (predicted-truth)*100.
    result.update(pooled_mae_pp=float(np.abs(error).mean()),
                  pooled_rmse_pp=float(np.sqrt(np.square(error).mean())),
                  prediction_range_soh=[float(predicted.min()), float(predicted.max())],
                  truth_range_soh=[float(truth.min()), float(truth.max())])
    return result


def main() -> None:
    if OUT.exists():
        raise FileExistsError('Preserve the one-time final evaluation directory')
    bindings = {'package_manifest_sha256': digest(PACKAGE/'manifest.json'),
                'final_protocol_sha256': digest(PROTOCOL),
                'evaluator_sha256': digest(Path(__file__))}
    receipt=json.loads(ACCEPTANCE.read_text())
    review_gate(receipt, bindings)
    isolation_path=ROOT/'reports/round3/frozen_streaming_query_isolation.json'
    isolation=json.loads(isolation_path.read_text())
    if isolation['status']!='passed' or isolation['package_manifest_sha256']!=bindings['package_manifest_sha256']:
        raise ValueError('Frozen-path isolation proof missing or stale')
    if receipt.get('isolation_sha256')!=digest(isolation_path):
        raise ValueError('Independent review did not bind this isolation proof')
    package_manifest = json.loads((PACKAGE/'manifest.json').read_text())
    if package_manifest['provenance_sha256']['view'] != digest(VIEW):
        raise ValueError('Frozen XJTU data changed')
    if package_manifest['provenance_sha256']['feature_map'] != digest(ROOT/'data/physical_curve_features.py'):
        raise ValueError('Frozen feature map changed')
    audit = json.loads((NASA/'summary.json').read_text())
    prior_transfer = json.loads((ROOT/'reports/round3/nasa_transfer/summary.json').read_text())
    if not audit['external_scoring_gate_candidate'] or audit['failed_cells']:
        raise ValueError('NASA audit gate not passed')
    if audit['parser_sha256'] != digest(ROOT/'data/nasa_pcoe.py'):
        raise ValueError('NASA parser changed after audit')
    if prior_transfer['audit_view_sha256'] != digest(NASA/'view.npz'):
        raise ValueError('NASA audited view changed')
    model = FrozenStreamingHybrid(PACKAGE, device='mps')
    # Deliberately do not read the truth arrays during feature loading/prediction.
    with np.load(VIEW, allow_pickle=False) as source:
        indices = np.flatnonzero(source['holdout'])
        x = source['x'][indices]; r = source['reference'][indices]
        q = source['log_window_ratio'][indices]; cells = source['cell'][indices].astype(str)
    if sorted(set(cells)) != package_manifest['heldout_cell_ids']:
        raise ValueError('Final test population changed')
    with np.load(NASA/'view.npz', allow_pickle=False) as source:
        nx = source['x']; nr = source['reference']; nq = source['log_window_ratio']
        ncells = source['cell'].astype(str)
    if len(nx) != audit['scored_candidate_rows']:
        raise ValueError('NASA scoring population changed')
    OUT.mkdir(parents=True)
    manifest = {'created_at_utc': datetime.now(timezone.utc).isoformat(), **bindings,
        'scope': 'frozen XJTU heldout test plus previously exposed NASA source stress test',
        'selected_recipe': 'tabicl_et_equal', 'device': 'mps', 'query_chunk_rows': 256,
        'primary_cells': sorted(set(cells)), 'primary_rows': len(x),
        'secondary_cells': sorted(set(ncells)), 'secondary_rows': len(nx),
        'xjtu_view_sha256': digest(VIEW), 'nasa_view_sha256': digest(NASA/'view.npz'),
        'review_receipt_sha256': digest(ACCEPTANCE), 'fit_query_labels': False,
        'prediction_truth_order': 'save predictions before opening truth arrays',
        'predeclared_components': ['soh','extra_trees_soh','tabicl_soh']}
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2))
    started = time.monotonic()
    predictions = model.predict_components(np.r_[x,nx], np.r_[r,nr], np.r_[q,nq],
        progress=lambda s:print(json.dumps(s),flush=True))
    np.savez(OUT/'predictions_before_truth.npz', **predictions,
             source=np.array(['xjtu']*len(x)+['nasa']*len(nx)), cell=np.r_[cells,ncells])
    pred_hash = digest(OUT/'predictions_before_truth.npz')
    (OUT/'prediction_receipt.json').write_text(json.dumps({
        'saved_at_utc': datetime.now(timezone.utc).isoformat(),
        'predictions_sha256': pred_hash, 'truth_arrays_opened_yet': False}, indent=2))
    with np.load(VIEW, allow_pickle=False) as source:
        truth = source['soh'][indices].astype(float)
    with np.load(NASA/'view.npz', allow_pickle=False) as source:
        ntruth = source['true_soh'].astype(float)
    if not np.isfinite(np.r_[truth,ntruth]).all() or np.any(np.r_[truth,ntruth] <= 0):
        raise ValueError('Invalid test truth; saved predictions remain preserved')
    old = pd.read_csv(ROOT/'reports/round3/nasa_transfer/predictions.csv').sort_values('view_row')
    nasa_et_delta = float(np.max(np.abs(predictions['extra_trees_soh'][len(x):]-old.pred_soh.to_numpy())))
    if not np.allclose(predictions['extra_trees_soh'][len(x):], old.pred_soh.to_numpy(), atol=1e-10, rtol=1e-10):
        raise ValueError('NASA frozen ET predictions did not reproduce')
    scores = {}; rows = []
    for name, y, cs, sl, source_rows in (
        ('xjtu_holdout', truth, cells, slice(0,len(x)), indices),
        ('nasa_secondary_transfer', ntruth, ncells, slice(len(x),None), np.arange(len(nx)))):
        scores[name] = {'cells': len(set(cs)), 'rows': len(y), 'components': {}}
        for component, values in predictions.items():
            pred = values[sl]
            scores[name]['components'][component] = metrics(y,pred,cs)
            for i, cell, actual, estimate in zip(source_rows, cs, y, pred):
                rows.append({'population': name, 'component': component, 'source_row': int(i),
                    'cell': str(cell), 'true_soh': float(actual), 'pred_soh': float(estimate),
                    'abs_error_pp': float(abs(actual-estimate)*100)})
    report = {'scope': manifest['scope'], 'selected_recipe_unchanged': 'tabicl_et_equal',
        'seconds': time.monotonic()-started, 'device': 'mps', 'scores': scores,
        'predictions_before_truth_sha256': pred_hash, 'nasa_et_reload_max_abs_delta': nasa_et_delta,
        'input_shift': {'xjtu_holdout': outside_training_range(x,r,q,model.et),
                        'nasa_secondary_transfer': outside_training_range(nx,nr,nq,model.et)},
        'limitations': ['only three independent XJTU final cells',
            'development architecture selection repeatedly adapted on 21 cells',
            'NASA ET errors were already known before this secondary comparison',
            'XJTU RPT and NASA operational discharge are different tasks',
            'no exact published-benchmark SOTA comparison', 'no guarantee of zero overfitting'],
        'retuning_after_test': False}
    pd.DataFrame(rows).to_csv(OUT/'predictions.csv', index=False)
    (OUT/'summary.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k != 'input_shift'},indent=2),flush=True)


if __name__ == '__main__':
    main()

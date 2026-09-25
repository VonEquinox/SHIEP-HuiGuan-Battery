"""Audit actual frozen inference batches using development/NASA inputs only.

Instrument the publisher predict call locally, without changing package/model
files or its returned values. Probe singleton, 32-row subdivision, reversal,
other-query perturbations, and repeated calls for each real 256-row chunk.
No heldout XJTU features are read; query targets are never consulted by the
checks. The frozen development context necessarily retains its training labels.
"""
from __future__ import annotations

import gc
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from model_lab.modeling.frozen_hybrid import FrozenHybrid
from model_lab.scripts.train_nested_cv import ROOT, VIEW, digest, load_development

OUT = ROOT/'reports/round3/frozen_query_isolation.json'
PACKAGE = ROOT/'reports/round3/champion_hybrid_v1'
TOLERANCE = 1e-4


def main():
    if OUT.exists():
        raise FileExistsError('Preserve the previous frozen-path isolation check')
    data, _ = load_development(VIEW)
    with np.load(ROOT/'reports/round3/nasa_audit/view.npz', allow_pickle=False) as source:
        nx = source['x'][:260]; nr = source['reference'][:260]
        nq = source['log_window_ratio'][:260]
    # Alternate populations within batches and cross two 256-row boundaries.
    x = np.stack([data.x[:260], nx], axis=1).reshape(-1,71)
    r = np.stack([data.reference[:260], nr], axis=1).reshape(-1,71)
    q = np.stack([data.log_ratio[:260], nq], axis=1).reshape(-1)
    model = FrozenHybrid(PACKAGE, 'mps')
    from tabicl import TabICLRegressor
    original_predict = TabICLRegressor.predict
    checks = []
    started = time.monotonic()

    def instrumented_predict(self, query, *args, **kwargs):
        a = np.asarray(query).copy()
        baseline = np.asarray(original_predict(self,a,*args,**kwargs),dtype=float)
        selected = sorted(set([0, min(31,len(a)-1), len(a)//2, len(a)-1]))
        alone = np.array([float(original_predict(self,a[j:j+1],*args,**kwargs)[0]) for j in selected])
        subdivision = np.concatenate([np.asarray(original_predict(self,a[j:j+32],*args,**kwargs),dtype=float)
                                      for j in range(0,len(a),32)])
        reversed_prediction = np.asarray(original_predict(self,a[::-1].copy(),*args,**kwargs),dtype=float)[::-1]
        changed = a*7. + 13.
        changed[selected] = a[selected]
        altered = np.asarray(original_predict(self,changed,*args,**kwargs),dtype=float)
        repeated = np.asarray(original_predict(self,a,*args,**kwargs),dtype=float)
        deltas = {'singleton': float(np.max(np.abs(alone-baseline[selected]))),
                  'subdivision_32': float(np.max(np.abs(subdivision-baseline))),
                  'reverse_order': float(np.max(np.abs(reversed_prediction-baseline))),
                  'other_rows_perturbed': float(np.max(np.abs(altered[selected]-baseline[selected]))),
                  'repeated_after_other_calls': float(np.max(np.abs(repeated-baseline)))}
        result = {'seed': self.random_state, 'batch_rows': len(a), 'probe_indices': selected,
                  'max_log_deltas': deltas, 'passed': all(np.isfinite(v) and v<=TOLERANCE for v in deltas.values())}
        checks.append(result)
        print(json.dumps(result),flush=True)
        if not result['passed']:
            raise RuntimeError('Frozen-path query-isolation test failed')
        return baseline

    report = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'runtime isolation check on actual frozen interface; no XJTU heldout input or query-target comparison',
        'package_manifest_sha256': digest(PACKAGE/'manifest.json'),
        'script_sha256': digest(Path(__file__)),
        'inference_sha256': digest(ROOT/'modeling/frozen_hybrid.py'),
        'rows': len(x), 'mixed_populations': ['XJTU development','previously audited NASA'],
        'chunk_rows': 256, 'tolerance_log_soh': TOLERANCE,
        'instrumentation': 'additional calls to unmodified publisher predict; original baseline returned',
        'heldout_model_scores': False, 'query_labels_used': False}
    try:
        TabICLRegressor.predict = instrumented_predict
        components = model.predict_components(x,r,q,chunk_rows=256)
        if len(checks) != 9 or {c['seed'] for c in checks}!={0,1,2}:
            raise RuntimeError('Did not exercise every frozen seed and chunk')
        report.update(status='passed', output_shapes={key:list(value.shape) for key,value in components.items()})
    except Exception as error:
        report.update(status='failed', error=repr(error))
        raise
    finally:
        TabICLRegressor.predict = original_predict
        gc.collect()
        report.update(checks=checks, seconds=time.monotonic()-started)
        OUT.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2),flush=True)


if __name__ == '__main__':
    main()

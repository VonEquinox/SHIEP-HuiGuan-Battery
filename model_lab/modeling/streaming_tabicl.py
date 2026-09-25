"""Serial cache evaluation of the pinned publisher TabICLv2 algorithm.

Uses the same encoder, ensemble views, cache construction, forward method and
target inverse transform as tabicl 2.2.0. Only cache lifetime changes: one view
is retained instead of concatenating all eight training caches on the device.
Private publisher helpers are version-pinned and require numerical validation.
"""
from __future__ import annotations

import gc
import importlib.metadata
import time

import numpy as np
import torch


def bound_manager_batches(estimator):
    """Cap independent feature/row batch axes, not sequence or context length.

    The native manager accepts max_bs but its caller otherwise uses 50000.
    Its hardware estimate can overestimate MPS capacity; cap without truncating
    any feature, observation, context label, attention sequence or model view.
    """
    def cap_one(manager, cap):
        if getattr(manager,'_battery_max_bs',None)==cap:
            return
        original=manager.estimate_safe_batch_size
        def bounded(seq_len,include_inputs=True,in_dim=None,max_bs=50000):
            return original(seq_len,include_inputs=include_inputs,in_dim=in_dim,max_bs=min(max_bs,cap))
        manager.estimate_safe_batch_size=bounded
        manager._battery_max_bs=cap
    for component,cap in ((estimator.model_.col_embedder,16),
                          (estimator.model_.row_interactor,64),
                          (estimator.model_.icl_predictor,1)):
        cap_one(component.inference_mgr,cap)


def streaming_predict(estimator, query: np.ndarray, chunk_rows: int = 256,
                      verify_isolation: bool = False, progress=None):
    if importlib.metadata.version('tabicl') != '2.2.0':
        raise ValueError('Streaming adapter requires exactly tabicl 2.2.0')
    if not 1 <= chunk_rows <= 512:
        raise ValueError('Invalid query chunk size')
    if estimator.model_kv_cache_ is not None:
        raise ValueError('Fit with kv_cache=False to avoid retaining all-view caches')
    bound_manager_batches(estimator)
    query = np.asarray(query, dtype=np.float32)
    if query.ndim != 2 or query.shape[1] != estimator.n_features_in_ or not np.isfinite(query).all():
        raise ValueError('Finite, schema-matched query matrix required')
    encoded = estimator.X_encoder_.transform(query)
    train = estimator.ensemble_generator_.transform(X=None, mode='train')
    test = estimator.ensemble_generator_.transform(encoded, mode='test')
    results = []; checks = []
    if verify_isolation:
        probes=sorted(set([0,min(31,len(query)-1),len(query)//2,len(query)-1]))
        raw_changed=query.copy()*7.+13.;raw_changed[probes]=query[probes]
        variants={
            'first32':(query[:32],slice(0,min(32,len(query)))),
            'reverse':(query[::-1].copy(),None),
            'other_rows_perturbed':(raw_changed,probes)}
        for label,(raw,index) in variants.items():
            mapped=estimator.ensemble_generator_.transform(estimator.X_encoder_.transform(raw),mode='test')
            for norm,(base,) in test.items():
                (other,)=mapped[norm]
                if label=='reverse':left,right=other[:,::-1],base
                elif label=='first32':left,right=other,base[:,index]
                else:left,right=other[:,index],base[:,index]
                delta=float(np.max(np.abs(left-right)))
                ok=bool(np.allclose(left,right,atol=1e-6,rtol=1e-6))
                checks.append({'stage':'preprocessing','seed':estimator.random_state,
                    'norm':norm,'variant':label,'max_feature_difference':delta,'passed':ok})
                if not ok:raise RuntimeError('Query-dependent preprocessing detected')
    for norm, (xs, ys) in train.items():
        (queries,) = test[norm]
        if len(xs) != len(queries):
            raise ValueError('Publisher view alignment changed')
        for view in range(len(xs)):
            start = time.monotonic(); cache = None
            if progress:
                progress({'stage':'cache_start','seed':estimator.random_state,'norm':norm,'view':view})
            tx = torch.from_numpy(xs[view:view+1]).float().to(estimator.device_)
            ty = torch.from_numpy(ys[view:view+1]).float().to(estimator.device_)
            try:
                with torch.no_grad():
                    estimator.model_.predict_stats_with_cache(
                        X_train=tx,y_train=ty,use_cache=False,store_cache=True,
                        cache_mode='repr',inference_config=estimator.inference_config_)
                cache = estimator.model_._cache
                estimator.model_.clear_cache()
                def forward(a):
                    return np.asarray(estimator._batch_forward_with_cache(a,cache,output_type=['mean']))
                parts = []
                for begin in range(0,len(query),chunk_rows):
                    a = queries[view:view+1,begin:begin+chunk_rows]
                    baseline = forward(a)
                    parts.append(baseline)
                    if verify_isolation:
                        n = a.shape[1]
                        selected = sorted(set([0,min(31,n-1),n//2,n-1]))
                        alone = np.concatenate([forward(a[:,j:j+1]) for j in selected],axis=1)
                        # The first 32 positions check a different actual batch size.
                        small = forward(a[:,:min(32,n)])
                        reverse = forward(a[:,::-1].copy())[:,::-1]
                        changed = a.copy()*7.+13.; changed[:,selected]=a[:,selected]
                        altered = forward(changed)
                        repeated = forward(a)
                        # Convert scaled deviations to the original log-SOH units.
                        scale = float(estimator.y_scaler_.scale_[0])
                        ds = {'singleton': float(np.max(np.abs(alone-baseline[:,selected])))*scale,
                              'first32': float(np.max(np.abs(small-baseline[:,:min(32,n)])))*scale,
                              'reverse': float(np.max(np.abs(reverse-baseline)))*scale,
                              'other_rows_perturbed': float(np.max(np.abs(altered[:,selected]-baseline[:,selected])))*scale,
                              'repeated': float(np.max(np.abs(repeated-baseline)))*scale}
                        check = {'stage':'prediction','seed':estimator.random_state,'norm':norm,'view':view,
                                 'start_row':begin,'rows':n,'deltas_log_soh':ds,
                                 'passed':all(np.isfinite(v) and v<=1e-4 for v in ds.values())}
                        checks.append(check)
                        if not check['passed']:
                            raise RuntimeError(f'Query isolation failed: {check}')
                results.append(np.concatenate(parts,axis=1))
            finally:
                estimator.model_.clear_cache()
                # Closures and local GPU tensors must not retain previous-view memory.
                if 'forward' in locals():
                    del forward
                del cache,tx,ty
                gc.collect()
                if str(estimator.device_) == 'mps':
                    torch.mps.empty_cache()
            if progress:
                progress({'stage':'view_done','seed':estimator.random_state,'norm':norm,
                          'view':view,'seconds':time.monotonic()-start})
    array = np.concatenate(results,axis=0)
    if array.shape != (estimator.n_estimators,len(query)):
        raise ValueError('Unexpected publisher ensemble shape')
    values = estimator.y_scaler_.inverse_transform(array.reshape(-1,1)).reshape(array.shape)
    prediction = np.mean(values,axis=0)
    if not np.isfinite(prediction).all():
        raise ValueError('Nonfinite streamed output')
    return prediction,checks

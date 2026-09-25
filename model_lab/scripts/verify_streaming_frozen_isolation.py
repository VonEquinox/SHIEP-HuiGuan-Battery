"""Exercise the actual frozen serial-cache interface before any final score."""
from __future__ import annotations
import json,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from model_lab.scripts.train_nested_cv import ROOT,VIEW,digest,load_development
from model_lab.modeling.frozen_hybrid_streaming import FrozenStreamingHybrid


def main():
    out=ROOT/'reports/round3/frozen_streaming_query_isolation.json'
    package=ROOT/'reports/round3/champion_hybrid_v2_streaming'
    if out.exists():raise FileExistsError('Preserve prior isolation results')
    data,_=load_development(VIEW)
    with np.load(ROOT/'reports/round3/nasa_audit/view.npz',allow_pickle=False) as src:
        nx,nr,nq=src['x'][:260],src['reference'][:260],src['log_window_ratio'][:260]
    x=np.stack((data.x[:260],nx),axis=1).reshape(-1,71)
    r=np.stack((data.reference[:260],nr),axis=1).reshape(-1,71)
    q=np.stack((data.log_ratio[:260],nq),axis=1).reshape(-1)
    model=FrozenStreamingHybrid(package,'mps')
    report={'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'actual frozen full-development context; interleaved dev/NASA inputs only; no query-target comparison',
        'package_manifest_sha256':digest(package/'manifest.json'),
        'script_sha256':digest(Path(__file__)),
        'adapter_sha256':digest(ROOT/'modeling/streaming_tabicl.py'),
        'streaming_inference_sha256':digest(ROOT/'modeling/frozen_hybrid_streaming.py'),
        'rows':520,'train_context_rows':2058,'chunk_rows':256,
        'heldout_inputs_used':False,'query_labels_used':False,'tolerance_log_soh':1e-4}
    started=time.monotonic()
    try:
        output=model.predict_components(x,r,q,chunk_rows=256,verify_isolation=True,
            progress=lambda s:print(json.dumps(s),flush=True))
        checks=model.last_isolation_checks
        if len(checks)!=90 or not all(s['passed'] for s in checks):
            raise RuntimeError('Not all declared isolation checks passed')
        report.update(status='passed',checks=checks,
            prediction_checks=sum(s['stage']=='prediction' for s in checks),
            preprocessing_checks=sum(s['stage']=='preprocessing' for s in checks),
            max_log_difference=max(v for c in checks if c['stage']=='prediction' for v in c['deltas_log_soh'].values()),
            max_preprocessing_difference=max(c['max_feature_difference'] for c in checks if c['stage']=='preprocessing'),
            output_shapes={k:list(v.shape) for k,v in output.items()})
    except BaseException as exc:
        report.update(status='failed_or_interrupted',error=repr(exc))
        raise
    finally:
        report['seconds']=time.monotonic()-started
        out.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2),flush=True)


if __name__=='__main__':main()

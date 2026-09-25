"""Recover absolute temperature and diagnose Coulomb-audit exceptions.
No target edits or target-dependent row exclusions are made.
"""
from __future__ import annotations
import argparse,json,hashlib,time
from pathlib import Path
import numpy as np
from scipy.io import loadmat
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from model_lab.data.xjtu_raw import build_cc_window


def main(args):
    start=time.monotonic()
    bundle=Path(args.bundle)
    meta=json.loads(bundle.with_suffix('.json').read_text())
    by_cell={}
    for row in meta['rows']:by_cell.setdefault(row['cell'],[]).append(row)
    env=np.full((len(meta['rows']),2),np.nan,dtype=np.float32)
    refenv=np.full_like(env,np.nan);checks=[]
    for k,(cell,rows) in enumerate(by_cell.items(),1):
        p=Path(rows[0]['source_path'])
        h=hashlib.sha256(p.read_bytes()).hexdigest()
        if h!=rows[0]['source_sha256']:raise RuntimeError('source changed')
        data=loadmat(p,simplify_cells=True);cycles=data['data'];summary=data['summary']
        ref=int(rows[0]['reference_cycle_index'])
        observations={}
        for cycle_id in sorted({ref}|{int(r['cycle_index']) for r in rows}):
            cycle=cycles[cycle_id-1]
            t=np.asarray(cycle['relative_time_min'],dtype=float).reshape(-1)
            v=np.asarray(cycle['voltage_V'],dtype=float).reshape(-1)
            i=np.asarray(cycle['current_A'],dtype=float).reshape(-1)
            temp=np.asarray(cycle['temperature_C'],dtype=float).reshape(-1)
            # Reuse the exact selected segment and real lower-boundary bracket.
            window=build_cc_window(cycle)
            if not window.valid:raise RuntimeError('previously valid window no longer reproduces')
            j=int(window.source_start_index)
            f=(3.7-v[j])/(v[j+1]-v[j]) if v[j+1]>v[j] else 0.0
            if not -1e-6<=f<=1+1e-6:raise RuntimeError('lower boundary bracket mismatch')
            t0=float(temp[j]+f*(temp[j+1]-temp[j]));i0=float(i[j]+f*(i[j+1]-i[j]))
            observations[cycle_id]=[t0,i0]
            # Label audit is separate and NEVER used for exclusion/features.
            dt=np.diff(t);valid=(dt>0)&np.isfinite(dt)&(i[:-1]<-.05)&(i[1:]<-.05)&np.isfinite(i[:-1])&np.isfinite(i[1:])
            integrated=float(np.sum(-(i[1:][valid]+i[:-1][valid])*.5*dt[valid]/60))
            q=float(np.asarray(summary['discharge_capacity_Ah']).reshape(-1)[cycle_id-1])
            checks.append({'cell':cell,'cycle':cycle_id,'summary_Ah':q,'integrated_all_negative_segments_Ah':integrated,'relative_difference':abs(integrated-q)/q if q>0 else None})
        for row in rows:
            ix=int(row['row']);env[ix]=observations[int(row['cycle_index'])];refenv[ix]=observations[ref]
        print(f'{k}/{len(by_cell)} environment and label audit: {cell}',flush=True)
    output=Path(args.out);output.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(output,current_environment=env,reference_environment=refenv)
    finite=[c['relative_difference'] for c in checks if c['relative_difference'] is not None]
    report={'bundle_sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),'environment_fields':['absolute_temperature_at_lower_boundary_C','current_at_lower_boundary_A'],'rows':len(env),'cells':len(by_cell),'label_audit_quantiles':np.quantile(finite,[0,.5,.95,.99,1]).tolist(),'audit_above_1_percent':[c for c in checks if c.get('relative_difference',0) is not None and c['relative_difference']>.01],'label_changes':0,'excluded_rows':0,'seconds':time.monotonic()-start,'checks':checks}
    output.with_suffix('.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',default='model_lab/data/derived/xjtu_verified/bundle.npz');p.add_argument('--out',default='model_lab/data/derived/xjtu_verified/environment.npz');main(p.parse_args())

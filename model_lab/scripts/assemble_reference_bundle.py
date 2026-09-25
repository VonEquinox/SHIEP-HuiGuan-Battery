"""Join audited numeric windows and measured labels by physical cell/cycle keys."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import numpy as np


def main(a):
    root=Path(a.project_root)
    audit=json.loads(Path(a.audit).read_text())
    xx=[];rr=[];lq=[];yy=[];cells=[];protocol=[];held=[];rows=[];skipped=[];label_checks=[]
    for source in audit['raw_results']:
        rowpath=root/source['output_rows']
        metadata=json.loads(rowpath.read_text())
        if not source.get('output_npz'):
            skipped.append({'cell':source['cell_id'],'reason':'no_valid_input_window'});continue
        path=root/source['output_npz']
        with np.load(path,allow_pickle=False) as raw:
            by_cycle={int(k):j for j,k in enumerate(raw['original_cycle_index'])}
            channels=np.stack([raw['elapsed_min'],raw['incremental_charge_Ah'],raw['current_A'],raw['temperature_rel_C']],axis=2)
            vectors=np.concatenate([channels.reshape(len(channels),-1),np.isfinite(channels).reshape(len(channels),-1)],axis=1).astype(np.float32)
            q=raw['window_charge_Ah'].astype(float)
        added=0
        for row in metadata:
            if not row.get('is_scored_primary'):continue
            k=int(row['cycle_index']);ref=int(row['reference_cycle_index'])
            if not ref<k or k not in by_cycle or ref not in by_cycle:raise ValueError('invalid reference time/index')
            j,refj=by_cycle[k],by_cycle[ref]
            target=float(row['target_discharge_capacity_Ah'])/float(row['reference_capacity_Ah'])
            if not np.isfinite(target) or target<=0 or min(q[j],q[refj])<=0:raise ValueError('invalid label/observed charge')
            xx.append(vectors[j]);rr.append(vectors[refj]);lq.append(np.log(q[j]/q[refj]));yy.append(target)
            cells.append(source['cell_id']);protocol.append(source['batch']);held.append(source['assignment']=='holdout')
            rows.append({'row':len(yy)-1,'cell':source['cell_id'],'batch':source['batch'],'cycle_index':k,'reference_cycle_index':ref,'source_sha256':source['source_sha256'],'source_path':source['source_path'],'cutoff_source_index':row.get('source_end_index'),'label_provenance':row['label_provenance'],'label_rule':'measured diagnostic discharge / first usable diagnostic discharge','assignment':source['assignment']})
            check=row.get('discharge_audit',{});label_checks.append({'row':len(yy)-1,'cell':source['cell_id'],**check})
            added+=1
        if not added:skipped.append({'cell':source['cell_id'],'reason':'no_longitudinal_diagnostic_with_usable_reference'})
    if not yy:raise RuntimeError('no eligible measured-label samples')
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out,x=np.stack(xx),reference=np.stack(rr),log_window_ratio=np.array(lq,dtype=np.float32),soh=np.array(yy,dtype=np.float64),cell=np.array(cells),protocol=np.array(protocol),holdout=np.array(held,dtype=bool))
    manifest={'scope':'XJTU measured RPT partial-CC charging, initial-calibration required','features':'64 voltage-grid points of observed elapsed minutes, incremental charge Ah, current A, relative temperature C, and 4 finite masks; no capacity/age/cell ID features','voltage_window_V':[3.7,4.1],'row_count':len(yy),'scored_cell_count':len(set(cells)),'development_cells':len({c for c,h in zip(cells,held) if not h}),'heldout_cells':sorted({c for c,h in zip(cells,held) if h}),'skipped_cells':skipped,'audit_sha256':hashlib.sha256(Path(a.audit).read_bytes()).hexdigest(),'bundle_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'rows':rows,'label_integral_checks':label_checks}
    out.with_suffix('.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('rows','label_integral_checks','skipped_cells')},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project-root',default='model_lab');p.add_argument('--audit',default='model_lab/reports/round2/raw_verified/raw_audit.json');p.add_argument('--out',default='model_lab/data/derived/xjtu_verified/bundle.npz');main(p.parse_args())

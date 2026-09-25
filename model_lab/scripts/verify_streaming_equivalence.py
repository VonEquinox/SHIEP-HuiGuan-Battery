"""Verify streamed publisher operations against saved pre-freeze CV predictions."""
from __future__ import annotations
import json,time
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from model_lab.scripts.evaluate_tabicl import offline_environment,estimator
from model_lab.scripts.train_nested_cv import ROOT,VIEW,FOLDS,load_development,cell_indices,fit_transform,matched,digest
from model_lab.modeling.streaming_tabicl import streaming_predict


def main():
    out=ROOT/'reports/round3/streaming_equivalence.json'
    if out.exists():raise FileExistsError('Preserve existing numerical verification')
    offline_environment();torch.set_num_threads(4)
    data,_=load_development(VIEW);fold=json.loads(FOLDS.read_text())['folds'][0]
    tr=cell_indices(data,fold['train_cells']);va=cell_indices(data,fold['validation_cells'])
    sx,sr,_=fit_transform(data,tr);z=matched(sx,sr,data.log_ratio)
    prior=estimator(0);prior.set_params(kv_cache=False)
    start=time.monotonic();prior.fit(z[tr],np.log(data.soh[tr]))
    pred,checks=streaming_predict(prior,z[va],chunk_rows=256,verify_isolation=False,
        progress=lambda v: print(json.dumps(v),flush=True))
    old=pd.read_csv(ROOT/'reports/round3/tabicl_followup/outer_predictions.csv')
    old=old[(old.method=='tabicl')&(old.fold==0)&(old.seed==0)].set_index('source_row')
    expected=old.loc[data.source_row[va],'pred_soh'].to_numpy()
    delta=float(np.max(np.abs(pred-np.log(expected))))
    report={'status':'passed' if delta<=1e-4 else 'failed',
        'scope':'same published weights, same fold0 seed0 context, all675 saved development queries',
        'rows':len(va),'max_abs_log_prediction_difference':delta,'tolerance_log_soh':1e-4,
        'streaming_code_sha256':digest(ROOT/'modeling/streaming_tabicl.py'),
        'source_predictions_sha256':digest(ROOT/'reports/round3/tabicl_followup/outer_predictions.csv'),
        'seconds':time.monotonic()-start,'model_or_target_refitting_change':False,
        'heldout_model_scores':False,'resource_policy':'MPS high/low watermarks0.7/0.5; oneview cache only'}
    out.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
    if report['status']!='passed':raise RuntimeError('Streamed implementation not numerically verified')


if __name__=='__main__':main()

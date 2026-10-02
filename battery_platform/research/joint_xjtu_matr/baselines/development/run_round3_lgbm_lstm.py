import json, hashlib, random, time, os
from pathlib import Path
import numpy as np
import torch
from sklearn.metrics import mean_absolute_error, mean_squared_error
from lightgbm import LGBMRegressor, early_stopping
from model_lab.scripts.train_nested_cv import load_development, split_indices, fit_transform, matched, weights, cell_metrics

ROOT=Path('/Users/vonequinox/Program/GithubProjects/SHIEP-HuiGuan-Battery')
VIEW=ROOT/'model_lab/reports/round2/cv_physical/view_bundle.npz'
FOLDS=ROOT/'model_lab/reports/round2/cv_physical/preregistration.json'
OUT=Path('/tmp/xjtu_baselines_20261002.json')
SEEDS=(0,1,2)

class LSTMReg(torch.nn.Module):
  def __init__(self, hidden=64):
    super().__init__(); self.lstm=torch.nn.LSTM(3,hidden,batch_first=True); self.head=torch.nn.Sequential(torch.nn.Linear(hidden+1,64),torch.nn.ReLU(),torch.nn.Linear(64,1))
  def forward(self,x,r,q):
    # Matched view: sequence channels current/reference/difference; q is scalar context.
    seq=torch.stack((x,r,x-r),dim=-1)
    h,_=self.lstm(seq); return self.head(torch.cat((h[:,-1,:],q[:,None]),dim=1))[:,0]

def fit_lstm(sx,sr,q,y,cell,train,valid,seed,max_epochs=300,patience=60, fixed_epochs=None):
  random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
  device=torch.device('cpu'); model=LSTMReg().to(device)
  tx=torch.tensor(sx[train],dtype=torch.float32); tr=torch.tensor(sr[train],dtype=torch.float32); tq=torch.tensor(q[train],dtype=torch.float32); ty=torch.tensor(np.log(y[train]),dtype=torch.float32); tw=torch.tensor(weights(cell[train]),dtype=torch.float32)
  opt=torch.optim.AdamW(model.parameters(),lr=0.001,weight_decay=0.001)
  mu=float(ty.mean()); scale=max(float(ty.std()),.02)
  best=float('inf'); best_state=None; best_ep=0; bad=0
  limit=fixed_epochs or max_epochs
  def pred(ix):
    model.eval();
    with torch.no_grad(): out=model(torch.tensor(sx[ix],dtype=torch.float32),torch.tensor(sr[ix],dtype=torch.float32),torch.tensor(q[ix],dtype=torch.float32)); return np.exp(out.numpy())
  for ep in range(1,limit+1):
    model.train(); opt.zero_grad(set_to_none=True); out=model(tx,tr,tq); loss=((((out-ty)/scale)**2)*tw).mean(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),5.); opt.step()
    if fixed_epochs is None and (ep%5==0 or ep==limit):
      score=cell_metrics(y[valid],pred(valid),cell[valid])['cell_mae_pp']
      if score < best-1e-8: best=score; best_ep=ep; best_state={k:v.detach().clone() for k,v in model.state_dict().items()}; bad=0
      else: bad+=5
      if bad>=patience: break
  if best_state is None: best_state={k:v.detach().clone() for k,v in model.state_dict().items()}; best_ep=limit
  model.load_state_dict(best_state)
  return model,pred,best_ep,best

def run_lgbm(data,splits):
  allpred=[]; foldlogs=[]; start=time.time()
  for fold,inds in enumerate(splits):
    itrain,ival,otrain,oval=inds; sx,sr,_=fit_transform(data,itrain); z=matched(sx,sr,data.log_ratio)
    # One preregistered-ish LightGBM config, early stopping on inner validation, 3 seeds.
    for seed in SEEDS:
      model=LGBMRegressor(n_estimators=800,learning_rate=.03,num_leaves=31,max_depth=-1,min_child_samples=20,subsample=.9,colsample_bytree=.9,reg_lambda=.5,objective='regression',random_state=seed,verbosity=-1,n_jobs=1)
      model.fit(z[itrain],np.log(data.soh[itrain]),sample_weight=weights(data.cell[itrain]),eval_set=[(z[ival],np.log(data.soh[ival]))],eval_sample_weight=[weights(data.cell[ival])],callbacks=[early_stopping(60,verbose=False)])
      pred=np.exp(model.predict(z[oval],num_iteration=model.best_iteration_))
      score=cell_metrics(data.soh[oval],pred,data.cell[oval])
      foldlogs.append({'method':'lightgbm','fold':fold,'seed':seed,'best_iteration':int(model.best_iteration_ or 800),'outer_cell_mae_pp':score['cell_mae_pp'],'outer_cell_rmse_pp':score['cell_rmse_pp']})
      for ix,p in zip(oval,pred): allpred.append({'method':'lightgbm','fold':fold,'seed':seed,'source_row':int(data.source_row[ix]),'cell':str(data.cell[ix]),'true_soh':float(data.soh[ix]),'pred_soh':float(p)})
  return allpred,foldlogs,time.time()-start

def run_lstm(data,splits):
  allpred=[]; foldlogs=[]; start=time.time()
  # fixed 3 seeds; nested inner early stopping then outer refit same epoch count
  for fold,inds in enumerate(splits):
    itrain,ival,otrain,oval=inds; sx,sr,_=fit_transform(data,itrain)
    for seed in SEEDS:
      m,pred,ep,inner=fit_lstm(sx,sr,data.log_ratio,data.soh,data.cell,itrain,ival,seed)
      # Fit outer model at inner-selected epoch count, preserving split isolation
      sx2,sr2,_=fit_transform(data,otrain)
      m2,pred2,_,_=fit_lstm(sx2,sr2,data.log_ratio,data.soh,data.cell,otrain,None,seed,fixed_epochs=ep)
      predv=pred2(oval); score=cell_metrics(data.soh[oval],predv,data.cell[oval])
      foldlogs.append({'method':'lstm','fold':fold,'seed':seed,'fixed_epochs':int(ep),'inner_cell_mae_pp':float(inner),'outer_cell_mae_pp':score['cell_mae_pp'],'outer_cell_rmse_pp':score['cell_rmse_pp']})
      for ix,p in zip(oval,predv): allpred.append({'method':'lstm','fold':fold,'seed':seed,'source_row':int(data.source_row[ix]),'cell':str(data.cell[ix]),'true_soh':float(data.soh[ix]),'pred_soh':float(p)})
  return allpred,foldlogs,time.time()-start

def summarize(rows):
  out={}
  for method in ('lightgbm','lstm'):
    sub=[r for r in rows if r['method']==method]; byseed=[]
    for seed in SEEDS:
      s=[r for r in sub if r['seed']==seed]; byseed.append(cell_metrics(np.array([r['true_soh'] for r in s]),np.array([r['pred_soh'] for r in s]),np.array([r['cell'] for r in s])))
    # geomean across seed predictions
    bysource={}
    for r in sub: bysource.setdefault(r['source_row'],[]).append(r['pred_soh'])
    pred=np.array([np.exp(np.mean(np.log(v))) for _,v in sorted(bysource.items())]); true=np.array([next(r['true_soh'] for r in sub if r['source_row']==k) for k in sorted(bysource)]); cell=np.array([next(r['cell'] for r in sub if r['source_row']==k) for k in sorted(bysource)])
    ens=cell_metrics(true,pred,cell)
    out[method]={'single_seed_cell_mae_pp':[x['cell_mae_pp'] for x in byseed],'single_seed_mean_pp':float(np.mean([x['cell_mae_pp'] for x in byseed])),'geometric_ensemble':ens}
  return out

def main():
  data,held=load_development(VIEW); old=json.loads(FOLDS.read_text()); splits=[split_indices(data,f,n) for n,f in enumerate(old['folds'])]
  lp,ll,ls=run_lgbm(data,splits); tp,tl,ts=([],[],0)
  result={'scope':'development-only nested CV; heldout/protected XJTU cells unscored','view':str(VIEW),'heldout_cells':held,'lightgbm_seconds':ls,'lstm_seconds':ts,'fold_logs':ll+tl,'summary':summarize(lp+tp),'rows':lp+tp}
  OUT.write_text(json.dumps(result,indent=2)); print(json.dumps({'out':str(OUT),'heldout':held,'lightgbm_seconds':ls,'lstm_seconds':ts,'summary':result['summary']},indent=2))
if __name__=='__main__': main()

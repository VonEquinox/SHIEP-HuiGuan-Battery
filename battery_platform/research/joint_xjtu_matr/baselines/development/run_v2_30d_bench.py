import json,time,random
from pathlib import Path
import numpy as np, torch
from sklearn.preprocessing import StandardScaler
from lightgbm import LGBMRegressor,early_stopping
ROOT=Path('/Users/vonequinox/Program/GithubProjects/SHIEP-HuiGuan-Battery'); BASE=ROOT/'model_lab/data/derived/v2/multisource_features_20261002_v2'; OUT=Path('/tmp/v2_30d_benchmark_20261002.json')
SEEDS=(0,1,2)

def cell_scores(y,p,c,source=None):
  if source is not None: mask=np.asarray(source)==source; # dummy
  cells=[]
  for name in sorted(set(map(str,c))):
    m=np.asarray(c)==name; e=(np.asarray(p)[m]-np.asarray(y)[m])*100.; cells.append({'cell':name,'n':int(m.sum()),'mae_pp':float(np.abs(e).mean()),'rmse_pp':float(np.sqrt(np.mean(e**2)))})
  return {'cell_mae_pp':float(np.mean([x['mae_pp'] for x in cells])) if cells else None,'cell_rmse_pp':float(np.mean([x['rmse_pp'] for x in cells])) if cells else None,'cells':cells}

def source_scores(y,p,c,src):
  out={}
  for s in ['xjtu','matr','all']:
    m=np.ones(len(y),bool) if s=='all' else np.asarray(src)==s
    out[s]=cell_scores(np.asarray(y)[m],np.asarray(p)[m],np.asarray(c)[m])
  return out

def load_data():
  meta=json.loads((BASE/'features.json').read_text()); raw=np.load(BASE/'features.npz',allow_pickle=False)
  rows=meta['rows']; keep=np.array([r['source_id'] in ('xjtu','matr') and r['split'] in ('train','dev','calibration') for r in rows]); idx=np.flatnonzero(keep)
  x=np.asarray(raw['features'])[idx].astype(np.float32); y=np.asarray(raw['y_soh'])[idx].astype(np.float64); rows=[rows[i] for i in idx]
  if not np.isfinite(x).all():
   tr=np.array([r['split']=='train' for r in rows]); med=np.nanmedian(np.where(np.isfinite(x[tr]),x[tr],np.nan),axis=0); x=np.where(np.isfinite(x),x,med).astype(np.float32)
  else: med=None
  split=np.array([r['split'] for r in rows]); cells=np.array([r['physical_cell_id'] for r in rows]); src=np.array([r['source_id'] for r in rows]);
  if np.any(~np.isfinite(y)): raise ValueError('invalid y')
  return x,y,split,cells,src,med

def sw(c):
  _,inv,count=np.unique(c,return_inverse=True,return_counts=True); z=1./count[inv]; return z/z.mean()

class MLP(torch.nn.Module):
 def __init__(self,d): super().__init__(); self.net=torch.nn.Sequential(torch.nn.Linear(d,128),torch.nn.ReLU(),torch.nn.Linear(128,64),torch.nn.ReLU(),torch.nn.Linear(64,1))
 def forward(self,x): return self.net(x)[:,0]
class LSTM(torch.nn.Module):
 def __init__(self,h=32): super().__init__(); self.rnn=torch.nn.LSTM(1,h,batch_first=True); self.head=torch.nn.Sequential(torch.nn.Linear(h,32),torch.nn.ReLU(),torch.nn.Linear(32,1))
 def forward(self,x): return self.head(self.rnn(x.unsqueeze(-1))[0][:,-1])[:,0]

def fit_nn(x,y,c,train,dev,seed,kind):
 torch.set_num_threads(1); random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
 model=MLP(x.shape[1]) if kind=='mlp' else LSTM(); opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.001)
 tx=torch.tensor(x[train]); ty=torch.tensor(np.log(y[train]),dtype=torch.float32); tw=torch.tensor(sw(c[train]),dtype=torch.float32); dx=torch.tensor(x[dev]); dy=y[dev]
 best=1e9; best_state=None; best_ep=0; bad=0; maxep=300
 for ep in range(1,maxep+1):
  model.train(); opt.zero_grad(); out=model(tx); scale=max(float(ty.std()),.02); loss=((((out-ty)/scale)**2)*tw).mean(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),5); opt.step()
  if ep%5==0:
   model.eval();
   with torch.no_grad(): pred=np.exp(model(dx).numpy())
   score=cell_scores(dy,pred,c[dev])['cell_mae_pp']
   if score<best-1e-9: best=score;best_ep=ep;best_state={k:v.clone() for k,v in model.state_dict().items()};bad=0
   else: bad+=5
   if bad>=60: break
 model.load_state_dict(best_state)
 def pred(ix):
  model.eval();
  with torch.no_grad(): return np.exp(model(torch.tensor(x[ix])).numpy())
 return pred,best_ep,best

def fit_lgbm(x,y,c,train,dev,seed):
 m=LGBMRegressor(n_estimators=800,learning_rate=.03,num_leaves=31,min_child_samples=12,reg_lambda=.5,random_state=seed,verbosity=-1,n_jobs=1)
 m.fit(x[train],np.log(y[train]),sample_weight=sw(c[train]),eval_set=[(x[dev],np.log(y[dev]))],callbacks=[early_stopping(60,verbose=False)])
 return lambda ix:np.exp(m.predict(x[ix],num_iteration=m.best_iteration_)),int(m.best_iteration_ or 800)

def main():
 x,y,split,c,src,med=load_data(); tr=np.flatnonzero(split=='train'); dev=np.flatnonzero(split=='dev'); cal=np.flatnonzero(split=='calibration');
 assert not len(np.intersect1d(tr,dev)) and not len(np.intersect1d(tr,cal)); assert set(split)<=set(['train','dev','calibration']); print('counts',len(tr),len(dev),len(cal),'cells',len(set(c[tr])),len(set(c[dev])),len(set(c[cal])))
 rows=[]
 for kind in ['mlp','lstm']:
  for seed in SEEDS:
   pred,ep,inner=fit_nn(x,y,c,tr,dev,seed,kind); forset={}
   for part,ix in [('dev',dev),('calibration',cal)]:
    p=pred(ix); score=source_scores(y[ix],p,c[ix],src[ix]); rows.append({'method':kind,'seed':seed,'part':part,'epochs':ep,'inner_dev_cell_mae_pp':inner,'scores':score}); print(kind,seed,part,ep,score['all']['cell_mae_pp'],flush=True)
 for seed in SEEDS:
  pred,it=fit_lgbm(x,y,c,tr,dev,seed)
  for part,ix in [('dev',dev),('calibration',cal)]:
   p=pred(ix); score=source_scores(y[ix],p,c[ix],src[ix]); rows.append({'method':'lightgbm','seed':seed,'part':part,'best_iteration':it,'scores':score}); print('lightgbm',seed,part,it,score['all']['cell_mae_pp'],flush=True)
 out={'scope':'XJTU+MATR 30D development benchmark; final rows excluded before scoring','counts':{'train':len(tr),'dev':len(dev),'calibration':len(cal),'final_excluded':sum(r['split']=='final' and r['source_id'] in ('xjtu','matr') for r in json.loads((BASE/'features.json').read_text())['rows'])},'source_counts':{s:int(np.sum(src==s)) for s in ['xjtu','matr']},'rows':rows}
 OUT.write_text(json.dumps(out,indent=2)); print('saved',OUT)
if __name__=='__main__':main()

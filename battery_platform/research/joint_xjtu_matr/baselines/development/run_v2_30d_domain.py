import json,time,random
from pathlib import Path
import numpy as np,torch
from lightgbm import LGBMRegressor,early_stopping
ROOT=Path('/Users/vonequinox/Program/GithubProjects/SHIEP-HuiGuan-Battery'); BASE=ROOT/'model_lab/data/derived/v2/multisource_features_20261002_v2'; OUT=Path('/tmp/v2_30d_domain_20261002.json'); SEEDS=(0,1,2)
def scores(y,p,c,s):
 o={}
 for z in ['all','xjtu','matr']:
  m=np.ones(len(y),bool) if z=='all' else s==z; cells=[]
  for q in sorted(set(c[m])):
   k=m&(c==q); e=(p[k]-y[k])*100.; cells.append((abs(e).mean(),np.sqrt((e*e).mean())))
  o[z]={'cell_mae_pp':float(np.mean([a for a,b in cells])),'cell_rmse_pp':float(np.mean([b for a,b in cells]))}
 return o
def sw(c):
 _,inv,n=np.unique(c,return_inverse=True,return_counts=True); w=1/n[inv];return w/w.mean()
class MLP(torch.nn.Module):
 def __init__(self,d):super().__init__();self.net=torch.nn.Sequential(torch.nn.Linear(d,128),torch.nn.ReLU(),torch.nn.Linear(128,64),torch.nn.ReLU(),torch.nn.Linear(64,1))
 def forward(self,x):return self.net(x)[:,0]
class LSTM(torch.nn.Module):
 def __init__(self):super().__init__();self.rnn=torch.nn.LSTM(1,32,batch_first=True);self.h=torch.nn.Sequential(torch.nn.Linear(34,32),torch.nn.ReLU(),torch.nn.Linear(32,1))
 def forward(self,x,d):return self.h(torch.cat((self.rnn(x.unsqueeze(-1))[0][:,-1],d),1))[:,0]
def load():
 m=json.load(open(BASE/'features.json')); z=np.load(BASE/'features.npz',allow_pickle=False); rows=m['rows']; ids=[i for i,r in enumerate(rows) if r['source_id'] in ('xjtu','matr') and r['split'] in ('train','dev','calibration')]; rows=[rows[i] for i in ids]; x=z['features'][ids].astype(np.float32); y=z['y_soh'][ids].astype(float); split=np.array([r['split'] for r in rows]); c=np.array([r['physical_cell_id'] for r in rows]); s=np.array([r['source_id'] for r in rows]); tr=split=='train'; med=np.nanmedian(np.where(np.isfinite(x[tr]),x[tr],np.nan),0); x=np.where(np.isfinite(x),x,med); mu=np.nanmean(x[tr],0); sd=np.nanstd(x[tr],0); sd[sd<1e-6]=1.; x=(x-mu)/sd; d=np.column_stack((s=='xjtu',s=='matr')).astype(np.float32); x=np.concatenate((x,d),1); return x,y,split,c,s,d

def y_stats(y,s,tr):
 mu={};sc={}
 for q in ['xjtu','matr']:
  a=np.log(y[tr&(s==q)]);mu[q]=a.mean();sc[q]=max(a.std(),.02)
 return np.array([mu[q] for q in s]),np.array([sc[q] for q in s]),mu,sc
def train(kind,x,y,split,c,s,d,seed):
 tr=split=='train';dv=split=='dev'; mu,sc,_,_=y_stats(y,s,tr); target=(np.log(y)-mu)/sc; torch.set_num_threads(1);random.seed(seed);np.random.seed(seed);torch.manual_seed(seed); model=MLP(32) if kind=='mlp' else LSTM(); opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.001); tx=torch.tensor(x[tr]);td=torch.tensor(d[tr]);ty=torch.tensor(target[tr],dtype=torch.float32);tw=torch.tensor(sw(c[tr]),dtype=torch.float32);best=1e9;bs=None;epbest=0;bad=0
 for ep in range(1,301):
  model.train();opt.zero_grad();out=model(tx) if kind=='mlp' else model(tx[:,:30],td);loss=((((out-ty)/1.)**2)*tw).mean();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5);opt.step()
  if ep%5==0:
   model.eval();
   with torch.no_grad(): out=model(torch.tensor(x[dv])) if kind=='mlp' else model(torch.tensor(x[dv,:30]),torch.tensor(d[dv])); p=np.exp(mu[dv]+sc[dv]*out.numpy())
   q=scores(y[dv],p,c[dv],s[dv])['all']['cell_mae_pp']
   if q<best-1e-9:best=q;bs={k:v.clone() for k,v in model.state_dict().items()};epbest=ep;bad=0
   else:bad+=5
   if bad>=60:break
 model.load_state_dict(bs); model.eval()
 def pred(ix):
  with torch.no_grad():out=model(torch.tensor(x[ix])) if kind=='mlp' else model(torch.tensor(x[ix,:30]),torch.tensor(d[ix]));return np.exp(mu[ix]+sc[ix]*out.numpy())
 return pred,epbest,best

def lgb(x,y,split,c,s,seed):
 tr=split=='train';dv=split=='dev'; mu,sc,_,_=y_stats(y,s,tr);target=(np.log(y)-mu)/sc;m=LGBMRegressor(n_estimators=800,learning_rate=.03,num_leaves=31,min_child_samples=12,reg_lambda=.5,random_state=seed,verbosity=-1,n_jobs=1);m.fit(x[tr],target[tr],sample_weight=sw(c[tr]),eval_set=[(x[dv],target[dv])],callbacks=[early_stopping(60,verbose=False)]);return lambda ix:np.exp(mu[ix]+sc[ix]*m.predict(x[ix],num_iteration=m.best_iteration_)),int(m.best_iteration_ or 800)
def main():
 x,y,split,c,s,d=load();print('counts',sum(split=='train'),sum(split=='dev'),sum(split=='calibration'));rows=[]
 for kind in ['mlp','lstm']:
  for seed in SEEDS:
   p,ep,inner=train(kind,x,y,split,c,s,d,seed)
   for part in ['dev','calibration']:
    ix=split==part; q=scores(y[ix],p(ix),c[ix],s[ix]);rows.append({'method':kind,'seed':seed,'part':part,'epochs':ep,'inner_dev':inner,'scores':q});print(kind,seed,part,ep,q,flush=True)
 for seed in SEEDS:
  p,it=lgb(x,y,split,c,s,seed)
  for part in ['dev','calibration']:
   ix=split==part;q=scores(y[ix],p(ix),c[ix],s[ix]);rows.append({'method':'lightgbm','seed':seed,'part':part,'best_iteration':it,'scores':q});print('lgb',seed,part,it,q,flush=True)
 OUT.write_text(json.dumps({'scope':'XJTU+MATR 30D source-adapted development/calibration; final excluded','rows':rows},indent=2));print('saved',OUT)
if __name__=='__main__':main()

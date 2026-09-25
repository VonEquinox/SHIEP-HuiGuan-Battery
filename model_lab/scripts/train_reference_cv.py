"""Pre-registered grouped development CV on a numerical, provenance-checked bundle.

This runner never scores the external held-out physical cells. Model-selection
CV is explicitly development evidence, not a claim of benchmark SOTA.
"""
from __future__ import annotations
import argparse, hashlib, json, random, time
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.svm import SVR
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics.pairwise import rbf_kernel
from scipy.linalg import cho_factor, cho_solve
import joblib
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from model_lab.modeling.reference_potential import CurrentMLP,MatchedMLP,ReferencePotential,TabMDirect,TabMReferencePotential


def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while b:=f.read(1024*1024): h.update(b)
    return h.hexdigest()

def macro_metrics(y,p,cell):
    rows=[]
    for c in np.unique(cell):
        e=(p[cell==c]-y[cell==c])*100
        rows.append({'cell':str(c),'mae_pp':float(np.mean(np.abs(e))),'rmse_pp':float(np.sqrt(np.mean(e*e))),'n':len(e)})
    e=(p-y)*100
    return {'cell_mae_pp':float(np.mean([r['mae_pp'] for r in rows])), 'cell_rmse_pp':float(np.mean([r['rmse_pp'] for r in rows])), 'pooled_mae_pp':float(np.mean(np.abs(e))),'pooled_rmse_pp':float(np.sqrt(np.mean(e*e))),'cells':rows}

def weights(cell):
    _,inv,cnt=np.unique(cell,return_inverse=True,return_counts=True)
    w=1/cnt[inv].astype(float)
    return w/w.mean()

def transform_fit(x,r,tr):
    raw=np.concatenate([x[tr],r[tr]],axis=0)
    median=np.nanmedian(np.where(np.isfinite(raw),raw,np.nan),axis=0)
    median=np.nan_to_num(median)
    raw=np.where(np.isfinite(raw),raw,median)
    scaler=StandardScaler().fit(raw)
    def apply(z): return scaler.transform(np.where(np.isfinite(z),z,median)).astype(np.float32)
    return apply(x),apply(r),{'median':median,'mean':scaler.mean_,'scale':scaler.scale_}

def matched(x,r,lq): return np.concatenate([x,r,x-r,lq[:,None]],axis=1)

class DifferenceKernel:
    def __init__(self,alpha=.1,gamma=None,prior=True):self.alpha,self.gamma,self.prior=alpha,gamma,prior
    def kernel(self,x,r,z,s):
        return rbf_kernel(x,z,gamma=self.gamma)-rbf_kernel(x,s,gamma=self.gamma)-rbf_kernel(r,z,gamma=self.gamma)+rbf_kernel(r,s,gamma=self.gamma)
    def fit(self,x,r,lq,y,w):
        self.x,self.r=x.astype(float),r.astype(float)
        self.ys=max(float(np.std(y)),.02)
        self.sw=np.sqrt(w)
        k=self.kernel(self.x,self.r,self.x,self.r)
        a=k*self.sw[:,None]*self.sw[None,:]+self.alpha*np.eye(len(x))
        target=(y-(lq if self.prior else 0))/self.ys
        self.coef=self.sw*cho_solve(cho_factor(a,lower=True,check_finite=True),self.sw*target)
        return self
    def predict(self,x,r,lq):
        return (lq if self.prior else 0)+self.ys*(self.kernel(x,r,self.x,self.r)@self.coef)


def neural_fit(name,x,r,lq,y,cell,tr,va,config,seed,device,max_epochs,patience,artifact):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    width=int(config.get('width',64))
    factories={
      'current_mlp':lambda:CurrentMLP(x.shape[1],width),
      'matched_mlp':lambda:MatchedMLP(x.shape[1],width),
      'reference_potential':lambda:ReferencePotential(x.shape[1],width,True),
      'potential_no_prior':lambda:ReferencePotential(x.shape[1],width,False),
      'tabm':lambda:TabMDirect(x.shape[1],width,8),
      'tabm_potential':lambda:TabMReferencePotential(x.shape[1],width,8),
    }
    m=factories[name]().to(device)
    prior=('potential' in name)
    mu=float(y[tr].mean());sigma=max(float(y[tr].std()),.02)
    a=torch.tensor(x,dtype=torch.float32,device=device);b=torch.tensor(r,dtype=torch.float32,device=device);q=torch.tensor(lq,dtype=torch.float32,device=device)
    target=torch.tensor(y,dtype=torch.float32,device=device)
    _, group_inverse = np.unique(cell[tr], return_inverse=True)
    group_matrix=torch.nn.functional.one_hot(torch.tensor(group_inverse,device=device)).float()
    group_count=group_matrix.sum(0).clamp_min(1.)
    wt=torch.tensor(weights(cell[tr]),dtype=torch.float32,device=device)
    train=torch.tensor(tr,device=device);valid=torch.tensor(va,device=device)
    opt=torch.optim.AdamW(m.parameters(),lr=float(config['lr']),weight_decay=float(config.get('weight_decay',.001)))
    best=float('inf');best_epoch=-1;best_state=None;history=[];bad=0
    for epoch in range(max_epochs):
        m.train();opt.zero_grad(set_to_none=True)
        raw=m(a[train],b[train],q[train])
        output=raw if prior else mu+sigma*raw
        residual=(output-target[train,None])/sigma
        error=residual.square().mean(dim=1)
        loss=(error*wt).mean()
        if prior:
            group_mean=(group_matrix.T@residual)/group_count[:,None]
            centered=residual-group_matrix@group_mean
            loss=loss+.25*(centered.square().mean(dim=1)*wt).mean()
        if not torch.isfinite(loss):raise ValueError('nonfinite train loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(m.parameters(),5.);opt.step()
        if epoch%5==4 or epoch==max_epochs-1:
            m.eval()
            with torch.no_grad():
                raw=m(a[valid],b[valid],q[valid]);pred=torch.exp((raw if prior else mu+sigma*raw).mean(dim=1)).cpu().numpy()
            score=macro_metrics(np.exp(y[va]),pred,cell[va])['cell_mae_pp']
            history.append({'epoch':epoch+1,'train_loss':float(loss.detach().cpu()),'validation_cell_mae_pp':score})
            if score<best-1e-8:
                best=score;best_epoch=epoch+1;best_state={k:v.detach().cpu().clone() for k,v in m.state_dict().items()};bad=0
            else:bad+=5
            if bad>=patience:break
    if best_state is None:raise RuntimeError('no valid checkpoint')
    m.load_state_dict(best_state);m.eval()
    with torch.no_grad():
        raw=m(a[valid],b[valid],q[valid]);pred=torch.exp((raw if prior else mu+sigma*raw).mean(dim=1)).cpu().numpy()
    torch.save({'state_dict':best_state,'name':name,'config':config,'seed':seed,'mu':mu,'sigma':sigma,'dimension':x.shape[1],'best_epoch':best_epoch},artifact)
    artifact.with_suffix('.history.json').write_text(json.dumps(history,indent=2))
    return pred,{'best_epoch':best_epoch,'parameters':sum(p.numel() for p in m.parameters())}


def main(args):
    torch.set_num_threads(4)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    bundle=np.load(args.bundle,allow_pickle=False)
    x=np.asarray(bundle['x'],dtype=np.float32);r=np.asarray(bundle['reference'],dtype=np.float32)
    lq=np.asarray(bundle['log_window_ratio'],dtype=np.float32)
    y=np.asarray(bundle['soh'],dtype=float)
    cell=np.asarray(bundle['cell']);protocol=np.asarray(bundle['protocol'])
    holdout=np.asarray(bundle['holdout'],dtype=bool)
    if np.any(y<=0) or not np.isfinite(y).all():raise ValueError('all labels must be finite positive measured SOH')
    dev=np.flatnonzero(~holdout)
    logy=np.log(y)
    split=StratifiedGroupKFold(n_splits=3,shuffle=True,random_state=2047)
    folds=[(dev[tr],dev[va]) for tr,va in split.split(dev,protocol[dev],groups=cell[dev])]
    names=args.models.split(',');seeds=[int(s) for s in args.seeds.split(',')]
    configs={
      'ridge':[{'alpha':a} for a in (.1,10.,1000.)],
      'histgb':[{'max_leaf_nodes':n} for n in (7,15,31)],
      'extra_trees':[{'min_samples_leaf':n} for n in (1,3,7)],
      'svr':[{'C':c,'gamma':g/x.shape[1]} for c,g in ((1,.25),(10,1),(10,4))],
      'catboost':[{'depth':d} for d in (3,5,7)],
      'difference_kernel':[{'alpha':a,'gamma':g/x.shape[1]} for a,g in ((.01,.25),(.1,1),(1,4))],
      'kernel_no_prior':[{'alpha':a,'gamma':g/x.shape[1]} for a,g in ((.01,.25),(.1,1),(1,4))],
      'partial_charge_ratio':[{}],
    }
    for name in ('current_mlp','matched_mlp','reference_potential','potential_no_prior','tabm','tabm_potential'):
        configs[name]=[{'width':64,'lr':lr,'weight_decay':.001} for lr in (.0005,.002,.006)]
    manifest={'scope':'development grouped CV; no heldout scores','bundle_sha256':digest(args.bundle),'code_sha256':digest(__file__),'model_code_sha256':digest(Path(__file__).resolve().parents[1]/'modeling'/'reference_potential.py'),'models':names,'configs':{n:configs[n] for n in names},'seeds':seeds,'epochs':args.epochs,'patience':args.patience,'folds':[{'train_cells':np.unique(cell[tr]).tolist(),'validation_cells':np.unique(cell[va]).tolist()} for tr,va in folds],'heldout_cells':np.unique(cell[holdout]).tolist(),'primary_metric':'mean of per-cell MAE, SOH percentage points'}
    (out/'preregistration.json').write_text(json.dumps(manifest,indent=2))
    device=torch.device('mps' if args.device=='auto' and torch.backends.mps.is_available() else 'cpu' if args.device=='auto' else args.device)
    allrows=[];runs=[];start=time.time()
    stochastic={'current_mlp','matched_mlp','reference_potential','potential_no_prior','tabm','tabm_potential','extra_trees','catboost'}
    for fold,(tr,va) in enumerate(folds):
        assert not set(cell[tr])&set(cell[va]) and not set(cell[tr])&set(cell[holdout])
        sx,sr,scaler=transform_fit(x,r,tr);z=matched(sx,sr,lq)
        np.savez(out/f'fold{fold}_scaler.npz',**scaler)
        w=weights(cell[tr])
        for name in names:
          for ci,cfg in enumerate(configs[name]):
           for seed in seeds if name in stochastic else [0]:
            path=out/f'{name}-c{ci}-f{fold}-s{seed}'
            tick=time.time()
            try:
              extra={}
              if name=='partial_charge_ratio':pred=np.exp(lq[va])
              elif name in ('difference_kernel','kernel_no_prior'):
                model=DifferenceKernel(**cfg,prior=name=='difference_kernel').fit(sx[tr],sr[tr],lq[tr],logy[tr],w)
                pred=np.exp(model.predict(sx[va],sr[va],lq[va]));np.savez_compressed(path.with_suffix('.npz'),x=model.x,reference=model.r,coef=model.coef,target_scale=model.ys,gamma=model.gamma,alpha=model.alpha,prior=model.prior)
              elif name in ('ridge','histgb','extra_trees','svr','catboost'):
                if name=='ridge':model=Ridge(**cfg)
                elif name=='histgb':model=HistGradientBoostingRegressor(**cfg,max_iter=200,learning_rate=.05,early_stopping=False,l2_regularization=1.,random_state=seed)
                elif name=='extra_trees':model=ExtraTreesRegressor(**cfg,n_estimators=300,n_jobs=4,random_state=seed)
                elif name=='svr':model=SVR(**cfg,epsilon=.02)
                else:
                  from catboost import CatBoostRegressor
                  model=CatBoostRegressor(**cfg,iterations=400,learning_rate=.035,l2_leaf_reg=5,loss_function='RMSE',random_seed=seed,thread_count=4,verbose=False,allow_writing_files=False)
                mu=logy[tr].mean();sd=max(logy[tr].std(),.02)
                model.fit(z[tr],(logy[tr]-mu)/sd,sample_weight=w)
                pred=np.exp(mu+sd*model.predict(z[va]));joblib.dump({'model':model,'mu':mu,'sigma':sd},path.with_suffix('.joblib'))
              else:pred,extra=neural_fit(name,sx,sr,lq,logy,cell,tr,va,cfg,seed,device,args.epochs,args.patience,path.with_suffix('.pt'))
              score=macro_metrics(y[va],pred,cell[va])
              record={'model':name,'config':ci,'fold':fold,'seed':seed,'status':'ok','elapsed_s':time.time()-tick,**{k:v for k,v in score.items() if k!='cells'},**extra}
              for i,p in zip(va,pred):allrows.append({'model':name,'config':ci,'fold':fold,'seed':seed,'row':int(i),'cell':str(cell[i]),'protocol':str(protocol[i]),'true_soh':float(y[i]),'pred_soh':float(p)})
            except Exception as e:record={'model':name,'config':ci,'fold':fold,'seed':seed,'status':'failed','error':repr(e)}
            runs.append(record)
            print(json.dumps(record),flush=True)
            pd.DataFrame(runs).to_csv(out/'runs.csv',index=False)
            pd.DataFrame(allrows).to_csv(out/'predictions.csv',index=False)
    frame=pd.DataFrame(allrows);summaries=[]
    for (name,ci),g in frame.groupby(['model','config']):
        ens=g.groupby(['row','cell','protocol'],as_index=False).agg(true_soh=('true_soh','first'),pred_soh=('pred_soh','mean'),seeds=('seed','nunique'))
        expected_seeds=len(seeds) if name in stochastic else 1
        if len(ens)!=len(dev) or not (ens.seeds==expected_seeds).all():continue
        if 'potential' in name:
            geometric=g.assign(log_pred=np.log(g.pred_soh)).groupby('row').log_pred.mean()
            ens['pred_soh']=np.exp(ens.row.map(geometric))
        m=macro_metrics(ens.true_soh.to_numpy(),ens.pred_soh.to_numpy(),ens.cell.to_numpy())
        summaries.append({'model':name,'config':int(ci),'config_values':configs[name][ci],**m})
    summaries.sort(key=lambda z:z['cell_mae_pp'])
    result={'scope':'development grouped CV; final test never scored','seconds':time.time()-start,'device':str(device),'development_cells':len(np.unique(cell[dev])),'development_rows':len(dev),'heldout_cells':np.unique(cell[holdout]).tolist(),'candidates':summaries,'failed_runs':[r for r in runs if r['status']!='ok']}
    (out/'summary.json').write_text(json.dumps(result,indent=2))
    print('DONE',json.dumps({k:v for k,v in result.items() if k!='candidates'}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--out',required=True)
    p.add_argument('--models',default='partial_charge_ratio,ridge,histgb,extra_trees,svr,difference_kernel,current_mlp,matched_mlp,reference_potential,tabm,tabm_potential')
    p.add_argument('--seeds',default='0,1,2');p.add_argument('--epochs',type=int,default=150);p.add_argument('--patience',type=int,default=30);p.add_argument('--device',default='auto')
    main(p.parse_args())

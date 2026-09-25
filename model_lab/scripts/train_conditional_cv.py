"""Test calibrated conditional potentials against an unconditioned ablation."""
from __future__ import annotations
import argparse,json,time,sys,random
from pathlib import Path
import numpy as np
import pandas as pd
import torch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from model_lab.modeling.conditional_reference import ConditionalTabMPotential,FiLMReferencePotential
from model_lab.scripts.train_reference_cv import weights,transform_fit,macro_metrics,digest
from model_lab.scripts.train_capacity_cv import read_capacity_targets


def fit_one(x,r,y,cap,refcap,cell,tr,va,cfg,seed,mode,device,out,max_epochs=500,patience=60,fixed_epochs=None):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    m=(ConditionalTabMPotential(x.shape[1],cfg['width'],8) if mode.startswith('conditional_') else FiLMReferencePotential(x.shape[1],cfg['width'],8,use_context=mode!='film_no_context')).to(device)
    _,first=np.unique(cell[tr],return_index=True)
    combined=np.r_[cap[tr],refcap[tr[first]]]
    mu=float(combined.mean());scale=max(float(combined.std()),.02)
    relscale=max(float(np.std(y[tr])),.02)
    xx=torch.tensor(x,device=device,dtype=torch.float32);rr=torch.tensor(r,device=device,dtype=torch.float32)
    yl=torch.tensor(y,device=device,dtype=torch.float32);cq=torch.tensor((cap-mu)/scale,device=device,dtype=torch.float32);cr=torch.tensor((refcap-mu)/scale,device=device,dtype=torch.float32)
    it=torch.tensor(tr,device=device);iv=torch.tensor(va,device=device)
    wt=torch.tensor(weights(cell[tr]),device=device,dtype=torch.float32)
    opt=torch.optim.AdamW(m.parameters(),lr=cfg['lr'],weight_decay=.001)
    best=float('inf');state=None;best_epoch=0;bad=0;history=[]
    limit=fixed_epochs if fixed_epochs is not None else max_epochs
    for epoch in range(limit):
        m.train();opt.zero_grad(set_to_none=True)
        a,b=m.paired(xx[it],rr[it])
        relative=(scale*(a-b)-yl[it,None])/relscale
        labs=.5*((a-cq[it,None]).square()+(b-cr[it,None]).square()).mean(1)
        lrel=relative.square().mean(1)
        if mode=='conditional_joint':loss=((lrel+.25*labs)*wt).mean()
        elif mode in ('conditional_relative','film_context','film_no_context'):loss=(lrel*wt).mean()
        else:raise ValueError('unknown mode')
        if not torch.isfinite(loss):raise ValueError('nonfinite loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(m.parameters(),5);opt.step()
        if fixed_epochs is None and (epoch%5==4 or epoch==limit-1):
            m.eval()
            with torch.no_grad():pred=torch.exp(scale*m(xx[iv],rr[iv]).mean(1)).cpu().numpy()
            score=macro_metrics(np.exp(y[va]),pred,cell[va])['cell_mae_pp']
            history.append({'epoch':epoch+1,'train_loss':float(loss.detach().cpu()),'cell_mae_pp':score})
            if score<best-1e-8:best=score;state={k:v.detach().cpu().clone() for k,v in m.state_dict().items()};best_epoch=epoch+1;bad=0
            else:bad+=5
            if bad>=patience:break
    if fixed_epochs is not None:
        state={k:v.detach().cpu().clone() for k,v in m.state_dict().items()};best_epoch=fixed_epochs
    if state is None:raise RuntimeError('no checkpoint')
    m.load_state_dict(state);m.eval()
    with torch.no_grad():pred=torch.exp(scale*m(xx[iv],rr[iv]).mean(1)).cpu().numpy()
    torch.save({'state_dict':state,'dimension':x.shape[1],'config':cfg,'seed':seed,'mu':mu,'capacity_log_scale':scale,'mode':mode,'best_epoch':best_epoch},out.with_suffix('.pt'))
    out.with_suffix('.history.json').write_text(json.dumps(history,indent=2))
    return pred,{'best_epoch':best_epoch,'parameters':sum(p.numel() for p in m.parameters())}


def main(args):
    torch.set_num_threads(4);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    if (out/'preregistration.json').exists():raise FileExistsError('existing experiment')
    d=np.load(args.view,allow_pickle=False);x=d['x'];r=d['reference'];y=np.log(d['soh']);cell=d['cell'];held=d['holdout'];protocol=d['protocol']
    cap,refcap=read_capacity_targets(d,args.raw_bundle,args.environment)
    original=json.loads(Path(args.folds).read_text())
    folds=[(np.flatnonzero(np.isin(cell,f['train_cells'])),np.flatnonzero(np.isin(cell,f['validation_cells']))) for f in original['folds']]
    modes=['conditional_relative','conditional_joint','film_context','film_no_context']
    configs=[{'width':96,'lr':lr} for lr in (.0005,.002,.006)];seeds=[0,1,2]
    prereg={'scope':'adaptive development; heldout unscored; no absolute-capacity input','view_sha256':digest(args.view),'source_bundle_sha256':digest(args.raw_bundle),'code_sha256':digest(__file__),'model_code_sha256':digest(Path(__file__).resolve().parents[1]/'modeling/conditional_reference.py'),'folds':original['folds'],'configs':configs,'seeds':seeds,'modes':modes,'max_epochs':500,'patience':60,'joint_absolute_loss_weight':.25,'heldout_cells':np.unique(cell[held]).tolist()}
    (out/'preregistration.json').write_text(json.dumps(prereg,indent=2))
    records=[];runs=[];start=time.time();device=torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
    for fold,(tr,va) in enumerate(folds):
        assert not set(cell[tr])&set(cell[va]) and not held[tr].any() and not held[va].any()
        sx,sr,scaler=transform_fit(x,r,tr);np.savez(out/f'fold{fold}_scaler.npz',**scaler)
        for mode in modes:
         for ci,cfg in enumerate(configs):
          for seed in seeds:
            tick=time.time();nprev=len(records);path=out/f'{mode}-c{ci}-f{fold}-s{seed}'
            try:
                pred,extra=fit_one(sx,sr,y,cap,refcap,cell,tr,va,cfg,seed,mode,device,path)
                m=macro_metrics(np.exp(y[va]),pred,cell[va])
                result={'model':mode,'config':ci,'fold':fold,'seed':seed,'status':'ok','seconds':time.time()-tick,**{k:v for k,v in m.items() if k!='cells'},**extra}
                for i,p in zip(va,pred):records.append({'model':mode,'config':ci,'fold':fold,'seed':seed,'row':int(i),'cell':str(cell[i]),'protocol':str(protocol[i]),'true_soh':float(np.exp(y[i])),'pred_soh':float(p)})
            except Exception as e:result={'model':mode,'config':ci,'fold':fold,'seed':seed,'status':'failed','error':repr(e)}
            print(json.dumps(result),flush=True);runs.append(result)
            pd.DataFrame(runs).to_csv(out/'runs.csv',index=False)
            if len(records)>nprev:pd.DataFrame(records[nprev:]).to_csv(out/'predictions.csv',mode='a',header=not(out/'predictions.csv').exists(),index=False)
    f=pd.DataFrame(records);candidates=[]
    for (mode,ci),g in f.groupby(['model','config']):
        g=g.assign(log_pred=np.log(g.pred_soh))
        e=g.groupby(['row','cell'],as_index=False).agg(true_soh=('true_soh','first'),log_pred=('log_pred','mean'),seeds=('seed','nunique'))
        if len(e)!=int((~held).sum()) or not(e.seeds==3).all():continue
        candidates.append({'model':mode,'config':int(ci),'config_values':configs[ci],**macro_metrics(e.true_soh.to_numpy(),np.exp(e.log_pred.to_numpy()),e.cell.to_numpy())})
    candidates.sort(key=lambda c:c['cell_mae_pp'])
    report={'scope':'development only','seconds':time.time()-start,'candidates':candidates,'failed_runs':[r for r in runs if r['status']!='ok']}
    (out/'summary.json').write_text(json.dumps(report,indent=2));print('CONDITIONAL_CV_DONE',time.time()-start,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--view',default='model_lab/reports/round2/cv_physical/view_bundle.npz');p.add_argument('--folds',default='model_lab/reports/round2/cv_physical/preregistration.json');p.add_argument('--raw-bundle',default='model_lab/data/derived/xjtu_verified/bundle.npz');p.add_argument('--environment',default='model_lab/data/derived/xjtu_verified/environment.npz');p.add_argument('--out',default='model_lab/reports/round2/cv_conditional');main(p.parse_args())

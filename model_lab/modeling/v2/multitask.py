"""M2 research candidate: masked temporal encoder, source adapters, independent heads."""
from __future__ import annotations
import numpy as np
import torch
from torch import nn
from scipy.special import expit, logit
from scipy.stats import norm
from .baselines import object_weights
from .contracts import domain_key
from .survival import event_bins


class TemporalMultiTask(nn.Module):
    def __init__(self,n_features,n_domains,n_survival_bins,width=128,adapter_width=32,channels=5,
                 domain_adapter=True,history=True,single_task=False):
        super().__init__()
        self.history,self.single_task = history,single_task
        self.encoder = nn.Sequential(nn.Conv1d(channels,width,5,padding=2),nn.GELU(),
            nn.Conv1d(width,width,3,padding=2,dilation=2),nn.GELU(),
            nn.Conv1d(width,width,3,padding=4,dilation=4),nn.GELU())
        self.statistics = nn.Sequential(nn.Linear(n_features,width),nn.GELU(),nn.Linear(width,width))
        self.adapters = nn.ModuleList([nn.Sequential(nn.Linear(width,adapter_width),nn.GELU(),nn.Linear(adapter_width,width)) for _ in range(n_domains)]) if domain_adapter else None
        self.soh = nn.Linear(width,2)
        self.efficiency = nn.Linear(width,2)
        self.survival = nn.Linear(width,n_survival_bins)
        self.fault = nn.Linear(width,1)

    def forward(self,features,sequences,mask,domain):
        b,h,t,c = sequences.shape
        clean = sequences*mask[...,None]
        pointmask = mask.reshape(b*h,1,t)
        active=pointmask.sum(dim=(1,2))>0
        sequence_encoding=torch.zeros((b*h,self.encoder[0].out_channels),device=features.device,dtype=features.dtype)
        if active.any():
            encoded=self.encoder(clean.reshape(b*h,t,c)[active].transpose(1,2))
            pm=pointmask[active]
            sequence_encoding[active]=(encoded*pm).sum(dim=-1)/pm.sum(dim=-1).clamp_min(1)
        sequence_encoding = sequence_encoding.reshape(b,h,-1)
        valid = mask.sum(dim=-1)>0
        if self.history:
            temporal = (sequence_encoding*valid[...,None]).sum(dim=1)/valid.sum(dim=1,keepdim=True).clamp_min(1)
        else:
            positions = torch.arange(h,device=mask.device).expand(b,h)
            last = torch.where(valid,positions,-1).max(dim=1).values.clamp_min(0)
            temporal = sequence_encoding[torch.arange(b,device=mask.device),last]
        representation = temporal+self.statistics(features)
        if self.adapters is not None:
            residual = torch.zeros_like(representation)
            for d,adapter in enumerate(self.adapters):
                ix = domain==d
                if ix.any(): residual[ix] = adapter(representation[ix])
            representation = representation+residual
        return {"soh":self.soh(representation),"efficiency":self.efficiency(representation),
                "hazard_logits":self.survival(representation),"fault_logits":self.fault(representation).squeeze(-1)}


def torch_survival_nll(logits,lower,upper,kind,grid):
    log_survival = torch.nn.functional.logsigmoid(-logits).cumsum(-1)
    s = torch.cat([torch.ones((len(logits),1),device=logits.device),log_survival.exp()],dim=1)
    l,u = event_bins(lower.detach().numpy(),upper.detach().numpy(),kind.detach().numpy(),grid)
    l,u = torch.as_tensor(l),torch.as_tensor(u)
    rows = torch.arange(len(logits))
    likelihood = torch.where(kind==0,s[rows,l],s[rows,l]-s[rows,u])
    beyond = (kind>0)&(upper>grid[-1])
    likelihood = torch.where(beyond,s[:,-1],likelihood)
    return -likelihood.clamp_min(1e-12).log()


def masked_loss(output,labels,weights,grid,single_task=False,domain_denominator=None,task_weights=None):
    task_weights=task_weights or {}
    losses = []
    active = []
    for task in ("soh",) if single_task else ("soh","efficiency"):
        y = labels[f"y_{task}"]
        valid = torch.isfinite(y)
        if not valid.any(): continue
        target = y[valid].log() if task=="soh" else torch.logit(y[valid].clamp(1e-6,1-1e-6))
        mu,logscale = output[task][valid].unbind(-1)
        logscale = logscale.clamp(-5,3)
        nll = .5*((target-mu)/logscale.exp())**2+logscale+.5*np.log(2*np.pi)
        w = weights[valid]
        losses.append(task_weights.get(task,1.)*(nll*w).sum()/(w.sum() if domain_denominator is None else domain_denominator)); active.append(task)
    if not single_task:
        valid = labels["survival_kind"]>=0
        if valid.any():
            nll = torch_survival_nll(output["hazard_logits"][valid],labels["survival_lower"][valid],labels["survival_upper"][valid],labels["survival_kind"][valid],grid)
            w = weights[valid]
            losses.append(task_weights.get("rul",1.)*(nll*w).sum()/(w.sum() if domain_denominator is None else domain_denominator)); active.append("rul")
        valid = labels["y_fault"]>=0
        if valid.any():
            loss = nn.functional.binary_cross_entropy_with_logits(output["fault_logits"][valid],labels["y_fault"][valid],reduction="none")
            w = weights[valid]
            losses.append(task_weights.get("fault",1.)*(loss*w).sum()/(w.sum() if domain_denominator is None else domain_denominator)); active.append("fault")
    if not losses:
        # Connected zero; missing labels never become a synthetic supervision value.
        return sum(v.sum()*0 for v in output.values()),active
    return sum(losses)/(len(losses) if domain_denominator is None else 1),active


class MultiTaskModel:
    def __init__(self,spec,seed=0,grid=None):
        self.spec,self.seed,self.grid = spec,seed,grid or [50,100,150,200,300,400,600,800,1000]
        torch.manual_seed(seed)
        self.model = TemporalMultiTask(n_survival_bins=len(self.grid),**spec)
        self.label_support = {}

    def fit(self,arrays,rows,epochs=12,batch_size=8,learning_rate=.001,loss_contract="available_task_mean_v1",task_weights=None,min_survival_objects=1):
        torch.set_num_threads(2)
        optimizer = torch.optim.Adam(self.model.parameters(),lr=learning_rate)
        rng = np.random.default_rng(self.seed)
        base = object_weights([r["physical_cell_id"] for r in rows])
        # Every source has equal total weight, and each physical object equal within source.
        for source in sorted({r["source_id"] for r in rows}):
            mask = np.asarray([r["source_id"]==source for r in rows])
            base[mask] /= base[mask].sum()
        self.label_support = {k:bool(np.any(np.isfinite(arrays[f"y_{k}"]))) for k in ("soh","efficiency")}
        self.label_support.update(rul=bool(np.any(arrays["survival_kind"]>=0)),fault=bool(np.any(arrays["y_fault"]>=0)))
        if self.spec.get("single_task"):
            self.label_support.update(efficiency=False,rul=False,fault=False)
        self.label_support_by_domain = {}
        for key in {domain_key(r) for r in rows}:
            ix=np.asarray([domain_key(r)==key for r in rows])
            local={k:bool(np.any(np.isfinite(arrays[f"y_{k}"][ix]))) for k in ("soh","efficiency")}
            valid_survival=ix&(arrays["survival_kind"]>=0)
            local.update(rul=len({rows[i]["physical_cell_id"] for i in np.flatnonzero(valid_survival)})>=min_survival_objects,
                         fault=bool(np.any(arrays["y_fault"][ix]>=0)))
            if self.spec.get("single_task"):local.update(efficiency=False,rul=False,fault=False)
            self.label_support_by_domain[key]=local
        self.history = []
        for epoch in range(epochs):
            self.model.train()
            order = rng.permutation(len(rows)); batch_losses = []; heads = set()
            for start in range(0,len(rows),batch_size):
                ix = order[start:start+batch_size]
                tensor = lambda k:torch.as_tensor(arrays[k][ix],dtype=torch.float32)
                output = self.model(tensor("features"),tensor("sequences"),tensor("sequence_mask"),torch.as_tensor(arrays["domain"][ix],dtype=torch.long))
                labels = {k:tensor(k) for k in ("y_soh","y_efficiency","y_fault","survival_kind","survival_lower","survival_upper")}
                domain_denominator=None
                if loss_contract=="fixed_domain_object_task_v2":
                    domain_denominator=len({r["source_id"] for r in rows})/int(np.ceil(len(rows)/batch_size))
                elif loss_contract!="available_task_mean_v1":raise ValueError("unknown loss contract")
                loss,active = masked_loss(output,labels,torch.as_tensor(base[ix],dtype=torch.float32),self.grid,self.spec.get("single_task",False),domain_denominator,task_weights)
                if not active and loss_contract=="fixed_domain_object_task_v2":continue
                if not torch.isfinite(loss): raise ValueError("non-finite M2 training loss")
                optimizer.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(self.model.parameters(),5); optimizer.step()
                batch_losses.append(float(loss.detach()));heads.update(active)
            self.history.append({"epoch":epoch+1,"loss":float(np.mean(batch_losses)),"active_heads":sorted(heads)})
        return self

    def predict(self,arrays,rows,batch_size=8):
        self.model.eval(); collected = []
        with torch.no_grad():
            for start in range(0,len(rows),batch_size):
                sl = slice(start,start+batch_size)
                tensor = lambda k:torch.as_tensor(arrays[k][sl],dtype=torch.float32)
                output = self.model(tensor("features"),tensor("sequences"),tensor("sequence_mask"),torch.as_tensor(arrays["domain"][sl],dtype=torch.long))
                collected.append({k:v.numpy() for k,v in output.items()})
        if not collected: return {}
        outputs = {k:np.concatenate([o[k] for o in collected]) for k in collected[0]}
        result = {}
        for task in ("soh","efficiency"):
            params = outputs[task]
            scale = np.exp(np.clip(params[:,1],-5,3))
            quantiles = params[:,0,None]+scale[:,None]*norm.ppf([.05,.5,.95])
            q = np.exp(quantiles) if task=="soh" else expit(quantiles)
            result[f"{task}_quantiles"] = q if self.label_support.get(task) else np.full_like(q,np.nan)
            result[f"{task}_normal_transformed"] = np.column_stack([params[:,0],scale]) if self.label_support.get(task) else np.full_like(params,np.nan)
        result["hazard"] = expit(outputs["hazard_logits"]) if self.label_support.get("rul") else np.full_like(outputs["hazard_logits"],np.nan)
        result["fault_probability"] = expit(outputs["fault_logits"]) if self.label_support.get("fault") else np.full_like(outputs["fault_logits"],np.nan)
        for i,row in enumerate(rows):
            by_domain=getattr(self,"label_support_by_domain",{})
            # A feature bundle may enumerate dev-only policies so their domain
            # indices exist, but that does not make their heads trained. Legacy
            # wrappers without any domain map retain their explicit global map.
            support=by_domain.get(domain_key(row),{}) if by_domain else self.label_support
            for task in ("soh","efficiency"):
                if not support.get(task):
                    result[f"{task}_quantiles"][i]=np.nan
                    result[f"{task}_normal_transformed"][i]=np.nan
            if not support.get("rul"):result["hazard"][i]=np.nan
            if not support.get("fault"):result["fault_probability"][i]=np.nan
        return result

    def save(self,path):
        np.savez_compressed(path,**{k:v.detach().numpy() for k,v in self.model.state_dict().items()})

    @classmethod
    def load(cls,spec,path,seed=0,grid=None,label_support=None,label_support_by_domain=None):
        obj = cls(spec,seed,grid)
        with np.load(path,allow_pickle=False) as z:
            obj.model.load_state_dict({k:torch.from_numpy(z[k].copy()) for k in z.files},strict=True)
        obj.label_support = label_support or {}
        obj.label_support_by_domain=label_support_by_domain or {}
        return obj

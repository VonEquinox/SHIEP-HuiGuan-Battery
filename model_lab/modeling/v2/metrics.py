"""Per-source/per-object evaluation; real and generated namespaces never aggregate."""
from __future__ import annotations
import numpy as np
from scipy.stats import norm
from sklearn.metrics import average_precision_score,roc_curve
from .contracts import domain_key
from .calibration import apply_cqr,calibration_error,apply_fault_calibration
from .survival import censored_nll,survival_from_hazard


def regression_metrics(y,q,groups,normal=None,task="soh",intervals=None):
    y,q,groups=np.asarray(y),np.asarray(q),np.asarray(groups)
    valid=np.isfinite(y)&np.isfinite(q).all(axis=1)
    if not valid.any():return {"status":"unavailable","reason":"no supported legal labels"}
    y,q,groups=y[valid],q[valid],groups[valid]
    objects={}
    for group in sorted(set(groups)):
        ix=groups==group;error=q[ix,1]-y[ix]
        objects[str(group)]={"mae":float(np.abs(error).mean()),"rmse":float(np.sqrt((error**2).mean())),"rows":int(ix.sum())}
    err=y[:,None]-q
    pinball=np.maximum(np.asarray([.05,.5,.95])*err,(np.asarray([.05,.5,.95])-1)*err).mean(axis=1)
    result={"status":"evaluated","independent_objects":len(objects),"rows":len(y),"per_object":objects,
            "mae":float(np.mean([r["mae"] for r in objects.values()])),
            "rmse":float(np.mean([r["rmse"] for r in objects.values()])),
            "worst_object":max(objects,key=lambda k:objects[k]["mae"]),
            "pinball":float(np.mean([pinball[groups==g].mean() for g in set(groups)]))}
    if normal is not None:
        mu,scale=np.asarray(normal)[valid].T
        bounded=np.clip(y,1e-6,1-1e-6)
        target=np.log(y) if task=="soh" else np.log(bounded/(1-bounded))
        jacobian=np.log(y) if task=="soh" else np.log(bounded*(1-bounded))
        nll=-norm.logpdf(target,mu,scale)+jacobian
        result["nll_original_scale"]=float(np.mean([nll[groups==g].mean() for g in set(groups)]))
    if intervals is not None:
        band=np.asarray(intervals)[valid]
        covered=(y>=band[:,0])&(y<=band[:,1]);width=band[:,1]-band[:,0]
        result["interval_coverage"]=float(np.mean([covered[groups==g].mean() for g in set(groups)]))
        result["trajectory_coverage"]=float(np.mean([covered[groups==g].all() for g in set(groups)]))
        result["interval_mean_width"]=float(width.mean()) if np.isfinite(width).all() else None
        result["interval_status"]="finite" if np.isfinite(width).all() else "unbounded_insufficient_calibration_objects"
    return result


def survival_metrics(arrays,predictions,grid,groups,query_times=None):
    kind=np.asarray(arrays["survival_kind"]);hazard=predictions["hazard"]
    valid=(kind>=0)&np.isfinite(hazard).all(axis=1)
    if not valid.any():return {"status":"unavailable","reason":"no verified physical-time survival targets"}
    lower,upper=arrays["survival_lower"][valid],arrays["survival_upper"][valid];kind=kind[valid];h=hazard[valid]
    valid_groups=np.asarray(groups)[valid]
    times=np.zeros(len(kind)) if query_times is None else np.asarray(query_times)[valid]
    unique,counts=np.unique(valid_groups,return_counts=True);sizes=dict(zip(unique,counts))
    weights=np.asarray([1./sizes[group] for group in valid_groups])
    survival=survival_from_hazard(h);brier=[]
    for i,t in enumerate(grid):
        # Only known survival states are scored. No censored future is treated as failure.
        known=((kind>0)&(upper<=t))|(lower>=t)
        # S(t)=P(T>t): an exact event at t is dead at t, while a
        # right censor or open interval lower boundary at t is alive there.
        alive=(lower>t)|((lower==t)&(kind!=1))
        if known.any():
            error=(survival[known,i]-alive[known])**2
            brier.append({"horizon":float(t),"known_status_brier":float(np.mean([error[valid_groups[known]==g].mean() for g in set(valid_groups[known])])),
                          "n_known":int(known.sum()),"n_known_objects":len(set(valid_groups[known]))})
    comparable=concordant=0.;risk=1-survival[:,-1];pairs=set();by_query={}
    for a in range(len(kind)):
        for b in range(a+1,len(kind)):
            if valid_groups[a]==valid_groups[b] or times[a]!=times[b]:continue
            value=None
            if kind[a]>0 and upper[a]<lower[b]:value=float(risk[a]>risk[b])+.5*float(risk[a]==risk[b])
            elif kind[b]>0 and upper[b]<lower[a]:value=float(risk[b]>risk[a])+.5*float(risk[a]==risk[b])
            if value is not None:
                comparable+=1;concordant+=value;pairs.add(tuple(sorted((str(valid_groups[a]),str(valid_groups[b])))))
                entry=by_query.setdefault(str(float(times[a])),{"comparable_landmark_pairs":0,"concordant_weight":0.})
                entry["comparable_landmark_pairs"]+=1;entry["concordant_weight"]+=value
    for entry in by_query.values():entry["concordance"]=entry["concordant_weight"]/entry["comparable_landmark_pairs"]
    return {"status":"evaluated","independent_objects":len(unique),"rows":len(kind),"nll":censored_nll(h,lower,upper,kind,grid,weights),
            "nll_scope":"equal object weight over its eligible fixed-prefix landmarks","censoring_fraction":float((kind==0).mean()),
            "brier":brier,"brier_scope":"object-averaged observed known status; no IPCW guarantee", "concordance":concordant/comparable if comparable else None,
            "concordance_scope":"same physical-cycle query only; excludes within-object pairs", "concordance_by_query":by_query,
            "comparable_landmark_pairs":int(comparable),"comparable_independent_object_pairs":len(pairs)}


def evaluate_predictions(arrays,predictions,rows,grid,calibration=None):
    domains=np.asarray([domain_key(r) for r in rows]);groups=np.asarray([r["physical_cell_id"] for r in rows])
    result={}
    for domain in sorted(set(domains)):
        ix=np.flatnonzero(domains==domain)
        a={k:v[ix] for k,v in arrays.items()};p={k:v[ix] for k,v in predictions.items()}
        record={"independent_objects":len(set(groups[ix])),"rows":len(ix),"heads":{}}
        for task in ("soh","efficiency"):
            cal=calibration.get(task) if calibration else None
            band=apply_cqr(p[f"{task}_quantiles"],domains[ix],cal) if cal else None
            record["heads"][task]=regression_metrics(a[f"y_{task}"],p[f"{task}_quantiles"],groups[ix],p.get(f"{task}_normal_transformed"),task,band)
        record["heads"]["rul"]=survival_metrics(a,p,grid,groups[ix],[rows[i]["query_time"] for i in ix])
        y=a["y_fault"];prob=p["fault_probability"]
        if calibration and "fault" in calibration:prob=apply_fault_calibration(prob,domains[ix],calibration["fault"])
        valid=(y>=0)&np.isfinite(prob)
        if valid.any() and len(np.unique(y[valid]))==2:
            landmarks=[]
            for g in sorted(set(groups[ix][valid])):
                candidates=np.flatnonzero(valid & (groups[ix]==g))
                landmarks.append(candidates[0])
            landmarks=np.asarray(landmarks,dtype=int)
            independent_y=y[landmarks];independent_probability=prob[landmarks]
            fpr,tpr,threshold=roc_curve(independent_y,independent_probability);reachable=np.flatnonzero(tpr>=.9)
            pos=reachable[0]
            record["heads"]["fault"]={"status":"evaluated","aucpr":float(average_precision_score(independent_y,independent_probability)),
               "snippet_aucpr":float(average_precision_score(y[valid],prob[valid])),"metric_unit":"first frozen landmark per independent vehicle",
               "class_counts":{str(int(c)):int((independent_y==c).sum()) for c in np.unique(independent_y)},
               "false_positive_rate_at_recall_0_9":float(fpr[pos]),"threshold_at_recall_0_9":float(threshold[pos]),
               "calibration_error":calibration_error(independent_probability,independent_y)}
        else:record["heads"]["fault"]={"status":"unavailable","reason":"missing confirmed labels or only one class"}
        result[str(domain)]=record
    return result

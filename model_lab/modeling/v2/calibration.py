"""Finite-sample CQR on independent physical objects, grouped maximum scores."""
from __future__ import annotations
import math
import numpy as np


def fit_cqr(y, quantiles, groups, domains, alpha=.1):
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie in (0,1)")
    y,q = np.asarray(y),np.sort(np.asarray(quantiles),axis=1)
    groups,domains = np.asarray(groups),np.asarray(domains)
    result = {"method":"object_max_cqr", "alpha":alpha, "version":"cqr-v2", "domains":{}}
    for domain in sorted(set(domains)):
        valid = (domains==domain) & np.isfinite(y) & np.isfinite(q).all(axis=1)
        units = sorted(set(groups[valid]))
        scores = [max(0.,float(np.max(np.maximum(q[valid & (groups==g),0] - y[valid & (groups==g)],
                    y[valid & (groups==g)] - q[valid & (groups==g),-1])))) for g in units]
        m = len(scores)
        rank = math.ceil((m+1)*(1-alpha))
        correction = float(np.sort(scores)[rank-1]) if m and rank<=m else None
        result["domains"][str(domain)] = {"independent_objects":m,"resolution":1/(m+1),"rank":rank,
            "correction":correction,"status":"finite" if correction is not None else "insufficient_calibration_objects",
            "object_ids":list(map(str,units)),"coverage_scope":"specified trajectory set under within-domain exchangeability"}
    return result


def apply_cqr(quantiles, domains, calibration):
    q = np.sort(np.asarray(quantiles),axis=1)
    intervals = np.column_stack([q[:,0],q[:,-1]])
    for i,domain in enumerate(domains):
        entry = calibration["domains"].get(str(domain))
        if not entry or entry["correction"] is None:
            intervals[i] = [-np.inf,np.inf]
        else:
            intervals[i] += [-entry["correction"],entry["correction"]]
    return intervals


def calibration_error(probability, labels, bins=10):
    p,y = np.asarray(probability),np.asarray(labels)
    valid = np.isfinite(p) & (y>=0)
    p,y = p[valid],y[valid]
    if not len(p): return None
    result = 0.
    for i in range(bins):
        mask = (p>=i/bins)&(p<(i+1)/bins if i+1<bins else p<=1)
        if mask.any(): result += mask.mean()*abs(p[mask].mean()-y[mask].mean())
    return float(result)


def fit_fault_calibration(probability,labels,groups,domains):
    """Platt calibration on one predetermined first landmark per physical object."""
    from scipy.special import logit
    from sklearn.linear_model import LogisticRegression
    p,y,groups,domains=map(np.asarray,(probability,labels,groups,domains))
    result={"method":"first_object_landmark_platt","version":"fault-platt-v2","domains":{}}
    for domain in sorted(set(domains)):
        selected=[]
        for group in sorted(set(groups[domains==domain])):
            ix=np.flatnonzero((domains==domain)&(groups==group)&np.isfinite(p)&(y>=0))
            if len(ix):selected.append(ix[0])
        selected=np.asarray(selected,dtype=int);target=y[selected]
        counts={str(int(c)):int((target==c).sum()) for c in np.unique(target)}
        entry={"independent_objects":len(selected),"class_counts":counts,"landmark":"first frozen input row per object"}
        if len(np.unique(target))!=2 or min(counts.values(),default=0)<2:
            entry.update(status="insufficient_calibration_class_objects",coef=None,intercept=None)
        else:
            x=logit(np.clip(p[selected],1e-6,1-1e-6))[:,None]
            model=LogisticRegression(C=1.,random_state=0).fit(x,target)
            entry.update(status="fitted",coef=float(model.coef_[0,0]),intercept=float(model.intercept_[0]))
        result["domains"][str(domain)]=entry
    return result


def apply_fault_calibration(probability,domains,calibration):
    from scipy.special import expit,logit
    p=np.asarray(probability).copy()
    for i,domain in enumerate(domains):
        row=calibration["domains"].get(str(domain),{})
        if row.get("status")=="fitted" and np.isfinite(p[i]):p[i]=expit(row["coef"]*logit(np.clip(p[i],1e-6,1-1e-6))+row["intercept"])
    return p

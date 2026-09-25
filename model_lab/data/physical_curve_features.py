"""Deterministic, target-free features from a previously fixed charging window."""
from __future__ import annotations
import numpy as np


def curve_features(flat: np.ndarray) -> np.ndarray:
    """Voltage-local charge increments retain shape, unlike a single Ah ratio.

    Input: 64 x (elapsed minutes, observed incremental Ah, current A,
    relative temperature C), followed by finite masks. No fitted statistics and
    no labels are used. Missing temperatures stay NaN for train-only imputation.
    """
    a = np.asarray(flat, dtype=np.float64)[:, :256].reshape(-1,64,4)
    idx = np.rint(np.linspace(0,63,17)).astype(int)
    q = a[:,idx,1]
    dt = np.diff(a[:,idx,0],axis=1)
    dq = np.diff(q,axis=1)
    total = q[:,-1] - q[:,0]
    safe = np.maximum(total,1e-8)
    log_dq = np.log(np.maximum(dq,1e-8))
    fractions = dq / safe[:,None]
    log_dt = np.log(np.maximum(dt,1e-8))
    temp = a[:,idx[1:],3]
    current = a[:,:,2]
    summary = np.column_stack([np.log(safe),np.log(np.maximum(a[:,-1,0],1e-8)),np.nanmean(current,axis=1),np.nanstd(current,axis=1),np.isfinite(a[:,:,3]).mean(axis=1)])
    return np.concatenate([log_dq,fractions,log_dt,temp,summary],axis=1).astype(np.float32)

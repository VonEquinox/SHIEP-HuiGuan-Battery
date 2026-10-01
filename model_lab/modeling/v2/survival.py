"""Discrete hazard likelihood for exact, right-, and interval-censored outcomes."""
from __future__ import annotations
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit


def survival_from_hazard(hazard: np.ndarray) -> np.ndarray:
    h = np.asarray(hazard, dtype=float)
    if not np.isfinite(h).all() or np.any((h < 0) | (h > 1)):
        raise ValueError("hazards must lie in [0,1]")
    return np.cumprod(1 - h, axis=-1)


def event_bins(lower: np.ndarray, upper: np.ndarray, kind: np.ndarray, grid: np.ndarray):
    grid = np.asarray(grid)
    if np.any(np.diff(grid) <= 0) or grid[0] <= 0:
        raise ValueError("positive, strictly increasing survival grid required")
    # S(c) includes every grid endpoint <= c. Events are coarse interval observations.
    l = np.searchsorted(grid, lower, side="right")
    u = np.searchsorted(grid, upper, side="left") + 1
    exact = kind == 1
    l[exact] = np.maximum(0, u[exact] - 1)
    return np.clip(l, 0, len(grid)), np.clip(u, 0, len(grid))


def censored_nll(hazard, lower, upper, kind, grid, weights=None):
    """kind=0 right censored, 1 event, 2 interval (lower < T <= upper), -1 missing."""
    h = np.clip(np.asarray(hazard), 1e-8, 1 - 1e-8)
    s = np.concatenate([np.ones((len(h), 1)), survival_from_hazard(h)], axis=1)
    l, u = event_bins(np.asarray(lower), np.asarray(upper), np.asarray(kind), np.asarray(grid))
    rows = np.arange(len(h))
    likelihood = np.where(np.asarray(kind) == 0, s[rows, l], s[rows, l] - s[rows, u])
    # Out-of-range events are right censored at the grid end, never clipped into a fake event.
    beyond = (np.asarray(kind) > 0) & (np.asarray(upper) > grid[-1])
    likelihood[beyond] = s[beyond, -1]
    valid = np.asarray(kind) >= 0
    w = np.ones(len(h)) if weights is None else np.asarray(weights)
    return float(np.sum(-np.log(np.clip(likelihood[valid], 1e-12, 1)) * w[valid]) / max(w[valid].sum(), 1e-12))


def summarize_survival(hazard, grid, horizon=None):
    s = survival_from_hazard(np.asarray(hazard).reshape(-1))
    crossings = np.flatnonzero(s <= .5)
    if horizon is None:
        horizon = float(grid[-1])
    pos = np.searchsorted(grid, horizon, side="right") - 1
    return {"grid": list(map(float, grid)), "survival": s.tolist(),
            "median": float(grid[crossings[0]]) if len(crossings) else None,
            "median_status": "within_support" if len(crossings) else "exceeds_prediction_range",
            "horizon": horizon, "threshold_probability": float(1 - s[pos]) if pos >= 0 else 0.}


class DiscreteHazardBaseline:
    """Censor-aware linear hazard strong interpretable survival baseline."""
    def __init__(self, grid, regularization=.01):
        self.grid = np.asarray(grid, dtype=float)
        self.regularization = regularization

    def fit(self, x, lower, upper, kind, sample_weight=None):
        x = np.asarray(x)
        n_features = x.shape[1]
        def objective(theta):
            h = expit(x @ theta[:n_features, None] + theta[n_features:])
            return censored_nll(h, lower, upper, kind, self.grid, sample_weight) + self.regularization * np.mean(theta ** 2)
        result = minimize(objective, np.r_[np.zeros(n_features), np.full(len(self.grid), -3.)], method="L-BFGS-B", options={"maxiter":200})
        if not np.isfinite(result.fun):
            raise ValueError("survival fitting failed")
        self.coef = result.x[:n_features]
        self.intercept = result.x[n_features:]
        self.fit_status = {"success": bool(result.success), "message": str(result.message), "nll_regularized": float(result.fun)}
        return self

    def predict_hazard(self, x):
        return expit(np.asarray(x) @ self.coef[:, None] + self.intercept)

    def to_dict(self):
        return {"grid": self.grid.tolist(), "coef": self.coef.tolist(), "intercept": self.intercept.tolist(), "fit_status": self.fit_status}

    @classmethod
    def from_dict(cls, obj):
        model = cls(obj["grid"])
        model.coef = np.asarray(obj["coef"])
        model.intercept = np.asarray(obj["intercept"])
        model.fit_status = obj["fit_status"]
        return model

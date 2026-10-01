"""M1: per-source NGBoost/quantile trees, censor-aware survival, and fault heads.

Models export numerical tree arrays to JSON; no joblib/pickle deserialization.
"""
from __future__ import annotations
import numpy as np
from scipy.special import expit, logit
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
from .survival import DiscreteHazardBaseline
from .safe_numeric import validate_baseline_dict,validate_gb_dict


def object_weights(groups):
    groups = np.asarray(groups)
    unique, counts = np.unique(groups, return_counts=True)
    sizes = dict(zip(unique, counts))
    w = np.asarray([1. / sizes[g] for g in groups])
    return w / w.mean()


def tree_to_dict(estimator):
    tree = estimator.tree_
    return {"children_left": tree.children_left.tolist(), "children_right": tree.children_right.tolist(),
            "feature": tree.feature.tolist(), "threshold": tree.threshold.tolist(),
            "value": tree.value.reshape(tree.node_count, -1).tolist()}


def predict_tree(tree, x):
    x = np.asarray(x)
    nodes = np.zeros(len(x), dtype=int)
    left, right = np.asarray(tree["children_left"]), np.asarray(tree["children_right"])
    features, thresholds = np.asarray(tree["feature"]), np.asarray(tree["threshold"])
    while True:
        active = left[nodes] >= 0
        if not active.any():
            break
        idx = np.flatnonzero(active)
        current = nodes[idx]
        go_left = x[idx, features[current]] <= thresholds[current]
        nodes[idx] = np.where(go_left, left[current], right[current])
    return np.asarray(tree["value"])[nodes, 0]


def gb_to_dict(model):
    return {"kind": "gradient_boosting", "learning_rate": float(model.learning_rate),
            "initial": float(np.asarray(model.init_.constant_).ravel()[0]),
            "trees": [tree_to_dict(t[0]) for t in model.estimators_]}


def predict_gb(model, x):
    x=np.asarray(x)
    if x.ndim!=2 or not np.isfinite(x).all():raise ValueError("finite two-dimensional features required")
    validate_gb_dict(model,n_features=x.shape[1])
    value = np.full(len(x), model["initial"])
    for tree in model["trees"]:
        value += model["learning_rate"] * predict_tree(tree, x)
    return value


def fit_ngboost(x, y, weights, seed, n_estimators):
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    from sklearn.tree import DecisionTreeRegressor
    model = NGBRegressor(Dist=Normal, Base=DecisionTreeRegressor(max_depth=2, min_samples_leaf=3),
                         n_estimators=n_estimators, learning_rate=.03, random_state=seed, verbose=False)
    model.fit(x, y, sample_weight=weights)
    result = {"kind":"ngboost_normal", "initial": np.asarray(model.init_params).tolist(),
              "learning_rate":float(model.learning_rate), "scalings":np.asarray(model.scalings).tolist(),
              "columns":[np.asarray(c).tolist() for c in model.col_idxs],
              "trees":[[tree_to_dict(t) for t in iteration] for iteration in model.base_models]}
    # Verify exported numerical recipe against live inference before returning it.
    expected = model.pred_dist(x[:min(16,len(x))])
    actual = predict_ngboost(result, x[:min(16,len(x))])
    if not np.allclose(expected.loc, actual[:,0], atol=1e-7) or not np.allclose(expected.scale, actual[:,1], atol=1e-7):
        raise ValueError("NGBoost numerical serialization mismatch")
    return result


def predict_ngboost(model, x):
    params = np.tile(model["initial"], (len(x),1)).astype(float)
    for scale, columns, iteration in zip(model["scalings"],model["columns"],model["trees"]):
        residual = np.column_stack([predict_tree(t,np.asarray(x)[:,columns]) for t in iteration])
        params -= model["learning_rate"] * scale * residual
    return np.column_stack([params[:,0],np.exp(params[:,1])])


def transform(y, task):
    if task == "soh":
        if np.any(y <= 0):
            raise ValueError("positive SOH required")
        return np.log(y)
    if task == "efficiency":
        if np.any((y <= 0) | (y > 1)):
            raise ValueError("efficiency labels outside (0,1]")
        return logit(np.clip(y,1e-6,1-1e-6))
    return y


def inverse(y, task):
    return np.exp(y) if task == "soh" else expit(y) if task == "efficiency" else y


class DomainBaseline:
    def __init__(self, seed=0, n_estimators=100, survival_grid=None, use_ngboost=True, min_survival_objects=1):
        self.seed, self.n_estimators, self.use_ngboost = seed,n_estimators,use_ngboost
        if type(min_survival_objects) is not int or min_survival_objects<1:raise ValueError("positive integer independent survival-object requirement")
        self.min_survival_objects=int(min_survival_objects)
        self.grid = survival_grid or [50,100,150,200,300,400,600,800,1000]
        self.models = {}

    def fit(self, arrays, rows):
        domain_key = lambda r: "::".join(str(r.get(k)) for k in ("source_id","chemistry","protocol_id"))
        domains = sorted({domain_key(r) for r in rows})
        for domain in domains:
            ix = np.flatnonzero([domain_key(r) == domain for r in rows])
            x = arrays["features"][ix]
            weights = object_weights([rows[i]["physical_cell_id"] for i in ix])
            models = {}
            for task in ("soh","efficiency"):
                y = arrays[f"y_{task}"][ix]
                valid = np.isfinite(y)
                if valid.sum() < 8:
                    models[task] = {"support":"unsupported","reason":"too_few_legal_labels"}
                    continue
                label = transform(y[valid],task)
                models[task] = {"support":"supported", "quantiles":{}}
                for q in (.05,.5,.95):
                    estimator = GradientBoostingRegressor(loss="quantile",alpha=q,random_state=self.seed,
                        n_estimators=self.n_estimators,max_depth=2,min_samples_leaf=3)
                    estimator.fit(x[valid],label,sample_weight=weights[valid])
                    exported = gb_to_dict(estimator)
                    if not np.allclose(estimator.predict(x[valid][:8]),predict_gb(exported,x[valid][:8]),atol=1e-8):
                        raise ValueError("quantile numerical serialization mismatch")
                    models[task]["quantiles"][str(q)] = exported
                if self.use_ngboost:
                    models[task]["distribution"] = fit_ngboost(x[valid],label,weights[valid],self.seed,self.n_estimators)
            kind = arrays["survival_kind"][ix]
            valid = kind >= 0
            independent_survival_objects=len({rows[i]["physical_cell_id"] for i in ix[valid]})
            models["survival_support"]={"independent_training_objects":independent_survival_objects,
                "minimum_training_objects":self.min_survival_objects,"status":"unsupported",
                "reason":"no_verified_physical_time_threshold_labels" if not independent_survival_objects else "too_few_independent_survival_objects"}
            if independent_survival_objects>=self.min_survival_objects:
                survival = DiscreteHazardBaseline(self.grid).fit(x[valid],arrays["survival_lower"][ix][valid],
                    arrays["survival_upper"][ix][valid],kind[valid],weights[valid])
                models["survival"] = survival.to_dict()
                models["survival_support"].update(status="supported",reason=None)
            fault = arrays["y_fault"][ix]
            valid = fault >= 0
            if valid.sum() >= 8 and len(np.unique(fault[valid])) == 2:
                clf = GradientBoostingClassifier(random_state=self.seed,n_estimators=self.n_estimators,max_depth=2)
                clf.fit(x[valid],fault[valid],sample_weight=weights[valid])
                priors = clf.init_.class_prior_
                models["fault"] = {"kind":"binary_gradient_boosting", "initial":float(np.log(priors[1]/priors[0])),
                    "learning_rate":float(clf.learning_rate),"trees":[tree_to_dict(t[0]) for t in clf.estimators_]}
            self.models[domain] = models
        return self

    def predict(self, arrays, rows):
        output = {"soh_quantiles":np.full((len(rows),3),np.nan),"efficiency_quantiles":np.full((len(rows),3),np.nan),
                  "hazard":np.full((len(rows),len(self.grid)),np.nan),"fault_probability":np.full(len(rows),np.nan)}
        domain_key = lambda r: "::".join(str(r.get(k)) for k in ("source_id","chemistry","protocol_id"))
        for domain, models in self.models.items():
            ix = np.flatnonzero([domain_key(r) == domain for r in rows])
            if not len(ix): continue
            x = arrays["features"][ix]
            for task in ("soh","efficiency"):
                model = models[task]
                if model["support"] != "supported": continue
                quantiles = np.column_stack([inverse(predict_gb(model["quantiles"][str(q)],x),task) for q in (.05,.5,.95)])
                output[f"{task}_quantiles"][ix] = np.sort(quantiles,axis=1)
                if "distribution" in model:
                    output.setdefault(f"{task}_normal_transformed",np.full((len(rows),2),np.nan))[ix] = predict_ngboost(model["distribution"],x)
            if "survival" in models:
                output["hazard"][ix] = DiscreteHazardBaseline.from_dict(models["survival"]).predict_hazard(x)
            if "fault" in models:
                output["fault_probability"][ix] = expit(predict_gb(models["fault"],x))
        return output

    def to_dict(self):
        return {"kind":"M1", "seed":self.seed,"survival_grid":self.grid,"min_survival_objects":self.min_survival_objects,"domains":self.models}

    @classmethod
    def from_dict(cls,obj,*,n_features=None):
        validate_baseline_dict(obj,n_features=n_features)
        model = cls(obj["seed"],survival_grid=obj["survival_grid"],min_survival_objects=obj.get("min_survival_objects",1))
        model.models = obj["domains"]
        return model

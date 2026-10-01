"""Safe V2 model-package inference and explicit applicability profiles."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from .contracts import PREDICTION_SCHEMA,check_query,unsupported_profile,sha256_file,domain_key
from .features import preprocess
from .baselines import DomainBaseline
from .multitask import MultiTaskModel
from .calibration import apply_cqr,apply_fault_calibration
from .survival import summarize_survival


class SafePackage:
    def __init__(self,path):
        self.path=Path(path);self.manifest=json.loads((self.path/"manifest.json").read_text())
        if self.manifest.get("format")!="battery_model_safe_v2":raise ValueError("unknown package format")
        self.model_version=self.manifest.get("model_version")
        for name,digest in self.manifest["files"].items():
            if Path(name).name!=name:raise ValueError("package path traversal")
            if sha256_file(self.path/name)!=digest:raise ValueError("package integrity failure")
        self.record=json.loads((self.path/"run.json").read_text())
        self.model_version=self.model_version or self.record["run_id"]
        if self.record["family"]=="M1":self.model=DomainBaseline.from_dict(json.loads((self.path/"model.json").read_text()))
        else:self.model=MultiTaskModel.load(self.record["spec"],self.path/"weights.npz",self.record["seed"],self.record["survival_grid"],self.record["label_support"],self.record.get("label_support_by_domain"))
        self.calibration=json.loads((self.path/"calibration.json").read_text()) if (self.path/"calibration.json").exists() else {}

    def predict(self,query,arrays):
        reasons=check_query(query,self.record["support_domains"])
        if reasons:return unsupported_profile(query,";".join(reasons),self.model_version)
        x=np.asarray(arrays["features"])
        if x.ndim!=2 or len(x)!=1 or x.shape[1]!=len(self.record["preprocessor"]["feature_mean"]) or not np.isfinite(x).all():
            return unsupported_profile(query,"invalid_features",self.model_version)
        if np.asarray(arrays["sequences"]).shape[:1]!=(1,) or not np.isfinite(arrays["sequences"]).all():
            return unsupported_profile(query,"invalid_sequence",self.model_version)
        arrays={**arrays,"domain":np.asarray([self.record["domain_index"]["::".join(str(query.get(k)) for k in ("source_id","chemistry","protocol_id"))]],dtype=np.int64)}
        transformed=preprocess(arrays,self.record["preprocessor"],self.record["ablation"]=="no_history")
        predictions=self.model.predict(transformed,[query])
        mean=np.asarray(self.record["preprocessor"]["feature_mean"]);scale=np.asarray(self.record["preprocessor"]["feature_scale"])
        score=float(np.linalg.norm((x[0]-mean)/scale)/np.sqrt(len(mean)))
        profile={"schema_version":PREDICTION_SCHEMA,"model_version":self.model_version,"data_namespace":query["data_namespace"],
                 "query":query,"support":{"status":"supported","reasons":[],"ood_score":{"kind":"uncalibrated_feature_distance","value":score}},"heads":{}}
        allowed=query.get("allowed_heads",["soh","rul","threshold_risk","efficiency","fault"])
        for task in ("soh","efficiency"):
            q=predictions[f"{task}_quantiles"][0]
            entry={"support":"unsupported","target_definition":self.record.get("target_definitions_by_domain",{}).get(domain_key(query),self.record["target_definitions"]).get(task),"unit":"ratio", "horizon":None,
                   "distribution_kind":None,"calibration_version":None,"evidence_refs":query.get("evidence_refs",[])}
            if task in allowed and np.isfinite(q).all():
                entry.update(support="supported",distribution_kind="quantiles",quantiles={"0.05":float(q[0]),"0.5":float(q[1]),"0.95":float(q[2])})
                params=predictions.get(f"{task}_normal_transformed")
                if params is not None and np.isfinite(params[0]).all():
                    normal_kind="lognormal" if task=="soh" else "logit_normal"
                    normal_params={"location":float(params[0,0]),"scale":float(params[0,1])}
                    if self.record["family"]=="M1":
                        entry["alternative_distribution"]={"model":"NGBoost", "distribution_kind":normal_kind,"params":normal_params,"calibration_version":None}
                    else:
                        entry.update(distribution_kind=normal_kind,params=normal_params)
                if task in self.calibration:
                    cal=self.calibration[task];interval=apply_cqr(q[None,:],[domain_key(query)],cal)[0]
                    entry.update(calibration_version=cal["version"],calibrated_interval={"lower":float(interval[0]) if np.isfinite(interval[0]) else None,
                        "upper":float(interval[1]) if np.isfinite(interval[1]) else None,"nominal_coverage":1-cal["alpha"],
                        "status":cal["domains"].get(domain_key(query),{}).get("status","uncalibrated_domain"),
                        "scope":"within-domain object exchangeability; unbounded if too few calibration objects"})
            else:entry["reason"]="head_not_authorized" if task not in allowed else "missing_legal_training_labels"
            profile["heads"][task]=entry
        hazard=predictions["hazard"][0]
        if np.isfinite(hazard).all() and ("rul" in allowed or "threshold_risk" in allowed):
            summary=summarize_survival(hazard,self.record["survival_grid"],query.get("horizon"))
            base={"support":"supported","target_definition":self.record["target_definitions"].get("rul"),"unit":"physical_cycle", "horizon":summary["horizon"],
                  "calibration_version":None,"evidence_refs":query.get("evidence_refs",[])}
            profile["heads"]["rul"]={**base,"distribution_kind":"discrete_survival","params":summary}
            profile["heads"]["threshold_risk"]={**base,"distribution_kind":"bernoulli","params":{"probability":summary["threshold_probability"]}}
            for task in ("rul", "threshold_risk"):
                if task not in allowed:
                    profile["heads"][task] = {"support":"unsupported","reason":"head_not_authorized", "target_definition":None, "unit":None,"horizon":None,"distribution_kind":None,"calibration_version":None,"evidence_refs":[]}
        else:
            for task in ("rul","threshold_risk"):
                profile["heads"][task]={"support":"unsupported","reason":"no_verified_physical_time_threshold_labels","target_definition":None,
                    "unit":None,"horizon":None,"distribution_kind":None,"calibration_version":None,"evidence_refs":[]}
        prob=predictions["fault_probability"][0]
        fault_calibration=self.calibration.get("fault")
        if fault_calibration:prob=apply_fault_calibration([prob],[domain_key(query)],fault_calibration)[0]
        profile["heads"]["fault"]={"support":"supported" if "fault" in allowed and np.isfinite(prob) else "unsupported",
            "reason":None if "fault" in allowed and np.isfinite(prob) else "missing_confirmed_fault_labels",
            "target_definition":self.record["target_definitions"].get("fault"),"unit":"probability","horizon":None,
            "distribution_kind":"bernoulli" if "fault" in allowed and np.isfinite(prob) else None,"params":{"probability":float(prob)} if "fault" in allowed and np.isfinite(prob) else None,
            "calibration_version":fault_calibration["version"] if fault_calibration and fault_calibration["domains"].get(domain_key(query),{}).get("status")=="fitted" else None,
            "calibration_status":fault_calibration["domains"].get(domain_key(query),{}).get("status") if fault_calibration else "uncalibrated", "evidence_refs":[]}
        return profile


def load_package(path):return SafePackage(path)

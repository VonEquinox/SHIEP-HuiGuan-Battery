"""Report every preregistered seed, including failed and unavailable heads."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
from .common import write_json


def summarize(directory,split="final"):
    directory=Path(directory);entries=[];buckets={}
    for path in sorted(directory.glob("*/run.json")):
        record=json.loads(path.read_text());metric_path=path.parent/f"{split}_metrics.json"
        item={"run_id":record["run_id"],"family":record["family"],"ablation":record["ablation"],"seed":record["seed"],"status":record["status"]}
        if not metric_path.exists():item.update(evaluation_status="unavailable",reason="split_not_executed")
        else:
            metric=json.loads(metric_path.read_text());metrics=metric.get("metrics",metric);item["evaluation_status"]="evaluated";item["metrics"]=metrics
            for domain,value in metrics.items():
                for task,head in value["heads"].items():
                    key=(record["family"],record["ablation"],domain,task)
                    bucket=buckets.setdefault(key,{"seeds":[],"independent_objects":value["independent_objects"],"metrics":{}})
                    bucket["seeds"].append(record["seed"])
                    for name,val in head.items():
                        if isinstance(val,(int,float)) and name not in ("rows","independent_objects"):
                            bucket["metrics"].setdefault(name,[]).append(float(val))
        entries.append(item)
    aggregate=[]
    for (family,ablation,domain,task),bucket in buckets.items():
        aggregate.append({"family":family,"ablation":ablation,"domain":domain,"head":task,"seeds":bucket["seeds"],
                          "independent_objects":bucket["independent_objects"],
                          "metrics":{name:{"mean":float(np.mean(vals)),"standard_deviation":float(np.std(vals,ddof=1)) if len(vals)>1 else 0.,"n_seeds":len(vals)} for name,vals in bucket["metrics"].items()}})
    return {"split":split,"runs":entries,"aggregate":aggregate,"selection":"all preregistered seeds; no best-seed replacement",
            "limitations":["Head support and target definitions are source-specific; unavailable labels never become synthetic supervision", "MATR summary-only views do not establish early-cycle curve or physical RUL transfer", "Vehicle anomaly labels do not identify individual cell root causes", "CQR intervals are unbounded when too few independent calibration objects", "No protected XJTU holdout is included; final results are not used for further selection"]}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--directory",required=True);p.add_argument("--split",choices=["dev","final"],default="final")
    a=p.parse_args();result=summarize(a.directory,a.split);write_json(Path(a.directory)/f"{a.split}_summary.json",result);print(str(Path(a.directory)/f"{a.split}_summary.json"))
if __name__=="__main__":main()

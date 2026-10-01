"""Fit independent-object CQR using calibration split only."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from model_lab.modeling.v2.contracts import load_dataset,sha256_file,domain_key
from model_lab.modeling.v2.features import preprocess
from model_lab.modeling.v2.calibration import fit_cqr,fit_fault_calibration
from .common import get_model,subset,write_json,resolve_dataset_path


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--run-id",required=True);parser.add_argument("--alpha",type=float,default=.1)
    args=parser.parse_args();run=Path(args.run_id);record,model=get_model(run)
    if record["status"] not in ("trained","calibrated"):raise ValueError("run is not trained")
    if (run/"calibration.json").exists():raise ValueError("calibration is immutable; create another experiment")
    manifest,arrays=load_dataset(resolve_dataset_path(record))
    if sha256_file(resolve_dataset_path(record))!=record["dataset_sha256"]:raise ValueError("dataset changed")
    transformed=preprocess(arrays,record["preprocessor"],record["ablation"]=="no_history")
    cal,rows=subset(transformed,manifest["rows"],"calibration")
    if not rows:raise ValueError("no independent calibration objects")
    prediction=model.predict(cal,rows);calibration={}
    for task in ("soh","efficiency"):
        calibration[task]=fit_cqr(cal[f"y_{task}"],prediction[f"{task}_quantiles"],
            [r["physical_cell_id"] for r in rows],[domain_key(r) for r in rows],args.alpha)
    calibration["fault"]=fit_fault_calibration(prediction["fault_probability"],cal["y_fault"],[r["physical_cell_id"] for r in rows],[domain_key(r) for r in rows])
    write_json(run/"calibration.json",calibration)
    record.update(status="calibrated",calibration_accessed=True,calibration_sha256=sha256_file(run/"calibration.json"))
    write_json(run/"run.json",record)
    print(json.dumps({"run_id":record["run_id"],"calibration":calibration},ensure_ascii=False))

if __name__=="__main__":main()

"""Evaluate frozen dev/calibration or explicitly released final split once."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from model_lab.modeling.v2.contracts import load_dataset,sha256_file
from model_lab.modeling.v2.features import preprocess
from model_lab.modeling.v2.metrics import evaluate_predictions
from .common import get_model,subset,write_json,resolve_dataset_path


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--run-id",required=True)
    parser.add_argument("--split",choices=["dev","calibration","final"],default="dev")
    parser.add_argument("--manifest",help="Independently released final bundle; frozen training IDs must match")
    parser.add_argument("--authorize-final",action="store_true",help="Confirm development frozen before final comparison")
    args=parser.parse_args();run=Path(args.run_id);record,model=get_model(run)
    if args.split=="final" and record.get("config",{}).get("development_only"):
        raise ValueError("development-only proof cannot evaluate final")
    if args.split=="final" and not args.authorize_final:raise ValueError("final evaluation requires frozen-recipe authorization")
    if args.split=="final" and (run/"final_metrics.json").exists():raise ValueError("final comparison already consumed")
    path=Path(args.manifest) if args.manifest else resolve_dataset_path(record);manifest,arrays=load_dataset(path)
    if not args.manifest and sha256_file(path)!=record["dataset_sha256"]:raise ValueError("dataset changed")
    if args.manifest:
        train_objects=sorted({r["physical_cell_id"] for r in manifest["rows"] if r["split"]=="train"})
        if train_objects!=record["train_objects"]:raise ValueError("final manifest changed frozen training objects")
    transformed=preprocess(arrays,record["preprocessor"],record["ablation"]=="no_history")
    selected,rows=subset(transformed,manifest["rows"],args.split)
    if not rows:raise ValueError("requested split has not been ingested/released")
    predictions=model.predict(selected,rows)
    calibration=json.loads((run/"calibration.json").read_text()) if (run/"calibration.json").exists() else None
    result={"run_id":record["run_id"],"split":args.split,"data_namespace":manifest["data_namespace"],
            "dataset_sha256":sha256_file(path),"model_sha256":record["model_sha256"],
            "metrics":evaluate_predictions(selected,predictions,rows,record["survival_grid"],calibration),
            "supported_protocols":record["support_domains"],"no_model_selection_on_this_split":args.split=="final"}
    write_json(run/f"{args.split}_metrics.json",result)
    if args.split=="final":record["final_accessed"]=True;write_json(run/"run.json",record)
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":main()

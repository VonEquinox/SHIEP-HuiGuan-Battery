"""Train the preregistered three-seed matrix without touching final-test labels."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
import traceback
import numpy as np
import yaml
from model_lab.modeling.v2.contracts import load_dataset,sha256_file
from model_lab.modeling.v2.features import fit_preprocessor,preprocess
from model_lab.modeling.v2.baselines import DomainBaseline
from model_lab.modeling.v2.multitask import MultiTaskModel
from model_lab.modeling.v2.metrics import evaluate_predictions
from .common import write_json,code_version,subset


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--config",required=True)
    parser.add_argument("--family",choices=["M1","M2"]);parser.add_argument("--seed",type=int)
    parser.add_argument("--ablation",choices=["joint","no_domain_adapter","no_history","single_task"])
    args=parser.parse_args();config=yaml.safe_load(Path(args.config).read_text())
    manifest,arrays=load_dataset(config["dataset_manifest"]);rows=manifest["rows"]
    train_ix=np.flatnonzero([r["split"]=="train" for r in rows])
    transform=fit_preprocessor(arrays["features"],arrays["sequences"],arrays["sequence_mask"],train_ix)
    families=[args.family] if args.family else config.get("families",["M1","M2"])
    seeds=[args.seed] if args.seed is not None else config.get("seeds",[0,1,2])
    output=Path(config["output_dir"]);output.mkdir(parents=True,exist_ok=True)
    prereg={"seeds":config.get("seeds",[0,1,2]),"ablations":config.get("ablations",["joint","no_domain_adapter","no_history","single_task"]),
            "dataset_manifest_sha256":sha256_file(Path(config["dataset_manifest"])),"config_sha256":sha256_file(Path(args.config)),
            "code":code_version(),"selection_split":"dev","calibration_split":"calibration","final_split":"final",
            "M0":"immutable existing V1; use original support only, no protected-cell scoring"}
    preregpath=output/"preregistration.json"
    if preregpath.exists() and json.loads(preregpath.read_text())["config_sha256"]!=prereg["config_sha256"]:
        raise ValueError("frozen experiment config changed; use a new output directory")
    write_json(preregpath,prereg)
    all_results=[]
    for family in families:
        ablations=["joint"] if family=="M1" else ([args.ablation] if args.ablation else config.get("ablations",["joint","no_domain_adapter","no_history","single_task"]))
        for ablation in ablations:
            for seed in seeds:
                run_id=f"{family}_{ablation}_seed{seed}";run=output/run_id
                if (run/"run.json").exists():
                    raise ValueError(f"existing run is immutable: {run}")
                run.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
                record={"run_id":run_id,"family":family,"ablation":ablation,"seed":seed,"status":"training",
                        "dataset_manifest":str(Path(config["dataset_manifest"]).resolve()),"dataset_sha256":prereg["dataset_manifest_sha256"],
                        "feature_schema":manifest["schema_version"],"domain_index":manifest["domains"],"target_definitions":manifest["target_definitions"],
                        "target_definitions_by_domain":manifest.get("target_definitions_by_domain",{}),
                        "data_namespace":manifest["data_namespace"],"survival_grid":config.get("survival_grid",[50,100,150,200,300,400,600,800,1000]),
                        "preprocessor":transform,"code":prereg["code"],"config":config,
                        "support_domains":[dict(source_id=s,chemistry=c,protocol_id=p) for s,c,p in sorted({(r["source_id"],r["chemistry"],r["protocol_id"]) for r in rows if r["split"]=="train"})],
                        "train_objects":sorted({r["physical_cell_id"] for r in rows if r["split"]=="train"}),
                        "dev_objects":sorted({r["physical_cell_id"] for r in rows if r["split"]=="dev"}),
                        "final_accessed":False,"calibration_accessed":False}
                write_json(run/"run.json",record)
                try:
                    transformed=preprocess(arrays,transform,no_history=ablation=="no_history")
                    tr,trrows=subset(transformed,rows,"train");dv,dvrows=subset(transformed,rows,"dev")
                    if family=="M1":
                        model=DomainBaseline(seed,config.get("m1_estimators",100),record["survival_grid"],config.get("ngboost",True)).fit(tr,trrows)
                        write_json(run/"model.json",model.to_dict())
                    else:
                        spec={"n_features":tr["features"].shape[1],"n_domains":len(manifest["domains"]),"width":128,"adapter_width":32,
                              "domain_adapter":ablation!="no_domain_adapter","history":ablation!="no_history","single_task":ablation=="single_task"}
                        model=MultiTaskModel(spec,seed,record["survival_grid"]).fit(tr,trrows,config.get("epochs",12),config.get("batch_size",8),config.get("learning_rate",.001),config.get("loss_contract","available_task_mean_v1"),config.get("task_weights"))
                        model.save(run/"weights.npz");record.update(spec=spec,label_support=model.label_support,label_support_by_domain=model.label_support_by_domain,training_history=model.history)
                    prediction_started=time.perf_counter();predictions=model.predict(dv,dvrows)
                    record["dev_inference_ms_per_row"]=(time.perf_counter()-prediction_started)*1000/max(1,len(dvrows))
                    metrics=evaluate_predictions(dv,predictions,dvrows,record["survival_grid"])
                    write_json(run/"dev_metrics.json",metrics)
                    record.update(status="trained",elapsed_seconds=time.perf_counter()-started,
                                  model_sha256=sha256_file(run/("model.json" if family=="M1" else "weights.npz")))
                    all_results.append({"run_id":run_id,"status":"trained","dev_metrics":metrics})
                    print(f"{run_id}: trained; {len(record['train_objects'])} train objects; final untouched",flush=True)
                except Exception as error:
                    record.update(status="failed",error=str(error),traceback=traceback.format_exc(),elapsed_seconds=time.perf_counter()-started)
                    all_results.append({"run_id":run_id,"status":"failed","error":str(error)})
                    print(f"{run_id}: FAILED {error}",flush=True)
                write_json(run/"run.json",record)
    write_json(output/"matrix.json",{"runs":all_results,"preregistration":prereg,"namespace":manifest["data_namespace"]})
    if any(r["status"]=="failed" for r in all_results):raise SystemExit(1)

if __name__=="__main__":main()

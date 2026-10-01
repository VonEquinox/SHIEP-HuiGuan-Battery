"""Export a checksummed JSON/NPZ package and prove reload numerical equivalence."""
from __future__ import annotations
import argparse,json,shutil
from pathlib import Path
import numpy as np
from model_lab.modeling.v2.contracts import load_dataset,sha256_file
from model_lab.modeling.v2.features import preprocess
from model_lab.modeling.v2.prediction import load_package
from .common import get_model,subset,write_json,resolve_dataset_path


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--run-id",required=True);parser.add_argument("--out",required=True)
    args=parser.parse_args();run=Path(args.run_id);out=Path(args.out)
    if out.exists():raise ValueError("export directory must be new")
    record,model=get_model(run)
    if record["status"] not in ("trained","calibrated"):raise ValueError("only completed runs export")
    out.mkdir(parents=True)
    names=["run.json","model.json" if record["family"]=="M1" else "weights.npz"]
    if (run/"calibration.json").exists():names.append("calibration.json")
    for name in names:shutil.copyfile(run/name,out/name)
    manifest={"format":"battery_model_safe_v2","model_version":f"{run.parent.name}:{record['run_id']}","feature_schema":record["feature_schema"],
              "data_namespace":record["data_namespace"],"files":{name:sha256_file(out/name) for name in names},
              "support_domains":record["support_domains"],"target_definitions":record["target_definitions"],"reload_verified":False}
    write_json(out/"manifest.json",manifest)
    package=load_package(out)
    dataset,arrays=load_dataset(resolve_dataset_path(record));dv,rows=subset(arrays,dataset["rows"],"dev")
    if not rows:raise ValueError("independent reload sample required")
    live=model.predict(preprocess(dv,record["preprocessor"],record["ablation"]=="no_history"),rows)
    reloaded=package.model.predict(preprocess(dv,record["preprocessor"],record["ablation"]=="no_history"),rows)
    for key,value in live.items():
        if not np.allclose(value,reloaded[key],equal_nan=True,atol=1e-7):raise ValueError(f"reload mismatch: {key}")
    sample=rows[0];query={**sample,"feature_schema":record["feature_schema"],"data_namespace":record["data_namespace"],"allowed_heads":["soh","rul","threshold_risk","efficiency","fault"]}
    sample_arrays={k:dv[k][:1] for k in ("features","sequences","sequence_mask","domain")}
    np.savez_compressed(out/"reload_sample.npz",**sample_arrays)
    write_json(out/"reload_sample_query.json",query)
    profile=package.predict(query,sample_arrays)
    write_json(out/"reload_verification.json",{"passed":True,"dev_rows":len(rows),"absolute_tolerance":1e-7,"heads":sorted(live),"sample_profile":profile})
    manifest["files"].update({"reload_sample.npz":sha256_file(out/"reload_sample.npz"),"reload_sample_query.json":sha256_file(out/"reload_sample_query.json")})
    # Ship one real, label-free development input per observed domain. This
    # lets a fresh checkout inspect source-specific head masking without raw
    # data or a sealed final bundle. Original feature arrays are unscaled.
    domain_indices=[];seen=set()
    for i,row in enumerate(rows):
        key=(row["source_id"],row["chemistry"],row["protocol_id"])
        if key not in seen:seen.add(key);domain_indices.append(i)
    domain_arrays={k:dv[k][domain_indices] for k in ("features","sequences","sequence_mask","domain")}
    domain_queries=[{**rows[i],"feature_schema":record["feature_schema"],"data_namespace":record["data_namespace"],"allowed_heads":["soh","rul","threshold_risk","efficiency","fault"]} for i in domain_indices]
    np.savez_compressed(out/"reload_domain_samples.npz",**domain_arrays)
    write_json(out/"reload_domain_queries.json",domain_queries)
    write_json(out/"reload_domain_profiles.json",[package.predict(q,{k:v[j:j+1] for k,v in domain_arrays.items()}) for j,q in enumerate(domain_queries)])
    for name in ("reload_domain_samples.npz","reload_domain_queries.json","reload_domain_profiles.json"):
        manifest["files"][name]=sha256_file(out/name)
    manifest["reload_verified"]=True;manifest["files"]["reload_verification.json"]=sha256_file(out/"reload_verification.json")
    write_json(out/"manifest.json",manifest);print(str(out))

if __name__=="__main__":main()

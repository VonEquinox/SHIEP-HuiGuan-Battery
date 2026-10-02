"""Bounded prefix views from parsed V2 tables; transforms fit only on training objects."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .contracts import CHANNEL_VALIDITY_SCHEMA,sha256_file,validate_training_manifest

FEATURE_NAMES = ["voltage_mean_V","voltage_std_V","voltage_min_V","voltage_max_V","current_abs_mean_Crate",
                 "current_abs_max_Crate","temperature_mean_C","temperature_std_C","duration_s",
                 "charge_fraction","discharge_fraction","recent_capacity_relative_to_reference",
                 "visible_capacity_slope_per_source_cycle","visible_history_count","recent_current_delta_Crate"]
HISTORY_FEATURES = [11,12,13,14]
SEQUENCE_CHANNELS = ["voltage_V", "current_Crate_or_A_if_nominal_unknown", "temperature_C",
                     "relative_time", "phase", "temperature_valid"]
TEMPERATURE_CHANNEL = 2
TEMPERATURE_VALID_CHANNEL = 5


def values(row,*keys):
    for key in keys:
        item = row.get(key)
        if item is not None and not (isinstance(item,float) and np.isnan(item)):
            return np.asarray(item,dtype=float).reshape(-1)
    return np.array([],dtype=float)


def segment_view(row,points=256,nominal=None):
    """Return finite values plus explicit temperature validity.

    Zero is a neutral fill, not an observed temperature. Interpolation is legal
    only inside a contiguous run of finite temperature samples; neither short
    arrays nor NaN gaps create fictional temperature observations.
    """
    voltage=values(row,"voltage_V"); current=values(row,"current_A"); temperature=values(row,"temperature_C")
    time=values(row,"time_s","relative_time_s")
    n=min(len(voltage),len(current),len(time))
    result=np.zeros((points,len(SEQUENCE_CHANNELS)),dtype=np.float32); mask=np.zeros(points,dtype=np.float32)
    if n<2:return result,mask
    v,i,t=voltage[:n],current[:n],time[:n]
    temp=np.full(n,np.nan)
    temp[:min(n,len(temperature))]=temperature[:n]
    valid=np.isfinite(v)&np.isfinite(i)&np.isfinite(t)
    v,i,t,temp=v[valid],i[valid],t[valid],temp[valid]
    # Do not bridge clock resets or duplicate timestamps using a fictional trajectory.
    if len(t)<2 or np.any(np.diff(t)<=0):return result,mask
    grid=np.linspace(t[0],t[-1],points)
    relative=(grid-grid[0])/max(grid[-1]-grid[0],1e-6)
    phase=np.where(i>0,1,np.where(i<0,-1,0))
    result[:,0]=np.interp(grid,t,v)
    result[:,1]=np.interp(grid,t,i)/(nominal if nominal and nominal>0 else 1.)
    finite_temperature=np.isfinite(temp)
    # Split into contiguous measured runs instead of bridging a missing sample.
    starts=np.flatnonzero(finite_temperature & np.r_[True,~finite_temperature[:-1]])
    ends=np.flatnonzero(finite_temperature & np.r_[~finite_temperature[1:],True])
    for start,end in zip(starts,ends):
        inside=(grid>=t[start])&(grid<=t[end])
        if start==end:
            inside=np.isclose(grid,t[start],rtol=0,atol=max(1.,abs(t[start]))*1e-10)
        result[inside,TEMPERATURE_CHANNEL]=np.interp(grid[inside],t[start:end+1],temp[start:end+1])
        result[inside,TEMPERATURE_VALID_CHANNEL]=1
    result[:,3]=relative
    # Phase is categorical; nearest sampling preserves fast-charge stages.
    idx=np.searchsorted(t,grid,side="left").clip(max=len(t)-1)
    result[:,4]=phase[idx]
    mask[:]=1
    return result,mask


def statistical_view(sequence,mask,visible_cycles,reference,nominal):
    valid=sequence[mask>0]
    out=np.zeros(len(FEATURE_NAMES),dtype=float); missing=np.zeros_like(out)
    if len(valid):
        if sequence.shape[-1]!=len(SEQUENCE_CHANNELS):
            raise ValueError("temperature statistics require the channel-validity feature contract")
        v,i=valid[:,0],valid[:,1]
        out[:6]=[v.mean(),v.std(),v.min(),v.max(),np.abs(i).mean(),np.abs(i).max()]
        temperature_valid=(valid[:,TEMPERATURE_VALID_CHANNEL]>0)&np.isfinite(valid[:,TEMPERATURE_CHANNEL])
        temp=valid[temperature_valid,TEMPERATURE_CHANNEL]
        if len(temp):out[6:8]=[temp.mean(),temp.std()]
        # Partial coverage also remains visible; values summarize measured points.
        missing[6:8]=int(not temperature_valid.all())
        out[9:11]=[(i>0).mean(),(i<0).mean()]
    else:missing[:11]=1
    capacity_cycles=visible_cycles[visible_cycles.diagnostic.astype(bool)] if "diagnostic" in visible_cycles else visible_cycles
    capacity=capacity_cycles.get("capacity_Ah",pd.Series(dtype=float)).to_numpy(float)
    validq=np.isfinite(capacity)&(capacity>0)
    q=capacity[validq]
    if len(q) and reference>0:
        out[11]=q[-1]/reference
        if len(q)>1:
            cycle=capacity_cycles["cycle_index"].to_numpy(float)[validq]
            out[12]=np.polyfit(cycle[-min(5,len(q)):],q[-min(5,len(q)):]/reference,1)[0]
        else:missing[12]=1
    else:missing[11:13]=1
    out[13]=len(visible_cycles)
    missing[14]=1
    return np.r_[out,missing].astype(np.float32)


def build_feature_bundle(derived_dir,out_dir,landmarks_per_cell=8,history=32,points=256):
    directory=Path(derived_dir);out=Path(out_dir)
    if (out/"features.json").exists():raise FileExistsError("feature runs are immutable; use a new feature version directory")
    out.mkdir(parents=True,exist_ok=True)
    identity=pd.read_parquet(directory/"identity_map.parquet")
    cycles=pd.read_parquet(directory/"cycles.parquet")
    segments=pd.read_parquet(directory/"segments.parquet")
    targets=pd.read_parquet(directory/"targets.parquet") if (directory/"targets.parquet").exists() else pd.DataFrame()
    split=json.loads((directory/"split_manifest.json").read_text())
    assignments=split.get("assignments",split.get("memberships",{}))
    if not assignments:
        for key,entries in split.get("splits",{}).items():
            for cell in entries:assignments[cell]=key
    rows=[]; features=[]; sequences=[]; masks=[]; labels=[]
    domain_key=lambda r: "::".join(str(r.get(k)) for k in ("source_id","chemistry","protocol_id"))
    domains=sorted({domain_key(r) for r in identity.to_dict("records")}); domain_index={d:i for i,d in enumerate(domains)}
    for cell in identity.to_dict("records"):
        cell_id=cell["physical_cell_id"]
        if cell.get("source_id")=="xjtu" and cell_id.endswith("-5"):
            raise ValueError("protected object reached feature builder")
        splitname=assignments.get(cell_id)
        if splitname is None and "split" in cell:splitname=cell["split"]
        if splitname=="final-test":splitname="final"
        if splitname is None:raise ValueError(f"missing frozen split: {cell_id}")
        if splitname in ("sealed","protected"):continue
        cc=cycles[cycles.physical_cell_id==cell_id].sort_values("cycle_index")
        ss=segments[segments.physical_cell_id==cell_id].sort_values("cycle_index") if {"physical_cell_id","cycle_index"}.issubset(segments.columns) else pd.DataFrame()
        valid=cc[np.isfinite(cc.capacity_Ah)&(cc.capacity_Ah>0)]
        if "diagnostic" in valid:
            valid=valid[valid.diagnostic.astype(bool)]
        if len(valid)<2:continue
        # Diagnostic/RPT labels only where provided; operation capacity is a different target.
        if "label_status" in valid:
            measured=valid[valid.label_status.isin(["available","measured","diagnostic"])]
            if len(measured)>=2:valid=measured
        reference=float(valid.iloc[0].capacity_Ah);reference_time=float(valid.iloc[0].cycle_index)
        target_definition="xjtu-rpt-reference-soh-v2" if cell["source_id"]=="xjtu" else "matr-frozen-initial-reference-soh-v2"
        if not targets.empty and {"physical_cell_id","target_name","reference_capacity_Ah","reference_cutoff"}.issubset(targets.columns):
            reference_rows=targets[(targets.physical_cell_id==cell_id)&(targets.target_name=="soh")].sort_values("available_at")
            if not reference_rows.empty:
                first=reference_rows.iloc[0]
                if np.isfinite(first.reference_capacity_Ah) and np.isfinite(first.reference_cutoff):
                    reference=float(first.reference_capacity_Ah);reference_time=float(first.reference_cutoff)
                    target_definition=str(first.get("target_definition_id",target_definition))
        eligible=valid[valid.cycle_index>reference_time]
        if eligible.empty:continue
        chosen=eligible.iloc[np.unique(np.linspace(0,len(eligible)-1,min(landmarks_per_cell,len(eligible))).astype(int))]
        nominal=cell.get("nominal_capacity_Ah")
        nominal=float(nominal) if nominal is not None and np.isfinite(nominal) and nominal>0 else None
        for target in chosen.to_dict("records"):
            query=float(target["cycle_index"]);cutoff=query-1
            if reference_time>cutoff:continue
            visible=cc[cc.cycle_index<=cutoff]
            prior=ss[ss.cycle_index<=cutoff].tail(history) if "cycle_index" in ss else pd.DataFrame()
            sequence=np.zeros((history,points,len(SEQUENCE_CHANNELS)),np.float32);mask=np.zeros((history,points),np.float32)
            for j,segment in enumerate(prior.to_dict("records"),start=history-len(prior)):
                sequence[j],mask[j]=segment_view(segment,points,nominal)
            f=statistical_view(sequence[-1],mask[-1],visible,reference,nominal)
            if len(prior):
                time=values(prior.iloc[-1].to_dict(),"time_s","relative_time_s")
                if len(time)>1:f[8]=max(0.,time[-1]-time[0])
            row={"source_id":cell["source_id"],"physical_cell_id":cell_id,"split":splitname,
                 "chemistry":cell.get("chemistry"),"protocol_id":cell.get("protocol_id"),
                 "query_time":query,"visible_cutoff":cutoff,"feature_max_time":float(prior.cycle_index.max()) if len(prior) else cutoff,
                 "available_at":cutoff,"reference_cutoff":reference_time,"reference_capacity_Ah":reference,
                 "target_definition":target_definition,"unit":"ratio",
                 "target_observed_at":query,"target_available_at":query,
                 "evidence_refs":prior.get("raw_ref",pd.Series(dtype=str)).astype(str).tolist(),
                 "survival_time_unit":None,"domain_index":domain_index[domain_key(cell)]}
            rows.append(row);features.append(f);sequences.append(sequence);masks.append(mask)
            labels.append(float(target["capacity_Ah"])/reference)
    if not rows:raise ValueError("no valid prefix/target pairs; ingest cannot be called success")
    n=len(rows)
    arrays={"features":np.stack(features),"sequences":np.stack(sequences),"sequence_mask":np.stack(masks),
            "domain":np.asarray([r["domain_index"] for r in rows],np.int64),"y_soh":np.asarray(labels,np.float32),
            "y_efficiency":np.full(n,np.nan,np.float32),"y_fault":np.full(n,-1,np.float32),
            "survival_kind":np.full(n,-1,np.float32),"survival_lower":np.zeros(n,np.float32),"survival_upper":np.zeros(n,np.float32)}
    # Missing efficiency/physical RUL remains missing; summary ordinal is not a cycle counter.
    np.savez_compressed(out/"features.npz",**arrays)
    manifest={"schema_version":CHANNEL_VALIDITY_SCHEMA,"data_namespace":"experimental","data_version":"v2-prefix-channel-validity-2",
              "arrays_file":"features.npz","arrays_sha256":sha256_file(out/"features.npz"),
              "rows":rows,"feature_names":FEATURE_NAMES+[f"missing_{n}" for n in FEATURE_NAMES],
              "sequence_channels":SEQUENCE_CHANNELS,
              "temperature_policy":{"fill_value":0,"validity_channel":"temperature_valid","interpolation":"contiguous finite runs only","statistics":"valid temperature points only","stat_missing_flag":"1 for partial or absent temperature coverage"},
              "temperature_stat_domains":list(domain_index.values()),
              "domains":domain_index,"history_limit":history,"points":points,
              "target_definitions":{"soh":next(iter({r["target_definition"] for r in rows})) if len({r["target_definition"] for r in rows})==1 else "source_specific_frozen_reference_soh_v2","rul":None,"efficiency":None,"fault":None},
              "target_definitions_by_domain":{domain_key(r):{"soh":r["target_definition"],"rul":None,"efficiency":None,"fault":None} for r in rows},
              "missing_heads":{"rul":"no verified physical cycle/threshold definition","efficiency":"unverified SOC/boundary completeness","fault":"no confirmed fault label"},
              "split_sha256":sha256_file(directory/"split_manifest.json")}
    validate_training_manifest(manifest)
    (out/"features.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False))
    return manifest


def fit_preprocessor(features,sequences,mask,train_indices,*,domain=None,temperature_stat_domains=None):
    x=np.asarray(features)[train_indices]
    mean=x.mean(axis=0);scale=x.std(axis=0);scale[scale<1e-6]=1
    valid=sequences[train_indices][mask[train_indices]>0]
    sm=valid.mean(axis=0) if len(valid) else np.zeros(sequences.shape[-1])
    ss=valid.std(axis=0) if len(valid) else np.ones(sequences.shape[-1]);ss[ss<1e-6]=1
    if sequences.shape[-1]==len(SEQUENCE_CHANNELS):
        temperature=valid[valid[:,TEMPERATURE_VALID_CHANNEL]>0,TEMPERATURE_CHANNEL]
        sm[TEMPERATURE_CHANNEL]=temperature.mean() if len(temperature) else 0.
        ss[TEMPERATURE_CHANNEL]=temperature.std() if len(temperature) else 1.
        if ss[TEMPERATURE_CHANNEL]<1e-6:ss[TEMPERATURE_CHANNEL]=1.
        # Binary observation state enters the encoder unchanged.
        sm[TEMPERATURE_VALID_CHANNEL]=0.;ss[TEMPERATURE_VALID_CHANNEL]=1.
        if temperature_stat_domains and domain is not None and x.shape[1]==2*len(FEATURE_NAMES):
            applicable=np.isin(np.asarray(domain)[train_indices],temperature_stat_domains)
            latest_measured=(sequences[train_indices,-1,:,TEMPERATURE_VALID_CHANNEL]*mask[train_indices,-1]).sum(axis=-1)>0
            for feature_index in (6,7):
                # Partial summaries contain only qualified measurements. Native
                # statistics-only sources have different column meanings.
                observed=x[~applicable|latest_measured,feature_index]
                mean[feature_index]=observed.mean() if len(observed) else 0.
                scale[feature_index]=observed.std() if len(observed) else 1.
                if scale[feature_index]<1e-6:scale[feature_index]=1.
    return {"feature_mean":mean.tolist(),"feature_scale":scale.tolist(),"sequence_mean":sm.tolist(),"sequence_scale":ss.tolist(),
            "fitted_split":"train","feature_min":x.min(axis=0).tolist(),"feature_max":x.max(axis=0).tolist(),
            **({"temperature_stat_domains":list(temperature_stat_domains)} if temperature_stat_domains is not None else {})}


def preprocess(arrays,transform,no_history=False):
    result={k:v.copy() for k,v in arrays.items()}
    result["features"]=(result["features"]-transform["feature_mean"])/transform["feature_scale"]
    result["sequences"]=(result["sequences"]-transform["sequence_mean"])/transform["sequence_scale"]
    result["sequences"]*=result["sequence_mask"][...,None]
    if result["sequences"].shape[-1]==len(SEQUENCE_CHANNELS):
        temperature_valid=arrays["sequences"][...,TEMPERATURE_VALID_CHANNEL]>0
        result["sequences"][...,TEMPERATURE_CHANNEL]*=temperature_valid
        result["sequences"][...,TEMPERATURE_VALID_CHANNEL]=temperature_valid*result["sequence_mask"]
        if transform.get("temperature_stat_domains") and result["features"].shape[1]==2*len(FEATURE_NAMES):
            applicable=np.isin(arrays["domain"],transform["temperature_stat_domains"])
            for feature_index in (6,7):
                # Entirely absent temperature summaries use the neutral fill.
                absent=applicable&(arrays["features"][:,len(FEATURE_NAMES)+feature_index]>0)&((arrays["sequences"][:,-1,:,TEMPERATURE_VALID_CHANNEL]*arrays["sequence_mask"][:,-1]).sum(axis=-1)==0)
                result["features"][absent,feature_index]=0.
    if no_history:
        if "history_feature_mask" in result:
            result["features"]*=1-result["history_feature_mask"]
        else:
            result["features"][:,HISTORY_FEATURES]=0
    return result


def build_fault_stat_bundle(derived_dir,out_dir,history=32,points=256):
    """Native-unit vehicle statistics; no nonexistent physical curves or cell roots."""
    directory=Path(derived_dir);out=Path(out_dir)
    if out.exists() and (out/"features.json").exists():raise FileExistsError("feature runs are immutable")
    out.mkdir(parents=True,exist_ok=True)
    identity=pd.read_parquet(directory/"identity_map.parquet");segments=pd.read_parquet(directory/"segments.parquet");targets=pd.read_parquet(directory/"targets.parquet")
    if any(k in segments for k in ("fault_label","original_snippet_label")):raise ValueError("hidden fault label cannot be a feature")
    split=json.loads((directory/"split_manifest.json").read_text())["assignments"]
    fields=["volt_mean","volt_std","current_mean","current_std","soc_mean","soc_std","max_single_volt_mean","min_single_volt_mean",
            "max_single_volt_std","min_single_volt_std","max_temp_mean","min_temp_mean","max_temp_std","min_temp_std","mileage_km"]
    rows=[];features=[];labels=[];domain="dyad::unknown::vehicle_charging"
    target_lookup={}
    for t in targets.to_dict("records"):
        key=(t["physical_cell_id"],t["observed_at"])
        if key in target_lookup and target_lookup[key]["value"]!=t["value"]:raise ValueError("conflicting vehicle/time labels")
        target_lookup[key]=t
    for row in segments.to_dict("records"):
        cell=row["physical_cell_id"];target=target_lookup.get((cell,row["observed_at"]))
        if not target:continue
        x=np.asarray([row.get(k,np.nan) for k in fields],dtype=float);missing=~np.isfinite(x)
        features.append(np.r_[np.nan_to_num(x),missing].astype(np.float32));labels.append(int(target["value"]))
        time=float(row["observed_at"])
        rows.append({"source_id":"dyad","physical_cell_id":cell,"split":split[cell],"chemistry":"unknown","chemistry_status":"unverified",
                     "protocol_id":"vehicle_charging","query_time":time,"visible_cutoff":time,"feature_max_time":time,"available_at":time,
                     "time_basis":"source_charge_segment_number","reference_cutoff":None,"target_definition":target["target_definition_id"],
                     "unit":"class","target_observed_at":None,"target_available_at":None,"target_label_timing":"offline_retrospective_label",
                     "sensor_level":"vehicle","evidence_refs":[row["raw_ref"]],"survival_time_unit":None,"domain_index":0})
    n=len(rows)
    arrays={"features":np.stack(features),"sequences":np.zeros((n,history,points,len(SEQUENCE_CHANNELS)),np.float32),"sequence_mask":np.zeros((n,history,points),np.float32),
            "domain":np.zeros(n,np.int64),"y_soh":np.full(n,np.nan,np.float32),"y_efficiency":np.full(n,np.nan,np.float32),"y_fault":np.asarray(labels,np.float32),
            "survival_kind":np.full(n,-1,np.float32),"survival_lower":np.zeros(n,np.float32),"survival_upper":np.zeros(n,np.float32)}
    np.savez_compressed(out/"features.npz",**arrays)
    defs={"soh":None,"rul":None,"efficiency":None,"fault":"dyad-original-retrospective-vehicle-anomaly-v2"}
    manifest={"schema_version":CHANNEL_VALIDITY_SCHEMA,"data_namespace":"experimental","data_version":"v2-dyad-native-statistics-channel-validity-2","arrays_file":"features.npz",
              "arrays_sha256":sha256_file(out/"features.npz"),"rows":rows,"feature_names":fields+[f"missing_{k}" for k in fields],
              "feature_units":["native_unverified"]*14+["km"]+["mask"]*15,"domains":{domain:0},"history_limit":history,"points":points,"sequence_channels":SEQUENCE_CHANNELS,"temperature_stat_domains":[],
              "target_definitions":defs,"target_definitions_by_domain":{domain:defs},"input_kind":"statistics_only_no_verified_curve_units",
              "label_granularity":"vehicle_anomaly_not_cell_root_cause","split_sha256":sha256_file(directory/"split_manifest.json")}
    validate_training_manifest(manifest);(out/"features.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False));return manifest


def combine_feature_bundles(manifest_paths,out_dir):
    """Combine frozen source views without refitting, relabeling, or moving objects."""
    from .contracts import load_dataset,domain_key
    out=Path(out_dir)
    if out.exists() and (out/"features.json").exists():raise FileExistsError("combined feature run is immutable")
    out.mkdir(parents=True,exist_ok=True)
    loaded=[load_dataset(p) for p in manifest_paths]
    if len({m["schema_version"] for m,a in loaded})!=1:raise ValueError("feature versions cannot mix; rebuild and retrain every source adapter")
    if len({m["data_namespace"] for m,a in loaded})!=1:raise ValueError("experimental/generated namespaces must not pool")
    feature_shapes={a["features"].shape[1:] for m,a in loaded};sequence_shapes={a["sequences"].shape[1:] for m,a in loaded}
    if len(feature_shapes)!=1 or len(sequence_shapes)!=1:raise ValueError("source adapters must expose identical structural dimensions")
    rows=[r.copy() for m,a in loaded for r in m["rows"]];domains={k:i for i,k in enumerate(sorted({domain_key(r) for r in rows}))}
    temperature_stat_domains=sorted({domains[key] for m,a in loaded for key,index in m["domains"].items() if index in m.get("temperature_stat_domains",[])})
    arrays={k:np.concatenate([a[k] for m,a in loaded]) for k in loaded[0][1]}
    history_masks=[]
    for m,a in loaded:
        hm=np.zeros_like(a["features"],dtype=np.float32)
        for i,row in enumerate(m["rows"]):
            if row["source_id"] in ("xjtu","matr"):
                hm[i,HISTORY_FEATURES]=1
        history_masks.append(hm)
    arrays["history_feature_mask"]=np.concatenate(history_masks)
    arrays["domain"]=np.asarray([domains[domain_key(r)] for r in rows],np.int64)
    for row in rows:row["domain_index"]=domains[domain_key(row)]
    np.savez_compressed(out/"features.npz",**arrays)
    by_domain={key:value for m,a in loaded for key,value in m.get("target_definitions_by_domain",{d:m["target_definitions"] for d in m["domains"]}).items()}
    manifest={"schema_version":loaded[0][0]["schema_version"],"data_namespace":loaded[0][0]["data_namespace"],"data_version":"v2-multisource-adapters-channel-validity-2" if loaded[0][0]["schema_version"]==CHANNEL_VALIDITY_SCHEMA else "v2-multisource-adapters-1",
              "arrays_file":"features.npz","arrays_sha256":sha256_file(out/"features.npz"),"rows":rows,"domains":domains,
              "feature_names_by_source":{m["data_version"]:m.get("feature_names") for m,a in loaded},
              "source_manifest_sha256":{str(p):sha256_file(Path(p)) for p in manifest_paths},
              **({"sequence_channels":SEQUENCE_CHANNELS,"temperature_stat_domains":temperature_stat_domains} if loaded[0][0]["schema_version"]==CHANNEL_VALIDITY_SCHEMA else {}),
              "target_definitions":{"soh":"source_specific_frozen_reference_soh_v2","rul":None,"efficiency":None,"fault":"dyad-original-retrospective-vehicle-anomaly-v2"},
              "target_definitions_by_domain":by_domain,"input_adapters":{"xjtu":"measured_curve_and_capacity_history","matr":"measured_capacity_history_no_curve","dyad":"native_statistics_no_curve_or_cell_root"},
              "history_limit":loaded[0][0]["history_limit"],"points":loaded[0][0]["points"]}
    validate_training_manifest(manifest);(out/"features.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False));return manifest

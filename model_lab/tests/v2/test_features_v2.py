import json
import numpy as np
import pandas as pd
from model_lab.modeling.v2.features import build_feature_bundle,fit_preprocessor


def write_fixture(path,future_capacity=1.4):
    path.mkdir()
    pd.DataFrame([{"source_id":"fixture","physical_cell_id":"a","chemistry":"NCM","protocol_id":"p","nominal_capacity_Ah":2.}]).to_parquet(path/"identity_map.parquet")
    pd.DataFrame([{"source_id":"fixture","physical_cell_id":"a","cycle_index":k,"capacity_Ah":q,"diagnostic":True} for k,q in [(1,2.),(3,1.8),(5,future_capacity)]]).to_parquet(path/"cycles.parquet")
    pd.DataFrame([{"source_id":"fixture","physical_cell_id":"a","cycle_index":k,"voltage_V":[3.,4.],"current_A":[1.,1.],"temperature_C":[25.,25.],"time_s":[0.,10.],"raw_ref":f"fixture:{k}"} for k in (1,3,5)]).to_parquet(path/"segments.parquet")
    (path/"split_manifest.json").write_text(json.dumps({"assignments":{"a":"train"}}))


def test_future_label_and_curves_never_enter_earlier_features(tmp_path):
    first=tmp_path/"first";other=tmp_path/"other";write_fixture(first);write_fixture(other,9.9)
    ma=build_feature_bundle(first,tmp_path/"a",landmarks_per_cell=2,history=2,points=16)
    mb=build_feature_bundle(other,tmp_path/"b",landmarks_per_cell=2,history=2,points=16)
    with np.load(tmp_path/"a"/"features.npz",allow_pickle=False) as a,np.load(tmp_path/"b"/"features.npz",allow_pickle=False) as b:
        assert np.array_equal(a["features"],b["features"])
        assert np.array_equal(a["sequences"],b["sequences"])
        assert a["y_soh"][-1]!=b["y_soh"][-1]
    assert all(r["feature_max_time"]<=r["visible_cutoff"]<r["target_observed_at"] for r in ma["rows"])


def test_preprocessor_does_not_fit_dev_or_future_objects():
    x=np.array([[1.,2.],[2.,4.],[999.,999.]])
    seq=np.zeros((3,1,2,5));mask=np.ones((3,1,2))
    transform=fit_preprocessor(x,seq,mask,[0,1])
    assert transform["feature_mean"]==[1.5,3.]

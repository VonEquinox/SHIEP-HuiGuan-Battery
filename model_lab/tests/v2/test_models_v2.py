from pathlib import Path
import numpy as np
import pytest
import torch
from sklearn.ensemble import GradientBoostingRegressor
from model_lab.modeling.v2.baselines import gb_to_dict,predict_gb,fit_ngboost,predict_ngboost
from model_lab.modeling.v2.calibration import fit_cqr,apply_cqr
from model_lab.modeling.v2.contracts import SCHEMA,validate_training_manifest,check_query
from model_lab.modeling.v2.survival import censored_nll,summarize_survival,survival_from_hazard
from model_lab.modeling.v2.multitask import TemporalMultiTask,masked_loss,MultiTaskModel


def test_survival_exact_right_interval_and_beyond_support():
    h=np.tile([.2,.25,.5],(4,1));grid=[10,20,30]
    # exact at 20: .8*.25=.2; censored 20: .6; interval (10,30]: .8-.3=.5; beyond support: .3.
    nll=censored_nll(h,[20,20,10,40],[20,20,30,40],[1,0,2,1],grid)
    assert nll==pytest.approx(-np.log([.2,.6,.5,.3]).mean())
    assert np.all(np.diff(survival_from_hazard(h),axis=1)<=0)
    output=summarize_survival([.01,.01,.01],grid)
    assert output["median"] is None and output["median_status"]=="exceeds_prediction_range"
    assert output["threshold_probability"]==pytest.approx(1-output["survival"][-1])


def test_cqr_uses_object_maximum_and_resolution():
    y=np.array([1.,2.,3.,4.,5.]);q=np.column_stack([y-.1,y,y+.1])
    q[1]-=1
    cal=fit_cqr(y,q,["a","a","b","c","d"],["x"]*5,.2)
    assert cal["domains"]["x"]["independent_objects"]==4
    assert cal["domains"]["x"]["correction"]==pytest.approx(.9)
    impossible=fit_cqr(y,q,["a"]*5,["x"]*5,.05)
    assert impossible["domains"]["x"]["correction"] is None
    assert not np.isfinite(apply_cqr(q,["x"]*5,impossible)).any()


def test_tree_and_ngboost_safe_export_are_exact():
    rng=np.random.default_rng(1);x=rng.normal(size=(40,3));y=x[:,0]+rng.normal(scale=.1,size=40)
    estimator=GradientBoostingRegressor(n_estimators=8).fit(x,y)
    assert np.allclose(estimator.predict(x),predict_gb(gb_to_dict(estimator),x))
    model=fit_ngboost(x,y,np.ones(40),1,8)
    params=predict_ngboost(model,x)
    assert params.shape==(40,2) and np.all(params[:,1]>0)


def test_manifest_rejects_future_reference_cross_split_and_protected_cells():
    row={"physical_cell_id":"cell-a","source_id":"xjtu","split":"train","query_time":10,"visible_cutoff":9,"available_at":9}
    m={"schema_version":SCHEMA,"data_namespace":"experimental","rows":[row]}
    validate_training_manifest(m)
    for bad in ({"reference_cutoff":10},{"physical_cell_id":"Batch-4/R3_battery-5"}):
        with pytest.raises(ValueError):validate_training_manifest({**m,"rows":[{**row,**bad}]})
    with pytest.raises(ValueError):validate_training_manifest({**m,"rows":[row,{**row,"split":"dev"}]})


def test_unknown_chemistry_schema_and_calendar_horizon_refuse():
    query={"feature_schema":SCHEMA,"data_namespace":"experimental","source_id":"xjtu","chemistry":"NCM","protocol_id":"R3","physical_cell_id":"a","query_time":10,"visible_cutoff":9}
    support=[{"source_id":"xjtu","chemistry":"NCM","protocol_id":"R3"}]
    assert check_query(query,support)==[]
    assert "unsupported_source_chemistry_protocol" in check_query({**query,"chemistry":"LFP"},support)
    assert "calendar_horizon_requires_operating_scenario" in check_query({**query,"horizon_unit":"day"},support)


def test_m2_missing_tasks_do_not_create_supervision_and_safe_reload(tmp_path):
    torch.manual_seed(0)
    model=TemporalMultiTask(3,2,3,width=128)
    features=torch.zeros((2,3));sequence=torch.zeros((2,2,16,5));mask=torch.zeros((2,2,16));domain=torch.tensor([0,1])
    output=model(features,sequence,mask,domain)
    labels={"y_soh":torch.tensor([1.,float("nan")]),"y_efficiency":torch.full((2,),float("nan")),"y_fault":torch.full((2,),-1.),"survival_kind":torch.full((2,),-1.),"survival_lower":torch.zeros(2),"survival_upper":torch.zeros(2)}
    loss,active=masked_loss(output,labels,torch.ones(2),[10,20,30])
    assert active==["soh"] and torch.isfinite(loss)
    loss.backward()
    assert model.efficiency.weight.grad is None and model.fault.weight.grad is None
    spec={"n_features":3,"n_domains":2,"width":128,"adapter_width":32}
    wrapper=MultiTaskModel(spec,grid=[10,20,30]);wrapper.label_support={"soh":True,"efficiency":False,"rul":False,"fault":False}
    wrapper.save(tmp_path/"weights.npz")
    reloaded=MultiTaskModel.load(spec,tmp_path/"weights.npz",grid=[10,20,30],label_support=wrapper.label_support)
    for key,value in wrapper.model.state_dict().items():assert torch.equal(value,reloaded.model.state_dict()[key])


def test_padding_values_are_invisible_to_m2():
    torch.manual_seed(4);model=TemporalMultiTask(3,1,3).eval()
    x=torch.randn(1,3);s=torch.randn(1,2,16,5);mask=torch.zeros(1,2,16);mask[:,1,:8]=1;d=torch.zeros(1,dtype=torch.long)
    other=s.clone();other[mask==0]=99999
    with torch.no_grad():a=model(x,s,mask,d);b=model(x,other,mask,d)
    for k in a:assert torch.allclose(a[k],b[k])


def test_fault_baseline_uses_vehicle_label_without_faking_soh():
    from model_lab.modeling.v2.baselines import DomainBaseline
    rng=np.random.default_rng(12);x=rng.normal(size=(40,4));n=len(x)
    rows=[{"source_id":"vehicle_fixture","physical_cell_id":f"vehicle-{i//4}","chemistry":"unknown","protocol_id":"stat-only"} for i in range(n)]
    arrays={"features":x,"y_soh":np.full(n,np.nan),"y_efficiency":np.full(n,np.nan),"survival_kind":np.full(n,-1),
            "survival_lower":np.zeros(n),"survival_upper":np.zeros(n),"y_fault":(x[:,0]>0).astype(float)}
    model=DomainBaseline(n_estimators=12,use_ngboost=False).fit(arrays,rows)
    prediction=model.predict(arrays,rows)
    assert np.isnan(prediction["soh_quantiles"]).all()
    assert np.isnan(prediction["hazard"]).all()
    assert ((prediction["fault_probability"]>=0)&(prediction["fault_probability"]<=1)).all()
    assert np.mean((prediction["fault_probability"]>.5)==arrays["y_fault"])>.8


def test_multitask_never_infers_missing_domain_head():
    n=8
    rows=[{"source_id":"aging" if i<4 else "fleet","physical_cell_id":f"object-{i//2}","chemistry":"NCM" if i<4 else "unknown","protocol_id":"p"} for i in range(n)]
    arrays={"features":np.zeros((n,3),np.float32),"sequences":np.zeros((n,1,16,5),np.float32),"sequence_mask":np.zeros((n,1,16),np.float32),"domain":np.r_[np.zeros(4),np.ones(4)].astype(int),
            "y_soh":np.r_[np.ones(4),np.full(4,np.nan)].astype(np.float32),"y_efficiency":np.full(n,np.nan,np.float32),
            "y_fault":np.r_[np.full(4,-1),[0,0,1,1]].astype(np.float32),"survival_kind":np.full(n,-1,np.float32),"survival_lower":np.zeros(n,np.float32),"survival_upper":np.zeros(n,np.float32)}
    model=MultiTaskModel({"n_features":3,"n_domains":2}).fit(arrays,rows,epochs=1,batch_size=4)
    output=model.predict(arrays,rows)
    assert np.isfinite(output["soh_quantiles"][:4]).all() and np.isnan(output["soh_quantiles"][4:]).all()
    assert np.isnan(output["fault_probability"][:4]).all() and np.isfinite(output["fault_probability"][4:]).all()


def test_fixed_task_weights_do_not_change_when_other_labels_missing():
    n=2
    output={"soh":torch.tensor([[0.,0.],[0.,0.]]),"efficiency":torch.tensor([[0.,0.],[0.,0.]]),"hazard_logits":torch.zeros(n,3),"fault_logits":torch.zeros(n)}
    labels={"y_soh":torch.ones(n),"y_efficiency":torch.full((n,),float("nan")),"y_fault":torch.full((n,),-1.),"survival_kind":torch.full((n,),-1.),"survival_lower":torch.zeros(n),"survival_upper":torch.zeros(n)}
    first,_=masked_loss(output,labels,torch.ones(n),[10,20,30],domain_denominator=2)
    both,_=masked_loss(output,{**labels,"y_fault":torch.zeros(n)},torch.ones(n),[10,20,30],domain_denominator=2)
    assert both-first==pytest.approx(np.log(2))

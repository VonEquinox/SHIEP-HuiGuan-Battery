"""Same frozen mixture and context as v1, with one-view cache lifetime."""
from __future__ import annotations
import gc
import numpy as np
import torch

from model_lab.modeling.frozen_hybrid import FrozenHybrid,ROOT,matched_input,sha256
from model_lab.modeling.frozen_et import predict_soh
from model_lab.modeling.streaming_tabicl import streaming_predict


class FrozenStreamingHybrid(FrozenHybrid):
    def __init__(self, package, device='mps'):
        super().__init__(package,device)
        for key,path in (('streaming_adapter',ROOT/'modeling/streaming_tabicl.py'),
                         ('streaming_inference',ROOT/'modeling/frozen_hybrid_streaming.py')):
            if self.manifest['code_sha256'].get(key) != sha256(path):
                raise ValueError(f'Streaming code changed after freeze: {key}')
        self.last_isolation_checks=[]

    def predict_components(self,current,reference,log_window_ratio,chunk_rows=256,
                           verify_isolation=False,progress=None):
        from tabicl import TabICLRegressor
        z=matched_input(current,reference,log_window_ratio,self.et)
        forest=predict_soh(current,reference,log_window_ratio,self.et)
        logs=[];checks=[];torch.set_num_threads(4)
        for seed in (0,1,2):
            prior=TabICLRegressor(n_estimators=8,batch_size=1,kv_cache=False,
                model_path=str(self.weight),allow_auto_download=False,device=self.device,
                use_amp=False,use_fa3=False,offload_mode='auto',
                disk_offload_dir=str(ROOT/'data/raw/tabicl/offload'),random_state=seed,n_jobs=4)
            try:
                prior.fit(self.x_context,self.y_context)
                lp,records=streaming_predict(prior,z,chunk_rows,verify_isolation,progress)
                logs.append(np.asarray(lp,dtype=float));checks.extend(records)
            finally:
                del prior;gc.collect()
                if self.device=='mps':torch.mps.empty_cache()
        lp=np.mean(logs,axis=0)
        with np.errstate(over='raise',invalid='raise'):
            result={'soh':np.exp(.5*(lp+np.log(forest))),
                    'extra_trees_soh':forest,'tabicl_soh':np.exp(lp)}
        if any(not np.isfinite(v).all() or np.any(v<=0) for v in result.values()):
            raise ValueError('Invalid streamed ensemble output')
        self.last_isolation_checks=checks
        return result

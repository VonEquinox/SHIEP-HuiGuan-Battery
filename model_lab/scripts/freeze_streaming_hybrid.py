"""Version the resource implementation, preserving the exact selected recipe."""
from __future__ import annotations
import json,shutil
from datetime import datetime,timezone
from pathlib import Path
from model_lab.scripts.train_nested_cv import ROOT,digest
from model_lab.modeling.frozen_hybrid_streaming import FrozenStreamingHybrid


def main():
    parent=ROOT/'reports/round3/champion_hybrid_v1'
    out=ROOT/'reports/round3/champion_hybrid_v2_streaming'
    proof_path=ROOT/'reports/round3/streaming_equivalence.json'
    proof=json.loads(proof_path.read_text())
    if proof['status']!='passed' or proof['streaming_code_sha256']!=digest(ROOT/'modeling/streaming_tabicl.py'):
        raise ValueError('Current adapter has not passed numeric equivalence')
    if out.exists():raise FileExistsError('Frozen packages must not be overwritten')
    manifest=json.loads((parent/'manifest.json').read_text())
    out.mkdir(parents=True)
    for name,expected in manifest['package_file_sha256'].items():
        if digest(parent/name)!=expected:raise ValueError('Parent data/forest changed')
        shutil.copy2(parent/name,out/name)
    manifest.update(created_at_utc=datetime.now(timezone.utc).isoformat(),
        resource_implementation_version=2,parent_manifest_sha256=digest(parent/'manifest.json'),
        scope='same frozen research recipe and immutable context; one-view cache implementation',
        numeric_equivalence_sha256=digest(proof_path),
        resource_policy={'cache_mode':'repr, one view at a time','column_batch_cap':16,
            'row_batch_cap':64,'icl_batch_cap':1,'context_rows_removed':0,'features_removed':0,
            'mps_high_watermark':0.7,'mps_low_watermark':0.5})
    manifest['code_sha256'].update(streaming_adapter=digest(ROOT/'modeling/streaming_tabicl.py'),
        streaming_inference=digest(ROOT/'modeling/frozen_hybrid_streaming.py'),
        streaming_packager=digest(Path(__file__)))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    FrozenStreamingHybrid(out,device='cpu')
    print(json.dumps({'package':str(out),'manifest_sha256':digest(out/'manifest.json'),
        'recipe':manifest['recipe'],'et_weight':manifest['et_weight'],
        'train_rows':manifest['train_rows'],'heldout_scored':False},indent=2),flush=True)


if __name__=='__main__':main()

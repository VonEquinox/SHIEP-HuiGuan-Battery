"""Package the preregistered development-selected recipe without test scoring."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from model_lab.modeling.frozen_et import load_champion
from model_lab.modeling.frozen_hybrid import CHECKPOINT_SHA, FrozenHybrid, matched_input
from model_lab.scripts.train_nested_cv import ROOT, VIEW, digest, load_development

OUT = ROOT/'reports/round3/champion_hybrid_v1'
FOLLOWUP = ROOT/'reports/round3/tabicl_followup'
ET = ROOT/'reports/round3/champion_v3'


def main():
    report = json.loads((FOLLOWUP/'summary.json').read_text())
    if report['selected_development_recipe'] != 'tabicl_et_equal':
        raise ValueError('This packager is only for the preregistered selected recipe')
    if report['failed_runs'] or report['incomplete_candidates'] or report['context_fits_attempted'] != 9:
        raise ValueError('Incomplete follow-up cannot be silently accepted')
    protocol = json.loads((FOLLOWUP/'manifest.json').read_text())
    if protocol['runner_sha256'] != digest(ROOT/'scripts/evaluate_tabicl.py'):
        raise ValueError('Evaluation code changed after scores')
    if protocol['protocol_sha256'] != digest(ROOT/'docs/ROUND3_TABICL_PROTOCOL.md'):
        raise ValueError('Selection protocol changed after scores')
    et_manifest = json.loads((ET/'manifest.json').read_text())
    if et_manifest['artifact_sha256'] != digest(ET/'et_champion.joblib'):
        raise ValueError('Frozen forest changed')
    if OUT.exists():
        raise FileExistsError('Never overwrite a frozen package')
    data, held = load_development(VIEW)
    artifact = load_champion(ET/'et_champion.joblib')
    z = matched_input(data.x, data.reference, data.log_ratio, artifact)
    OUT.mkdir(parents=True)
    shutil.copy2(ET/'et_champion.joblib', OUT/'et_champion.joblib')
    np.savez(OUT/'development_context.npz', x=z, log_soh=np.log(data.soh),
             cell=data.cell, source_row=data.source_row)
    chosen = next(m for m in report['methods'] if m['method'] == 'tabicl_et_equal')
    manifest = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'frozen research inference package; no final test score at freezing',
        'recipe': 'tabicl_et_equal', 'et_weight': .5, 'seeds': [0, 1, 2],
        'tabicl_estimators_per_seed': 8, 'tabicl_package': '2.2.0',
        'checkpoint_sha256': CHECKPOINT_SHA, 'schema': 'xjtu_71d_partial_cc_v1',
        'task': '3.7-4.1V preceding CC prefix and initial reference -> RPT-relative SOH',
        'train_rows': len(data.soh), 'train_cell_ids': sorted(set(map(str, data.cell))),
        'heldout_cell_ids': held, 'heldout_scored_at_freeze': False,
        'package_file_sha256': {name: digest(OUT/name) for name in ('et_champion.joblib','development_context.npz')},
        'code_sha256': {'inference': digest(ROOT/'modeling/frozen_hybrid.py'),
                        'et_inference': digest(ROOT/'modeling/frozen_et.py'),
                        'packager': digest(Path(__file__))},
        'provenance_sha256': {'followup_summary': digest(FOLLOWUP/'summary.json'),
            'followup_manifest': digest(FOLLOWUP/'manifest.json'),
            'selection_protocol': digest(ROOT/'docs/ROUND3_TABICL_PROTOCOL.md'),
            'view': digest(VIEW), 'feature_map': digest(ROOT/'data/physical_curve_features.py'),
            'environment': digest(ROOT/'locks/round3-tabicl-freeze.txt')},
        'development_ensemble_mae_pp': chosen['geometric_ensemble']['cell_mae_pp'],
        'not_claimed': ['public-benchmark SOTA','zero overfitting','universal battery transfer',
                        'low-latency production BMS','calibrated safety risk','RUL']}
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2))
    # Verify file/schema loading now; no heldout prediction or target reading here.
    FrozenHybrid(OUT, device='cpu')
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == '__main__':
    main()

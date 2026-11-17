"""Fixed timing-only movement-feature experiment on audited phase-clean windows."""
import argparse
import json
from pathlib import Path
import numpy as np
from aimguard.baseline import digest,write_json
from aimguard.tracking_models import with_abstentions


def pre_features(windows):
    values=[w['pre_first_features'] for w in windows if all(v is not None and np.isfinite(v) and v>=0 for v in w['pre_first_features'])]
    return (np.median(values,axis=0).tolist() if len(values)>=5 else None),len(values)


def run(pool,audit,output):
    pool,audit,output=map(Path,(pool,audit,output));base=json.loads((pool/'comparison.json').read_text());source=json.loads((pool/'inputs.json').read_text());data=json.loads((audit/'audit.json').read_text());plan=json.loads((audit/'protocol.json').read_text())
    if base['inputs_sha256']!=digest(pool/'inputs.json') or base['protocol_sha256']!=digest(pool/'protocol.json') or data['protocol_sha256']!=digest(audit/'protocol.json') or plan['source_comparison_sha256']!=digest(pool/'comparison.json') or plan['source_inputs_sha256']!=digest(pool/'inputs.json'):raise ValueError('Source audit/pool receipt differs')
    lookup={r['case_id']:r for r in data['cases']}
    if len(lookup)!=len(data['cases']) or set(lookup)!={r['case_id'] for r in source['cases']}:raise ValueError('Audit identities differ')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='inspected_pre_first_movement_experiment',audit_sha256=digest(audit/'audit.json'),source_comparison_sha256=digest(pool/'comparison.json'),code_sha256=digest(__file__),
        minimum_complete_pre_windows=5,pre_seconds=.1,threshold=.5,hyperparameters=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0),
        change='Replace first two movement medians with strictly pre-first-shot medians; preserve original two tracking features, participant groups and log1p/training-only scaling.',note='Fixed timing recipe, no radius/feature/threshold search. Not recoil correction or fresh evaluation. No model promotion or holdout use.'))
    rows=[];ids=[];values=[]
    for row in source['cases']:
        entry=lookup[row['case_id']]
        if entry['label']!=row['label'] or not np.allclose(entry['original_case_features'],row['features'][:2]):raise ValueError('Original audit features/label differ')
        pre,count=pre_features(entry['windows']);v=[*pre,*row['features'][2:]] if pre is not None and row['features'] is not None else None
        rows.append(dict(case_id=row['case_id'],label=row['label'],features=v,eligible_pre_windows=count));values.append(v);ids.append(row['case_id'])
    write_json(output/'inputs.json',dict(cases=rows,groups=source['groups']))
    g={cid:k for k,cs in source['groups'].items() for cid in cs};model=with_abstentions(values,[int(r['label']=='cheating') for r in rows],[g[cid] for cid in ids],ids,'log1p')
    result=dict(models=dict(original=base['models']['v06_speed_and_tracking'],pre_first=model),protocol_sha256=digest(output/'protocol.json'),inputs_sha256=digest(output/'inputs.json'),promotion_status='not_frozen_or_deployed');write_json(output/'comparison.json',result)
    lines=['# Strict pre-first-shot movement experiment','','| Recipe | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,m in result['models'].items():
        c=m['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {m['metrics']['abstentions']} |")
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True);return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pool',type=Path);p.add_argument('audit',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);run(a.pool,a.audit,a.output)


if __name__=='__main__':main()

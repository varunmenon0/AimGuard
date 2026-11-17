"""Re-evaluate training-only conservative cutoffs under explicit specificity-first priority."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path

from aimguard.baseline import digest,write_json
from aimguard.error_audit import low_false_flag_predictions


def run(pool,output):
    pool,output=map(Path,(pool,output));baseline=json.loads((pool/'comparison.json').read_text());source=json.loads((pool/'inputs.json').read_text());protocol=json.loads((pool/'protocol.json').read_text())
    if (baseline['inputs_sha256']!=digest(pool/'inputs.json') or baseline['protocol_sha256']!=digest(pool/'protocol.json')
        or protocol['role']!='inspected_v06_development' or source['groups']!=protocol['groups']
        or protocol['threshold']!=.5 or protocol['hyperparameters']!=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0)):
        raise ValueError('Phase-clean source/protocol receipt differs')
    rows=source['cases'];ids=[r['case_id'] for r in rows];members=[cid for cs in source['groups'].values() for cid in cs]
    if len(set(ids))!=len(ids) or len(set(members))!=len(members) or set(ids)!=set(members) or any(r['features'] is None or r['label'] not in ('cheating','legitimate') for r in rows):raise ValueError('Need eligible aligned cases and exact group partition')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='specificity_first_development',recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        objective='Prioritize fewer legitimate flags over cheating recall; no fixed recall floor',
        policy='Nested leave-one-group-out; strict score > maximum legitimate inner out-of-group score. Outer held-out data never choose cutoff. Incomplete calibration abstains.',
        source_sha256={name:digest(pool/name) for name in ('inputs.json','protocol.json','comparison.json')},
        code_sha256={name:digest(Path(__file__).with_name(name)) for name in ('specificity_policy.py','error_audit.py','development_models.py')},
        note='Existing conservative recipe revisited on expanded phase-clean data under changed user priority. No cutoff search or FPR guarantee; no reserved controls read or model frozen.'))
    by_case={cid:g for g,cs in source['groups'].items() for cid in cs}
    model=low_false_flag_predictions([r['features'] for r in rows],[int(r['label']=='cheating') for r in rows],[by_case[cid] for cid in ids],ids)
    result=dict(models=dict(default_cutoff=baseline['models']['v06_speed_and_tracking'],specificity_first=model),
        protocol_sha256=digest(output/'protocol.json'),promotion_status='development_only_not_frozen')
    write_json(output/'comparison.json',result)
    lines=['# Specificity-first development policy','','| Policy | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,m in result['models'].items():
        c=m['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {m['metrics']['abstentions']} |")
    false=[p['case_id'] for p in model['predictions'] if p['status']=='scored' and p['flagged'] and p['label']=='legitimate']
    lines+=['','Remaining legitimate false flags: '+', '.join(false),'','Inspected development diagnostics only. Reduced observed false flags are not a population guarantee; abstentions are not correct negatives. No model promotion or reserved-control evaluation.']
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True);return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pool',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);run(a.pool,a.output)


if __name__=='__main__':main()

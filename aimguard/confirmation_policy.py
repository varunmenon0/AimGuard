"""Agreement policy on fixed matched-fold predictions; review is never a clean decision."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path

import numpy as np
from scipy.special import expit

from aimguard.baseline import digest,write_json


def confirm(first,second):
    if first['case_id']!=second['case_id'] or first['label']!=second['label']:raise ValueError('Prediction identity/label differs')
    row=dict(case_id=first['case_id'],label=first['label'],first_score=first.get('baseline_score'),second_score=second.get('baseline_score'))
    if first['status']!='scored' or second['status']!='scored':return dict(row,decision='review_missing_evidence',flagged=None)
    for p in (first,second):
        if not np.isfinite(p['baseline_score']) or p['flagged']!=(p['baseline_score']>=.5):raise ValueError('Score/cutoff decision differs')
    if first['flagged']!=second['flagged']:return dict(row,decision='review_disagreement',flagged=None)
    return dict(row,decision='flag' if first['flagged'] else 'not_flagged',flagged=first['flagged'])


def verify_folds(first,second,inputs):
    groups={cid:g for g,cs in inputs['groups'].items() for cid in cs};values={r['case_id']:r for r in inputs['cases']}
    indices=[]
    for model,width in ((first,4),(second,7)):
        predictions={r['case_id']:r for r in model['predictions']}
        if len(predictions)!=len(model['predictions']) or set(predictions)!=set(values):raise ValueError('Prediction case partition differs')
        partition={};seen=set()
        for f in model['folds']:
            train=f['train_case_ids'];test=f['held_out_case_ids']
            if set(train)&set(test) or {groups[c] for c in train}&{groups[c] for c in test} or set(test)&seen:raise ValueError('Invalid participant fold separation')
            seen.update(test);partition[tuple(sorted(test))]=tuple(sorted(train))
            x=np.array([values[c]['features'][:width] for c in train])
            if not np.allclose(x.mean(axis=0),f['scaler_mean']) or not np.allclose(x.std(axis=0),f['scaler_scale']):raise ValueError('Training scaler differs')
            for cid in test:
                score=float(expit(np.dot((np.array(values[cid]['features'][:width])-f['scaler_mean'])/f['scaler_scale'],f['coefficients'])+f['intercept']))
                p=predictions[cid]
                if p['label']!=values[cid]['label'] or p['status']!='scored' or abs(score-p['baseline_score'])>1e-12 or p['flagged']!=(score>=.5):raise ValueError('Prediction does not reproduce')
        if seen!={cid for cid,r in values.items() if r['features'] is not None}:raise ValueError('Eligible fold coverage differs')
        indices.append(partition)
    if indices[0]!=indices[1]:raise ValueError('Stages have unmatched training/held-out partitions')


def run(source,output):
    source,output=map(Path,(source,output));result=json.loads((source/'comparison.json').read_text());inputs=json.loads((source/'inputs.json').read_text());protocol=json.loads((source/'protocol.json').read_text())
    if result['protocol_sha256']!=digest(source/'protocol.json') or result['inputs_sha256']!=digest(source/'inputs.json') or protocol['role']!='inspected_burst_recoil_development' or protocol['threshold']!=.5:raise ValueError('Source matched experiment receipt differs')
    first=result['models']['matched_coverage_baseline'];second=result['models']['with_burst'];verify_folds(first,second,inputs)
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='inspected_confirmation_policy_development',recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        rule='Both scored positive: flag; both scored negative: not flagged; any disagreement or missing stage: review. Cutoffs remain0.5.',
        source_sha256={n:digest(source/n) for n in ('comparison.json','inputs.json','protocol.json')},code_sha256=digest(__file__),
        caveat='Post-feedback hypothesis on inspected cases. No tuning/refitting. Stages are correlated, not independent evidence. Reviews are unresolved, not correct negatives. No holdout reading or automatic deployment.'))
    lookup={p['case_id']:p for p in second['predictions']};rows=[confirm(p,lookup[p['case_id']]) for p in first['predictions']]
    counts={label:dict(Counter(r['decision'] for r in rows if r['label']==label)) for label in ('cheating','legitimate')}
    for label in counts:
        for decision in ('flag','not_flagged','review_disagreement','review_missing_evidence'):counts[label].setdefault(decision,0)
    summary=dict(counts_by_label=counts,cases=len(rows),
        flag_fraction_of_all_positives=counts['cheating']['flag']/sum(counts['cheating'].values()),
        false_flag_fraction_of_all_legitimate=counts['legitimate']['flag']/sum(counts['legitimate'].values()),
        legitimate_flag_or_review=sum(v for k,v in counts['legitimate'].items() if k!='not_flagged'),
        note='All-case fractions retain missing/disagreement cases in denominators; also inspect review burden. Not a population FPR or calibrated probability.')
    write_json(output/'result.json',dict(predictions=rows,summary=summary,protocol_sha256=digest(output/'protocol.json'),promotion_status='development_only_not_frozen'))
    lines=['# Two-stage confirmation development policy','','| Source label | Flag | Not flagged | Review: disagreement | Review: missing evidence |','| --- | ---: | ---: | ---: | ---: |']
    for label,c in counts.items():lines.append(f"| {label} | {c['flag']} | {c['not_flagged']} | {c['review_disagreement']} | {c['review_missing_evidence']} |")
    lines+=['',f"Legitimate cases requiring a flag or review: {summary['legitimate_flag_or_review']}.",'','Review is not a clean decision. No model changes, fresh evaluation or population guarantee. Both stages use identical participant training/test folds.','', '| Case | Label | First score | Second score | Decision |','| --- | --- | ---: | ---: | --- |']
    for r in rows:
        if r['decision']!='not_flagged':lines.append(f"| {r['case_id']} | {r['label']} | {r['first_score']} | {r['second_score']} | {r['decision']} |")
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines[:9]),flush=True);return rows,summary


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);run(a.source,a.output)


if __name__=='__main__':main()

"""One fixed development-only two-tick motion smoothing comparison."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.baseline import digest, write_json
from aimguard.development_models import grouped_predictions
from aimguard.final_error_audit import movement


def counts(predictions):
    scored=[r for r in predictions if r['status']=='scored']
    return dict(TP=sum(r['flagged'] and r['label']=='cheating' for r in scored),
        FN=sum(not r['flagged'] and r['label']=='cheating' for r in scored),
        FP=sum(r['flagged'] and r['label']=='legitimate' for r in scored),
        TN=sum(not r['flagged'] and r['label']=='legitimate' for r in scored),
        unresolved=len(predictions)-len(scored))


def group_vector(partition,case_ids):
    lookup={}
    for group,members in partition.items():
        for cid in members:
            if cid in lookup:raise ValueError('Duplicate group assignment')
            lookup[cid]=str(group)
    if set(lookup)!=set(case_ids):raise ValueError('Group partition differs from cases')
    return [lookup[cid] for cid in case_ids]


def run(pool, reference, output):
    pool,reference,output=map(Path,(pool,reference,output))
    source=json.loads((pool/'inputs.json').read_text());old=json.loads((reference/'comparison.json').read_text())['models']['cost_ratio_threshold']
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='one_fixed_development_candidate_not_fresh_evaluation',
        code_sha256=digest(__file__),measurement_code_sha256=digest('aimguard/final_error_audit.py'),
        source_sha256={str(pool/'inputs.json'):digest(pool/'inputs.json'),str(reference/'comparison.json'):digest(reference/'comparison.json')},
        recipe='Replace only the two movement features with two-tick averaged angular velocity and its acceleration; require all supporting near-shot intervals. Same windows and original two tracking features. Case medians, log1p, training-fold scaler, balanced logistic C=1, cutoff .75.',
        policy='Same 63 inspected development cases and 61 participant groups. No feature/lag/threshold grid. Favorable diagnostic only if no increase in false flags or unresolved cases, no loss of detections, and at least one strict improvement.',
        limitation='Hypothesis informed by consumed-case audit. Neither development CV nor a favorable result establishes fresh improvement. Never score the consumed 55 with this candidate; retain the deployed frozen model.'))
    rows=[]
    for i,c in enumerate(source['cases'],1):
        directory=pool/'analysis'/f'job_{i:04d}'
        if digest(directory/'report.json')!=c['report_sha256']:raise ValueError('Development report changed')
        report=json.loads((directory/'report.json').read_text())
        frame=pd.read_csv(directory/'telemetry.csv',usecols=['tick','yaw','pitch','segment_id','active','phase_status'])
        measurements=[];excluded=Counter()
        for w in report['engagements']:
            part=frame.loc[frame.segment_id.eq(w['segment_id'])&frame.tick.between(w['start_tick'],w['end_tick'])]
            if len(part)!=w['samples'] or not part.active.all() or not part.phase_status.eq('live').all():raise ValueError('Unsupported motion window')
            if len(part)<4 or not (np.diff(part.tick.to_numpy())==1).all():
                excluded['short_or_nonconsecutive_window']+=1
                continue
            values=movement(part,w,64)['two_tick_features']
            if all(v is not None and np.isfinite(v) for v in values):measurements.append(values)
        if len(measurements)<5:raise ValueError('Candidate loses eligible case coverage')
        values=np.median(measurements,axis=0).tolist()+c['features'][2:]
        rows.append(dict(case_id=c['case_id'],label=c['label'],original_features=c['features'],features=values,
                         report_sha256=c['report_sha256'],telemetry_sha256=digest(directory/'telemetry.csv'),eligible_windows=len(measurements),excluded_windows=dict(excluded)))
        print(f'Prepared development case {i}/{len(source["cases"])}',flush=True)
    write_json(output/'inputs.json',dict(cases=rows,groups=source['groups']))
    ids=[c['case_id'] for c in rows];labels=[int(c['label']=='cheating') for c in rows]
    groups=group_vector(source['groups'],ids)
    models={}
    for name,key in [('original','original_features'),('two_tick','features')]:
        fitted=grouped_predictions([c[key] for c in rows],labels,groups,ids,'log1p')
        for p in fitted['predictions']:
            if p['status']=='scored':p['flagged']=p['baseline_score']>=.75
        # Avoid retaining metrics calculated by the helper at its default .5 cutoff.
        fitted.pop('metrics',None);fitted['counts']=counts(fitted['predictions']);models[name]=fitted
    old_by_id={p['case_id']:p for p in old['predictions']}
    for p in models['original']['predictions']:
        q=old_by_id[p['case_id']]
        if p['flagged']!=q['flagged'] or not np.isclose(p['baseline_score'],q['baseline_score'],rtol=0,atol=1e-12):raise ValueError('Original development scores do not reproduce')
    base=models['original']['counts'];new=models['two_tick']['counts']
    favorable=(new['FP']<=base['FP'] and new['TP']>=base['TP'] and new['unresolved']<=base['unresolved'] and (new['FP']<base['FP'] or new['TP']>base['TP']))
    result=dict(models=models,favorable_development_diagnostic=favorable,model_promoted=False,
        protocol_sha256=digest(output/'protocol.json'),inputs_sha256=digest(output/'inputs.json'),
        note='One candidate only. No source model, threshold or consumed-cohort result changed; no fresh evaluation claim.')
    write_json(output/'comparison.json',result)
    (output/'report.md').write_text('# Fixed two-tick development comparison\n\n'+json.dumps({k:v['counts'] for k,v in models.items()},indent=2)+f'\n\nFavorable diagnostic: {favorable}. Model promoted: False. Original scores reproduce exactly. No consumed-case rescoring or fresh accuracy claim.\n')
    print(json.dumps(dict(counts={k:v['counts'] for k,v in models.items()},favorable=favorable)),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pool',type=Path);p.add_argument('reference',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.pool,a.reference,a.output)

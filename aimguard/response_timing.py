"""Fixed pre-shot yaw/bearing response timing experiment on phase-clean tracks."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
import importlib.metadata
from pathlib import Path

import numpy as np

from aimguard.baseline import digest,write_json
from aimguard.tracking_models import with_abstentions,case_features,TRACKING_RECIPES

FEATURES=['median_zero_lag_correlation','median_zero_minus_delayed_correlation','median_zero_minus_leading_correlation']


def window_response(window,tickrate):
    if not np.isfinite(tickrate) or tickrate<=0:raise ValueError('Invalid tickrate')
    candidate=window['nearest_before_first_shot']
    if candidate is None:return None,'no_pre_shot_candidate'
    matches=[t for t in window['tracks'] if t['opponent_id']==candidate]
    if len(matches)!=1:raise ValueError('Expected one geometric candidate track')
    track=matches[0];ticks=np.asarray(track['ticks']);segments=np.asarray(track['segment_ids'])
    yaw=np.asarray(track['yaw_rate_dps'],dtype=float);bearing=np.asarray(track['bearing_rate_dps'],dtype=float)
    if ticks.ndim!=1 or any(a.shape!=ticks.shape for a in (segments,yaw,bearing)) or not np.isfinite(ticks).all() or (ticks%1).any() or (np.diff(ticks)<=0).any():raise ValueError('Invalid timing sample alignment')
    first=window['shot_ticks'][0];ends=np.flatnonzero(ticks==first-1)
    if len(ends)!=1:return None,'missing_pre_shot_endpoint'
    end=ends[0]
    if segments[end]<0 or not np.isfinite([yaw[end],bearing[end]]).all():return None,'invalid_endpoint'
    start=end
    while start>0 and ticks[start-1]>=first-.5*tickrate and ticks[start]-ticks[start-1]==1 and segments[start-1]==segments[end] and np.isfinite([yaw[start-1],bearing[start-1]]).all():start-=1
    # The first retained rate must have its preceding sample inside the same segment.
    start+=1
    lag=max(1,int(round(.1*tickrate)));indices=np.arange(start+lag,end-lag+1)
    if len(indices)<8:return None,'insufficient_common_pre_shot_support'
    a=yaw[indices];series=[bearing[indices],bearing[indices-lag],bearing[indices+lag]]
    if np.std(a)<1 or any(np.std(b)<1 for b in series):return None,'insufficient_angular_rate_variation'
    correlations=[float(np.clip(np.corrcoef(a,b)[0,1],-1,1)) for b in series]
    zero,delayed,leading=correlations
    return dict(features=[zero,zero-delayed,zero-leading],correlations=correlations,triplets=len(indices),lag_ticks=lag,
        first_support_tick=int(ticks[start]),last_support_tick=int(ticks[end])),None


def case_response(windows,tickrate):
    results=[];excluded=Counter()
    for window in windows:
        r,reason=window_response(window,tickrate)
        if r is None:excluded[reason]+=1
        else:results.append(r)
    coverage=dict(eligible_windows=len(results),excluded_windows=dict(excluded))
    return (np.median([r['features'] for r in results],axis=0).tolist() if len(results)>=5 else None),coverage


def compare(comparison,output):
    comparison,output=map(Path,(comparison,output));baseline=json.loads((comparison/'comparison.json').read_text());source=json.loads((comparison/'inputs.json').read_text());protocol=json.loads((comparison/'protocol.json').read_text())
    if (baseline['protocol_sha256']!=digest(comparison/'protocol.json') or baseline['inputs_sha256']!=digest(comparison/'inputs.json')
        or protocol['role']!='inspected_v06_development' or protocol['threshold']!=.5 or protocol['hyperparameters']!=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0)
        or protocol['recipe']!=TRACKING_RECIPES['speed_and_tracking'] or source['groups']!=protocol['groups']):raise ValueError('Phase-clean source receipt differs')
    ids=[r['case_id'] for r in source['cases']];members=[cid for cs in source['groups'].values() for cid in cs]
    if len(set(ids))!=len(ids) or len(set(members))!=len(members) or set(ids)!=set(members):raise ValueError('Case/group identity differs')
    if any(r['label'] not in ('cheating','legitimate') for r in source['cases']):raise ValueError('Unknown source label')
    old=baseline['models']['v06_speed_and_tracking']['predictions']
    if len(old)!=len(ids) or {r['case_id']:r['label'] for r in old}!={r['case_id']:r['label'] for r in source['cases']}:raise ValueError('Baseline label identity differs')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='inspected_response_timing_development',recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        dependencies={n:importlib.metadata.version(n) for n in ('numpy','scipy','scikit-learn')},
        baseline_features=protocol['recipe']['features'],new_features=FEATURES,pre_seconds=.5,lag_seconds=.1,min_common_triplets=8,
        minimum_rate_std_dps=1,min_windows=5,threshold=.5,hyperparameters=protocol['hyperparameters'],
        transform='log1p original four features; identity signed correlations; training-only scaling',
        comparison_sha256=digest(comparison/'comparison.json'),inputs_sha256=digest(comparison/'inputs.json'),
        code_sha256={n:digest(Path(__file__).with_name(n)) for n in ('response_timing.py','tracking_models.py','development_models.py')},
        note='Fixed signed zero/delayed/leading comparison, no lag/threshold/feature search. Geometric correlation is not causal response latency, actual mouse input, visibility or activation. Previously inspected data, not fresh evaluation.'))
    rows=[];values=[]
    for i,row in enumerate(source['cases'],1):
        path=comparison/'tracking'/f'case_{i:04d}.json'
        if digest(path)!=row['tracking_sha256']:raise ValueError('Tracking checksum differs')
        tracking=json.loads(path.read_text())
        if tracking['summary']['case_id']!=row['case_id'] or tracking['summary']['label']!=row['label']:raise ValueError('Tracking identity differs')
        old,old_coverage=case_features(tracking['windows'],tracking['assumed_tickrate_hz'])
        if row['features'] is not None and (old is None or not np.allclose(old,row['features'][2:])):raise ValueError('Original tracking features differ')
        feature,coverage=case_response(tracking['windows'],tracking['assumed_tickrate_hz'])
        vector=[*np.log1p(row['features']),*feature] if feature is not None and row['features'] is not None else None
        values.append(vector);rows.append(dict(case_id=row['case_id'],label=row['label'],features=vector,response_features=feature,coverage=coverage,tracking_sha256=digest(path)))
    write_json(output/'inputs.json',dict(cases=rows,groups=source['groups']))
    group_for={cid:g for g,cs in source['groups'].items() for cid in cs}
    model=with_abstentions(values,[int(r['label']=='cheating') for r in rows],[group_for[cid] for cid in ids],ids,'identity')
    for p in model['predictions']:
        if p['status']=='abstained' and p.get('error','').startswith('Fewer than'):p['error']='Fewer than five response-eligible windows or missing baseline evidence'
    result=dict(models=dict(phase_clean_linear=baseline['models']['v06_speed_and_tracking'],tracking_and_response=model),protocol_sha256=digest(output/'protocol.json'),inputs_sha256=digest(output/'inputs.json'),promotion_status='not_frozen_or_deployed')
    write_json(output/'comparison.json',result)
    lines=['# Pre-shot response timing development experiment','','| Recipe | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,m in result['models'].items():
        c=m['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {m['metrics']['abstentions']} |")
    lines+=['','No fresh accuracy or activation claim; no model promotion. Missing coverage is not a correct negative.'];(output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines));return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('comparison',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);compare(a.comparison,a.output)


if __name__=='__main__':main()

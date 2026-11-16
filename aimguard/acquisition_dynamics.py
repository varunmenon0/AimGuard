"""Exploratory pre-shot acquisition dynamics; no intended-target or visibility claim."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np
from aimguard.baseline import digest,write_json
from aimguard.core import angle_delta
from aimguard.tracking_models import with_abstentions

PRE_SECONDS=.5
MIN_INTERVALS=16
MIN_CLOSURE_DEGREES=3.
MIN_SETTLING_INTERVALS=3
MIN_WINDOWS=5
MIN_TRANSITIONS=3
FEATURES=['transition_fraction','median_player_closure_concentration','median_settling_speed_ratio']


def pre_segment(window,tickrate):
    if not np.isfinite(tickrate) or tickrate<=0:raise ValueError('Invalid tickrate')
    candidate=window['nearest_before_first_shot']
    if candidate is None:return None,'no_geometric_candidate'
    matches=[track for track in window['tracks'] if track['opponent_id']==candidate]
    if len(matches)!=1:raise ValueError('Expected one fixed pre-shot candidate')
    track=matches[0];ticks=np.asarray(track['ticks'],dtype=float);segments=np.asarray(track['segment_ids'])
    arrays=[np.asarray(track[key],dtype=float) for key in ('signed_error_degrees','yaw_rate_dps','bearing_rate_dps')]
    if ticks.ndim!=1 or any(len(values)!=len(ticks) for values in [segments,*arrays]):raise ValueError('Misaligned dynamics samples')
    if not np.isfinite(ticks).all() or (ticks%1!=0).any() or (np.diff(ticks)<=0).any():raise ValueError('Ticks must increase strictly as integers')
    error,yaw,bearing=arrays;first=window['shot_ticks'][0];endpoints=np.flatnonzero(ticks==first-1)
    if len(endpoints)!=1:return None,'missing_exact_pre_shot_endpoint'
    end=endpoints[0]
    if segments[end]<0 or not np.isfinite(error[end]):return None,'invalid_endpoint'
    start=end
    while (start>0 and ticks[start-1]>=first-PRE_SECONDS*tickrate and ticks[start]-ticks[start-1]==1
           and segments[start-1]==segments[end] and np.isfinite(error[start-1])):start-=1
    if end-start<MIN_INTERVALS:return None,'insufficient_contiguous_pre_shot_intervals'
    if not np.isfinite(np.r_[error[start:end+1],yaw[start+1:end+1],bearing[start+1:end+1]]).all():raise ValueError('Nonfinite supporting dynamics values')
    if (abs(error[start:end+1])>180).any():raise ValueError('Invalid horizontal error')
    return dict(ticks=ticks[start:end+1].astype(int).tolist(),error=error[start:end+1],
                yaw_step=yaw[start+1:end+1]/tickrate,relative_speed=abs(yaw[start+1:end+1]-bearing[start+1:end+1])),None


def window_dynamics(window,tickrate):
    segment,reason=pre_segment(window,tickrate)
    if segment is None:return None,reason
    error=segment['error'];absolute=abs(error)
    observed=np.maximum(absolute[:-1]-absolute[1:],0.)
    # Hold bearing fixed to ask whether the recorded yaw step itself closes error.
    view_only=np.maximum(absolute[:-1]-abs(angle_delta(error[:-1]-segment['yaw_step'])),0.)
    supported=np.minimum(observed,view_only)
    total=float(supported.sum());net=float(absolute[0]-absolute[-1])
    qualifies=net>=MIN_CLOSURE_DEGREES and total>=MIN_CLOSURE_DEGREES
    result=dict(valid_intervals=len(observed),start_tick=segment['ticks'][0],end_tick=segment['ticks'][-1],
        net_error_reduction_degrees=net,player_supported_closure_degrees=total,is_transition=bool(qualifies),
        concentration=None,settling_speed_ratio=None,settling_intervals=0,unavailable_reason=None)
    if not qualifies:return result,None
    peak=int(np.argmax(supported));speed=segment['relative_speed'];after=speed[peak+1:]
    result.update(concentration=float(supported[peak]/total),peak_interval_end_tick=segment['ticks'][peak+1],
        settling_intervals=len(after))
    if len(after)<MIN_SETTLING_INTERVALS:result['unavailable_reason']='insufficient_post_peak_pre_shot_intervals'
    elif speed[peak]<=1e-9:result['unavailable_reason']='zero_peak_relative_speed'
    else:result['settling_speed_ratio']=float(np.median(after)/speed[peak])
    return result,None


def case_dynamics(windows,tickrate):
    valid=[];usable=[];excluded=Counter();unavailable=Counter()
    for window in windows:
        result,reason=window_dynamics(window,tickrate)
        if result is None:excluded[reason]+=1;continue
        valid.append(result)
        if result['is_transition']:
            if result['settling_speed_ratio'] is None:unavailable[result['unavailable_reason']]+=1
            else:usable.append(result)
    transitions=sum(row['is_transition'] for row in valid)
    coverage=dict(valid_windows=len(valid),qualifying_transitions=transitions,usable_transitions=len(usable),
        excluded_windows=dict(excluded),unavailable_settling=dict(unavailable))
    if len(valid)<MIN_WINDOWS or len(usable)<MIN_TRANSITIONS:return None,coverage
    return [transitions/len(valid),float(np.median([r['concentration'] for r in usable])),
            float(np.median([r['settling_speed_ratio'] for r in usable]))],coverage


def compare(pool,baseline_directory,output):
    pool,baseline_directory,output=map(Path,(pool,baseline_directory,output))
    manifest=json.loads((pool/'manifest.json').read_text());receipt=json.loads((pool/'pool-receipt.json').read_text())
    baseline_protocol=json.loads((baseline_directory/'protocol.json').read_text());baseline_inputs=json.loads((baseline_directory/'inputs.json').read_text())
    baseline=json.loads((baseline_directory/'comparison.json').read_text())
    if (manifest.get('role')!='development' or manifest.get('features_inspected') is not True
        or receipt['manifest_sha256']!=digest(pool/'manifest.json') or baseline_protocol['manifest_sha256']!=digest(pool/'manifest.json')
        or baseline['protocol_sha256']!=digest(baseline_directory/'protocol.json') or baseline['inputs_sha256']!=digest(baseline_directory/'inputs.json')
        or baseline_inputs['groups']!=receipt['groups']):raise ValueError('Inspected pool/baseline receipt mismatch')
    expected=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0)
    if baseline_protocol['threshold']!=.5 or baseline_protocol['hyperparameters']!=expected:
        raise ValueError('Baseline classifier protocol differs from fixed comparison')
    recipes=dict(acquisition_dynamics=dict(features=FEATURES,transform='log1p'),
        tracking_and_dynamics=dict(features=[*baseline_protocol['recipes']['pre_shot_tracking']['features'],*FEATURES],transform='log1p'))
    output.mkdir(parents=True,exist_ok=False)
    protocol=dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(),role='exploratory_development',recipes=recipes,
        pre_seconds=PRE_SECONDS,min_intervals=MIN_INTERVALS,min_closure_degrees=MIN_CLOSURE_DEGREES,
        min_settling_intervals=MIN_SETTLING_INTERVALS,min_windows=MIN_WINDOWS,min_usable_transitions=MIN_TRANSITIONS,
        threshold=.5,hyperparameters=baseline_protocol['hyperparameters'],manifest_sha256=digest(pool/'manifest.json'),
        baseline_comparison_sha256=digest(baseline_directory/'comparison.json'),
        code_sha256={name:digest(Path(__file__).with_name(name)) for name in ('acquisition_dynamics.py','tracking_models.py','development_models.py','baseline.py','core.py')},
        dependencies={name:importlib.metadata.version(name) for name in ('numpy','scipy','scikit-learn')},
        cases=[dict(case_id=case['case_id']) for case in manifest['cases']],
        note='Choices fixed before this fit. Geometry/coverage thresholds are unvalidated engineering choices, not a detector. No hyperparameter or threshold search.')
    write_json(output/'protocol.json',protocol)
    membership=[case_id for members in receipt['groups'].values() for case_id in members]
    if len(set(membership))!=len(membership):raise ValueError('Participant groups repeat a case')
    groups_by_case={case_id:int(group) for group,cases in receipt['groups'].items() for case_id in cases}
    cases=manifest['cases'];ids=[case['case_id'] for case in cases]
    if len(set(ids))!=len(ids) or set(ids)!=set(groups_by_case):raise ValueError('Duplicate/missing group identities')
    if any(case['label'] not in ('cheating','legitimate') for case in cases):raise ValueError('Unknown development label')
    for name in ('pre_shot_tracking','speed_and_tracking'):
        predictions=baseline['models'][name]['predictions']
        if len(predictions)!=len(cases) or {row['case_id']:row['label'] for row in predictions}!={case['case_id']:case['label'] for case in cases}:
            raise ValueError('Baseline case labels/coverage mismatch')
    groups=[groups_by_case[case_id] for case_id in ids];labels=[int(case['label']=='cheating') for case in cases]
    vectors=[];combined=[];coverage=[]
    for index,case in enumerate(cases,1):
        path=pool/'tracking'/f'case_{index:04d}.json';expected=receipt['cases'][index-1]
        if expected['case_id']!=case['case_id'] or expected['tracking_sha256']!=digest(path):raise ValueError('Tracking checksum mismatch')
        record=json.loads(path.read_text())
        if record['summary']['case_id']!=case['case_id'] or record['summary']['label']!=case['label']:raise ValueError('Tracking identity mismatch')
        values,counts=case_dynamics(record['windows'],record['assumed_tickrate_hz'])
        old=baseline_inputs['tracking'][index-1]
        if old['case_id']!=case['case_id'] or old['tracking_sha256']!=digest(path):raise ValueError('Baseline tracking receipt mismatch')
        vectors.append(values);combined.append([*old['features'],*values] if values is not None and old['features'] is not None else None)
        coverage.append(dict(case_id=case['case_id'],label=case['label'],features=values,tracking_sha256=digest(path),**counts))
    write_json(output/'inputs.json',dict(cases=coverage,groups=receipt['groups']))
    models={name:baseline['models'][name] for name in ('pre_shot_tracking','speed_and_tracking')}
    for name,values in [('acquisition_dynamics',vectors),('tracking_and_dynamics',combined)]:
        result=with_abstentions(values,labels,groups,ids,'log1p')
        for row in result['predictions']:
            if row['status']=='abstained' and row.get('error','').startswith('Fewer than'):
                row['error']=f'Need {MIN_WINDOWS} valid pre-shot windows and {MIN_TRANSITIONS} usable transitions'
        models[name]=result
    result=dict(cases=len(cases),participant_groups=len(set(groups)),models=models,
        protocol_sha256=digest(output/'protocol.json'),inputs_sha256=digest(output/'inputs.json'),
        interpretation='Previously inspected development pool; missing transition coverage abstains, not negative evidence. No new held-out accuracy claim.')
    write_json(output/'comparison.json',result)
    lines=['# Pre-shot acquisition dynamics development experiment','',
        'Previously inspected cases only. Existing baseline predictions are copied unchanged; new recipes use the same groups, C=1 and cutoff 0.5.',
        'Fitting/scaling is within eligible training groups only. Missing dynamics is explicit abstention, never a negative label.',
        '', '| Recipe | TP | FN | FP | TN | Abstentions |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,model in models.items():
        c=model['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {model['metrics']['abstentions']} |")
    lines+=['','Coverage is part of the result. Rates use scored cases; recipes with different coverage are not directly comparable.',
        'Dynamics require a net closure and summed player-supported closure of at least 3 degrees. Player support is capped by observed improvement and a fixed-bearing yaw-only improvement; opponent motion alone does not create it.',
        'Concentration is the largest supported interval closure divided by total supported closure. Settling ratio is median relative speed strictly after that interval, divided by its relative speed. At least three later pre-shot intervals are required.',
        'First ties choose the earlier peak; all samples stay inside one contiguous fixed-opponent pre-shot segment. No post-shot observations, damage-based selection, visibility or intended-target annotations are used.',
        'These unvalidated engineering cutoffs and sample-informed feature choices need later fresh evaluation. No replacement model is frozen and the original failed frozen evaluation remains unchanged.','']
    (output/'report.md').write_text('\n'.join(lines));print('\n'.join(lines[:12]),flush=True)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('pool',type=Path);parser.add_argument('baseline_directory',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
    compare(args.pool,args.baseline_directory,args.output)


if __name__=='__main__':main()

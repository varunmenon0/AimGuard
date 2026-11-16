"""Exploratory repeated pre-shot correction consistency; no cheat-specific claim."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np
from aimguard.baseline import digest, write_json
from aimguard.core import angle_delta
from aimguard.acquisition_dynamics import pre_segment, PRE_SECONDS, MIN_INTERVALS, MIN_CLOSURE_DEGREES
from aimguard.tracking_models import with_abstentions

MIN_WINDOWS = 5
MIN_TRANSITIONS = 3
FEATURES = ['median_positive_correction_r_squared', 'positive_gain_relative_mad', 'positive_fit_fraction']


def correction_fit(window, tickrate):
    segment, reason = pre_segment(window, tickrate)
    if segment is None: return None, reason
    error = segment['error']; absolute = abs(error)
    differences = np.diff(error)
    if (abs(differences) > 180).any(): return None, 'horizontal_error_branch_crossing'
    observed = np.maximum(absolute[:-1]-absolute[1:], 0.)
    view_only = np.maximum(absolute[:-1]-abs(angle_delta(error[:-1]-segment['yaw_step'])), 0.)
    support = float(np.minimum(observed, view_only).sum())
    net = float(absolute[0]-absolute[-1])
    result = dict(valid_intervals=len(differences), start_tick=segment['ticks'][0], end_tick=segment['ticks'][-1],
                  player_supported_closure_degrees=support, net_closure_degrees=net,
                  qualifying_transition=False, positive_fit=False, gain=None, r_squared=None, unavailable_reason=None)
    if net < MIN_CLOSURE_DEGREES or support < MIN_CLOSURE_DEGREES: return result, None
    result['qualifying_transition'] = True
    previous = error[:-1]
    relative_velocity = -differences*tickrate
    denominator = float(previous @ previous)
    variance = float(np.sum((relative_velocity-relative_velocity.mean())**2))
    if denominator <= 1e-12 or variance <= 1e-12:
        result['unavailable_reason'] = 'insufficient_error_or_response_variation'; return result, None
    gain = float(previous @ relative_velocity / denominator)
    residual = relative_velocity-gain*previous
    r_squared = float(np.clip(1-float(residual @ residual)/variance, 0., 1.))
    result.update(gain=gain, r_squared=r_squared, positive_fit=bool(gain > 0))
    return result, None


def case_feedback(windows, tickrate):
    valid = []; positive = []; excluded = Counter(); unavailable = Counter()
    for window in windows:
        result, reason = correction_fit(window, tickrate)
        if result is None: excluded[reason] += 1; continue
        valid.append(result)
        if result['positive_fit']: positive.append(result)
        elif result['unavailable_reason']: unavailable[result['unavailable_reason']] += 1
    coverage = dict(valid_windows=len(valid), qualifying_transitions=sum(r['qualifying_transition'] for r in valid),
                    usable_transitions=len(positive), excluded_windows=dict(excluded), unavailable_fits=dict(unavailable))
    if len(valid) < MIN_WINDOWS or len(positive) < MIN_TRANSITIONS: return None, coverage
    gains = np.array([r['gain'] for r in positive]); median = float(np.median(gains))
    return [float(np.median([r['r_squared'] for r in positive])), float(np.median(abs(gains-median))/median),
            len(positive)/len(valid)], coverage


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
    recipes=dict(correction_consistency=dict(features=FEATURES,transform='log1p'),
        tracking_and_consistency=dict(features=[*baseline_protocol['recipes']['pre_shot_tracking']['features'],*FEATURES],transform='log1p'))
    output.mkdir(parents=True,exist_ok=False)
    protocol=dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(),role='exploratory_development',recipes=recipes,
        pre_seconds=PRE_SECONDS,min_intervals=MIN_INTERVALS,min_closure_degrees=MIN_CLOSURE_DEGREES,
        min_windows=MIN_WINDOWS,min_usable_transitions=MIN_TRANSITIONS,measurement='Proportional correction fit to signed horizontal error; player-supported alignment required; positive gain only for fit/gain summaries',
        threshold=.5,hyperparameters=baseline_protocol['hyperparameters'],manifest_sha256=digest(pool/'manifest.json'),
        baseline_comparison_sha256=digest(baseline_directory/'comparison.json'),
        code_sha256={name:digest(Path(__file__).with_name(name)) for name in ('correction_consistency.py','acquisition_dynamics.py','tracking_models.py','development_models.py','baseline.py','core.py')},
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
        values,counts=case_feedback(record['windows'],record['assumed_tickrate_hz'])
        old=baseline_inputs['tracking'][index-1]
        if old['case_id']!=case['case_id'] or old['tracking_sha256']!=digest(path):raise ValueError('Baseline tracking receipt mismatch')
        vectors.append(values);combined.append([*old['features'],*values] if values is not None and old['features'] is not None else None)
        windows=[]
        for window in record['windows']:
            measured,reason=correction_fit(window,record['assumed_tickrate_hz'])
            windows.append(dict(engagement_id=window['engagement_id'],first_shot_tick=window['shot_ticks'][0],
                                weapon=window['weapon'],measurement=measured,excluded_reason=reason))
        coverage.append(dict(case_id=case['case_id'],label=case['label'],features=values,tracking_sha256=digest(path),windows=windows,**counts))
    write_json(output/'inputs.json',dict(cases=coverage,groups=receipt['groups']))
    models={name:baseline['models'][name] for name in ('pre_shot_tracking','speed_and_tracking')}
    for name,values in [('correction_consistency',vectors),('tracking_and_consistency',combined)]:
        result=with_abstentions(values,labels,groups,ids,'log1p')
        for row in result['predictions']:
            if row['status']=='abstained' and row.get('error','').startswith('Fewer than'):
                row['error']=f'Need {MIN_WINDOWS} valid pre-shot windows and {MIN_TRANSITIONS} usable transitions'
        models[name]=result
    result=dict(cases=len(cases),participant_groups=len(set(groups)),models=models,
        protocol_sha256=digest(output/'protocol.json'),inputs_sha256=digest(output/'inputs.json'),
        interpretation='Previously inspected development pool; missing transition coverage abstains, not negative evidence. No new held-out accuracy claim.')
    write_json(output/'comparison.json',result)
    lines=['# Repeated pre-shot correction consistency experiment','',
        'Previously inspected cases only. Existing baseline predictions are copied unchanged; new recipes use the same groups, C=1 and cutoff 0.5.',
        'Fitting/scaling is within eligible training groups only. Missing correction coverage is explicit abstention, never a negative label.',
        '', '| Recipe | TP | FN | FP | TN | Abstentions |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,model in models.items():
        c=model['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {model['metrics']['abstentions']} |")
    lines+=['','All comparisons are development feedback, not independent accuracy estimates. Coverage differences must be included.',
        'Only fixed-opponent contiguous pre-shot segments are used. At least three degrees net and player-supported closure are required, so opponent movement alone cannot qualify.',
        'For each transition, signed relative angular velocity is fitted to previous signed horizontal error through the origin. Positive proportional gains contribute clipped R-squared and cross-window relative gain MAD; at least three positive fits and five valid windows per case are required.',
        'Case features are median positive-fit R-squared, relative gain MAD, and positive-fit fraction of valid windows. These are unvalidated kinematic proxies, not mouse-input identification or evidence of a specific cheat.',
        'No cutoff, feature-subset or parameter search; no full-pool model is frozen. Historical evaluation remains unchanged.','']
    (output/'report.md').write_text('\n'.join(lines));print('\n'.join(lines[:12]),flush=True)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('pool',type=Path);parser.add_argument('baseline_directory',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
    compare(args.pool,args.baseline_directory,args.output)


if __name__=='__main__':main()

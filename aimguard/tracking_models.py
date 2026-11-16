"""Prespecified grouped development comparisons of pre-shot tracking features."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from aimguard.baseline import digest, evaluation_metrics, write_json
from aimguard.development_models import RECIPES, grouped_predictions, load_development, participant_groups

PRE_SECONDS = .2
MIN_INTERVALS = 8
MIN_WINDOWS = 5
TRACKING_FEATURES = ['median_pre_shot_absolute_error_degrees','median_pre_shot_absolute_relative_rate_dps']
TRACKING_RECIPES = {
    'pre_shot_tracking': dict(features=TRACKING_FEATURES,transform='log1p'),
    'speed_and_tracking': dict(features=['p95_speed','mean_accel',*TRACKING_FEATURES],transform='log1p'),
}


def window_features(window, tickrate):
    """Only the fixed geometric candidate and pre-first-shot samples are eligible."""
    if not np.isfinite(tickrate) or tickrate<=0:
        raise ValueError('Invalid tracking tickrate')
    candidate=window['nearest_before_first_shot']
    if candidate is None:
        return None,'no_pre_shot_candidate'
    matches=[track for track in window['tracks'] if track['opponent_id']==candidate]
    if len(matches)!=1:
        raise ValueError('Expected exactly one pre-shot candidate track')
    track=matches[0]
    ticks=np.asarray(track['ticks'],dtype=float)
    segments=np.asarray(track['segment_ids'])
    arrays=[track[name] for name in ('signed_error_degrees','yaw_rate_dps','bearing_rate_dps')]
    if any(len(values)!=len(ticks) for values in [segments,*arrays]):
        raise ValueError('Tracking sample arrays must align')
    if not np.isfinite(ticks).all() or (ticks%1!=0).any() or (np.diff(ticks)<=0).any():
        raise ValueError('Tracking ticks must increase strictly as integers')
    error,yaw,bearing=[np.asarray(values,dtype=float) for values in arrays]
    first=window['shot_ticks'][0]
    endpoint=np.flatnonzero(ticks==first-1)
    if len(endpoint)!=1 or segments[endpoint[0]]<0 or not np.isfinite(error[endpoint[0]]):
        return None,'invalid_pre_shot_endpoint'
    end=endpoint[0]
    # Walk backwards from the exact endpoint, stopping at the first discontinuity.
    start=end
    while (start>0 and ticks[start-1]>=first-PRE_SECONDS*tickrate
           and ticks[start]-ticks[start-1]==1 and segments[start-1]==segments[end]
           and np.isfinite(error[start-1])):
        start-=1
    indices=np.arange(start,end+1)
    if len(indices)-1<MIN_INTERVALS:
        return None,'insufficient_contiguous_pre_shot_intervals'
    # Rate at the first sample may depend on a sample outside this period.
    rates=indices[1:]
    if (not np.isfinite(error[indices]).all() or not np.isfinite(yaw[rates]).all()
        or not np.isfinite(bearing[rates]).all() or (abs(error[indices])>180).any()):
        raise ValueError('Invalid supporting tracking measurements')
    return [float(np.median(abs(error[indices]))),float(np.median(abs(yaw[rates]-bearing[rates])))],None


def case_features(windows,tickrate):
    values=[];excluded=Counter()
    for window in windows:
        result,reason=window_features(window,tickrate)
        if result is None:excluded[reason]+=1
        else:values.append(result)
    counts=dict(eligible_windows=len(values),excluded_windows=dict(excluded))
    if len(values)<MIN_WINDOWS:
        return None,counts
    return np.median(np.asarray(values),axis=0).tolist(),counts


def with_abstentions(values,labels,groups,case_ids,transform):
    eligible=np.array([value is not None for value in values])
    indices=np.flatnonzero(eligible)
    if len(set(np.asarray(groups)[eligible]))>=2:
        result=grouped_predictions(np.asarray([values[i] for i in indices]),np.asarray(labels)[eligible],
            np.asarray(groups)[eligible],[case_ids[i] for i in indices],transform)
    else:
        result=dict(predictions=[dict(case_id=case_ids[i],label='cheating' if labels[i] else 'legitimate',
            status='abstained',error='Insufficient independent eligible groups') for i in indices],folds=[])
    for i in np.flatnonzero(~eligible):
        result['predictions'].append(dict(case_id=case_ids[i],label='cheating' if labels[i] else 'legitimate',
            status='abstained',error=f'Fewer than {MIN_WINDOWS} eligible pre-shot windows'))
    order={case_id:i for i,case_id in enumerate(case_ids)}
    result['predictions'].sort(key=lambda row:order[row['case_id']])
    metrics=evaluation_metrics(result['predictions'])
    for key in ('detection_rate','false_positive_rate','precision','accuracy'):
        metrics[key].pop('exact_95_interval',None)
    metrics['diagnostic_only']=True
    result['metrics']=metrics
    return result


def compare(manifest_path,analysis_root,tracking_root,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    recipes={**RECIPES,**TRACKING_RECIPES}
    # Save fixed choices before feature loading or model fitting. Failures leave a receipt.
    write_json(output/'protocol.json',dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        role='exploratory_development',recipes=recipes,pre_seconds=PRE_SECONDS,
        minimum_contiguous_intervals=MIN_INTERVALS,minimum_eligible_windows=MIN_WINDOWS,
        candidate='Nearest horizontal opponent at exact tick before first shot; no damage-based selection',
        aggregation='Median per-window measurements, then median across eligible windows per player/match',
        hyperparameters=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0),threshold=.5,
        selection='Fixed recipes; no hyperparameter, feature-subset, eligibility or cutoff search',
        manifest_sha256=digest(manifest_path),
        source_code_sha256={name:digest(Path(__file__).with_name(name)) for name in
            ('tracking_models.py','development_models.py','baseline.py','target_tracking.py','target_geometry.py','combat.py','gameplay.py','core.py')},
        dependencies={name:importlib.metadata.version(name) for name in ('numpy','pandas','scikit-learn','scipy','demoparser2')},
        note='Previously inspected development pool; not independent held-out performance. Overlapping folds are not independent binomial trials.'))
    cases,matrices,participants,provenance=load_development(manifest_path,analysis_root)
    groups=participant_groups(participants)
    tracking_root=Path(tracking_root)
    summary=json.loads((tracking_root/'summary.json').read_text())
    if summary['manifest_sha256']!=digest(manifest_path) or len(summary['cases'])!=len(cases):
        raise ValueError('Tracking manifest mismatch')
    features=[];tracking_provenance=[]
    for index,case in enumerate(cases,1):
        path=tracking_root/f'case_{index:04d}.json';record=json.loads(path.read_text())
        if record['summary']!=summary['cases'][index-1] or record['summary']['case_id']!=case['case_id'] or record['summary']['label']!=case['label']:
            raise ValueError('Tracking case identity mismatch')
        directory=Path(analysis_root)/f'job_{index:04d}'
        for name in ('report.json','telemetry.csv','events.json'):
            if record['input_sha256'][name]!=digest(directory/name):
                raise ValueError('Tracking input checksum mismatch')
        if record['demo_sha256']!=case['demo_sha256']:
            raise ValueError('Tracking demo identity mismatch')
        report=json.loads((directory/'report.json').read_text())
        if len(record['windows'])!=len(report['engagements']):
            raise ValueError('Tracking window count mismatch')
        for window,published in zip(record['windows'],report['engagements']):
            if any(window[key]!=published[key] for key in ('engagement_id','weapon','shot_ticks','round_id')):
                raise ValueError('Tracking window identity mismatch')
        if record['assumed_tickrate_hz']!=report['assumed_tickrate_hz']:
            raise ValueError('Tracking timing mismatch')
        values,counts=case_features(record['windows'],record['assumed_tickrate_hz'])
        features.append(values)
        tracking_provenance.append(dict(case_id=case['case_id'],tracking_sha256=digest(path),
            features=values,**counts))
    matrices['pre_shot_tracking']=features
    matrices['speed_and_tracking']=[None if feature is None else [*speed,*feature]
        for speed,feature in zip(matrices['speed_acceleration'].tolist(),features)]
    group_cases={str(group):[case['case_id'] for case,g in zip(cases,groups) if g==group] for group in np.unique(groups)}
    write_json(output/'inputs.json',dict(cases=provenance,tracking=tracking_provenance,groups=group_cases,
        tracking_summary_sha256=digest(tracking_root/'summary.json')))
    labels=np.array([int(case['label']=='cheating') for case in cases]);ids=[case['case_id'] for case in cases]
    results={name:with_abstentions(list(matrices[name]),labels,groups,ids,recipe['transform']) for name,recipe in recipes.items()}
    result=dict(cases=len(cases),participant_groups=len(set(groups)),models=results,
        protocol_sha256=digest(output/'protocol.json'),inputs_sha256=digest(output/'inputs.json'),
        interpretation='Exploratory grouped development comparison on previously inspected cases. No deployment winner or fresh held-out accuracy claim.')
    write_json(output/'comparison.json',result)
    # Compatibility with the generic diagnostic renderer, without changing saved receipts.
    write_json(output/'display.json',dict(cases=[dict(case_id=case['case_id']) for case in cases],threshold=.5))
    lines=['# Pre-shot tracking development model comparison','',
        f'{len(cases)} cases in {len(set(groups))} participant groups. Entire components held out; scaler and classifier fitted on eligible training cases only.',
        'All cases are previously inspected development data. These are diagnostic counts, not new held-out detection estimates.',
        '', '| Recipe | True positives | False negatives | False positives | True negatives | Abstentions |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,model in results.items():
        metrics=model['metrics'];c=metrics['confusion']
        lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {metrics['abstentions']} |")
    lines+=['','Tracking uses only the fixed geometric pre-shot candidate, never damage recipients or hit-only windows.',
        'Features summarize the contiguous segment ending exactly one tick before the first shot, restricted to the preceding 200 ms. At least eight intervals per window and five eligible windows per case are required.',
        'Tracking-only uses two case medians: horizontal absolute error and absolute yaw-minus-bearing velocity. The combined recipe appends them to original speed/acceleration. Nonnegative features use log1p, followed by training-fold scaling.',
        'Fixed balanced logistic regression C=1, cutoff 0.5; no parameter, cutoff or eligibility search. Missing tracking coverage causes explicit abstention, not imputation.',
        'Protocol and inputs are saved before fitting; fold training IDs, scalers, coefficients, scores and coverage are saved afterward.',
        'Overlapping windows are not training rows; cases are equally weighted. Visibility, vertical/hitbox geometry, recoil and lag/subtick limitations remain.',
        'No full-pool deployment model is fitted. Existing frozen baseline and diagnostic results remain preserved. Fresh cases are needed for independent evaluation.','']
    (output/'report.md').write_text('\n'.join(lines));print('\n'.join(lines[:12]),flush=True)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path);parser.add_argument('analysis_root',type=Path);parser.add_argument('tracking_root',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
    compare(args.manifest,args.analysis_root,args.tracking_root,args.output)


if __name__=='__main__':main()

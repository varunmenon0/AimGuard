"""Target-independent two-axis pre-shot trajectory shape development experiment."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.baseline import digest, report_features, write_json
from aimguard.core import extract_features
from aimguard.tracking_models import with_abstentions

PRE_SECONDS = .5
MIN_INTERVALS = 16
MIN_WINDOWS = 5
FEATURES = ['path_efficiency', 'mean_turn', 'speed_cv', 'stop_fraction']


def window_shape(telemetry, window, tickrate):
    if not np.isfinite(tickrate) or tickrate <= 0: raise ValueError('Invalid tickrate')
    if telemetry.index.has_duplicates: raise ValueError('Duplicate telemetry tick')
    first = window['shot_ticks'][0]; endpoint = first-1
    lower = max(window['start_tick'], first-PRE_SECONDS*tickrate)
    def valid(tick):
        if tick not in telemetry.index: return False
        row=telemetry.loc[tick]
        return (row['active'] == True and row['segment_id']==window['segment_id']
                and row['life_state']==0 and row['health']>0 and row['team_num'] in (2,3)
                and np.isfinite([row['yaw'],row['pitch']]).all() and abs(row['pitch'])<=90)
    if endpoint < lower or not valid(endpoint): return None, 'invalid_exact_pre_shot_endpoint'
    start=endpoint
    while start-1 >= lower and valid(start-1): start-=1
    if endpoint-start < MIN_INTERVALS: return None, 'insufficient_contiguous_pre_shot_intervals'
    part=telemetry.loc[list(range(start,endpoint+1))]
    features=extract_features(part.index.to_numpy(dtype=float)/tickrate,part.yaw.to_numpy(),part.pitch.to_numpy())
    return dict(start_tick=start,end_tick=endpoint,valid_intervals=endpoint-start,
                features=[features[name] for name in FEATURES]), None


def case_shape(telemetry, windows, tickrate):
    values=[]; excluded=Counter(); details=[]
    for window in windows:
        result,reason=window_shape(telemetry,window,tickrate)
        details.append(dict(engagement_id=window['engagement_id'],measurement=result,excluded_reason=reason))
        if result is None: excluded[reason]+=1
        else: values.append(result['features'])
    counts=dict(eligible_windows=len(values),excluded_windows=dict(excluded),windows=details)
    return (np.median(values,axis=0).tolist() if len(values)>=MIN_WINDOWS else None),counts


def compare(pool,baseline_directory,output):
    pool,baseline_directory,output=map(Path,(pool,baseline_directory,output))
    manifest=json.loads((pool/'manifest.json').read_text());receipt=json.loads((pool/'pool-receipt.json').read_text())
    old_protocol=json.loads((baseline_directory/'protocol.json').read_text());old_inputs=json.loads((baseline_directory/'inputs.json').read_text())
    baseline=json.loads((baseline_directory/'comparison.json').read_text())
    expected=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0)
    if (manifest.get('role')!='development' or manifest.get('features_inspected') is not True
        or receipt['manifest_sha256']!=digest(pool/'manifest.json') or old_protocol['manifest_sha256']!=digest(pool/'manifest.json')
        or baseline['protocol_sha256']!=digest(baseline_directory/'protocol.json') or baseline['inputs_sha256']!=digest(baseline_directory/'inputs.json')
        or old_inputs['groups']!=receipt['groups'] or old_protocol['hyperparameters']!=expected or old_protocol['threshold']!=.5):
        raise ValueError('Inspected pool/baseline protocol receipt mismatch')
    cases=manifest['cases'];ids=[c['case_id'] for c in cases]
    membership=[case_id for members in receipt['groups'].values() for case_id in members]
    if len(set(ids))!=len(ids) or len(membership)!=len(set(membership)) or set(membership)!=set(ids):
        raise ValueError('Duplicate/missing participant group identity')
    if any(c['label'] not in ('cheating','legitimate') for c in cases): raise ValueError('Unknown case label')
    if any(len(rows)!=len(cases) for rows in (receipt['cases'],old_inputs['cases'],old_inputs['tracking'])):
        raise ValueError('Source counts mismatch')
    predictions=baseline['models']['speed_and_tracking']['predictions']
    if len(predictions)!=len(cases) or {p['case_id']:p['label'] for p in predictions}!={c['case_id']:c['label'] for c in cases}:
        raise ValueError('Baseline labels/coverage mismatch')
    output.mkdir(parents=True,exist_ok=False)
    recipes=dict(pre_shot_shape=dict(features=FEATURES,transform='log1p'),
        speed_tracking_and_shape=dict(features=[*old_protocol['recipes']['speed_and_tracking']['features'],*FEATURES],transform='log1p'))
    write_json(output/'protocol.json',dict(role='exploratory_development',recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        recipes=recipes,pre_seconds=PRE_SECONDS,min_intervals=MIN_INTERVALS,min_windows=MIN_WINDOWS,
        hyperparameters=expected,threshold=.5,manifest_sha256=digest(pool/'manifest.json'),baseline_sha256=digest(baseline_directory/'comparison.json'),
        code_sha256={name:digest(Path(__file__).with_name(name)) for name in ('pre_shot_shape.py','core.py','tracking_models.py','development_models.py','baseline.py')},
        dependencies={name:importlib.metadata.version(name) for name in ('numpy','pandas','scikit-learn')},
        cases=[dict(case_id=case_id) for case_id in ids],note='Fixed two-axis pre-shot shape recipe; no opponent, damage or post-shot selection; no cutoff/parameter/feature search. Stationary samples retained, not treated as a cheat signature.'))
    groups_by_case={case_id:int(group) for group,members in receipt['groups'].items() for case_id in members}
    groups=[groups_by_case[case_id] for case_id in ids];labels=[int(c['label']=='cheating') for c in cases]
    vectors=[];combined=[];inputs=[]
    for index,case in enumerate(cases,1):
        directory=pool/'analysis'/f'job_{index:04d}';path=pool/'tracking'/f'case_{index:04d}.json'
        report=json.loads((directory/'report.json').read_text());track=json.loads(path.read_text())
        sources=[receipt['cases'][index-1],old_inputs['cases'][index-1],old_inputs['tracking'][index-1]]
        if (any(s['case_id']!=case['case_id'] for s in sources) or digest(directory/'report.json')!=sources[0]['report_sha256']
            or digest(directory/'report.json')!=sources[1]['report_sha256'] or digest(path)!=sources[0]['tracking_sha256']
            or digest(path)!=sources[2]['tracking_sha256'] or report['steamid']!=case['steamid']
            or report['source_sha256']!=case['demo_sha256'] or track['demo_sha256']!=case['demo_sha256']
            or track['summary']['case_id']!=case['case_id'] or track['summary']['label']!=case['label']):
            raise ValueError('Source identity/checksum mismatch')
        for name in ('report.json','telemetry.csv','events.json'):
            if digest(directory/name)!=track['input_sha256'][name]: raise ValueError('Tracking source checksum mismatch')
        telemetry=pd.read_csv(directory/'telemetry.csv',dtype={'steamid':str})
        if (not telemetry.steamid.eq(case['steamid']).all() or telemetry.tick.duplicated().any()
            or not np.isfinite(telemetry.tick).all() or (telemetry.tick%1!=0).any()):
            raise ValueError('Telemetry identity/tick mismatch')
        telemetry=telemetry.set_index('tick')
        vector,coverage=case_shape(telemetry,report['engagements'],report['assumed_tickrate_hz'])
        speed,_=report_features(report);tracking=sources[2]['features']
        vectors.append(vector);combined.append([*speed,*tracking,*vector] if vector is not None and tracking is not None else None)
        inputs.append(dict(case_id=case['case_id'],label=case['label'],features=vector,telemetry_sha256=digest(directory/'telemetry.csv'),**coverage))
    write_json(output/'inputs.json',dict(cases=inputs,groups=receipt['groups']))
    models=dict(speed_and_tracking=baseline['models']['speed_and_tracking'])
    for name,values in [('pre_shot_shape',vectors),('speed_tracking_and_shape',combined)]:
        model=with_abstentions(values,labels,groups,ids,'log1p')
        for row in model['predictions']:
            if row['status']=='abstained' and row.get('error','').startswith('Fewer than'):
                row['error']=f'Need {MIN_WINDOWS} eligible two-axis pre-shot windows and any required tracking coverage'
        models[name]=model
    result=dict(cases=len(cases),participant_groups=len(set(groups)),models=models,protocol_sha256=digest(output/'protocol.json'),
        inputs_sha256=digest(output/'inputs.json'),interpretation='Inspected development comparison only; no fresh accuracy claim or model promotion.')
    write_json(output/'comparison.json',result)
    lines=['# Two-axis pre-shot shape development experiment','','Whole participant groups held out; training-only scaling/fitting; fixed C=1 and cutoff 0.5. Previously inspected cases only.','',
        '| Recipe | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,model in models.items():
        c=model['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {model['metrics']['abstentions']} |")
    lines+=['','Features are case medians of path efficiency, mean two-axis direction change, speed variation and stop fraction over contiguous 500 ms pre-shot segments.',
        'No post-shot or opponent/damage selection. Stationary/quantized aim is not declared cheating. Missing coverage abstains.',
        'No full-pool fit, parameter/cutoff search or frozen model replacement. Historical evaluation is unchanged.','']
    (output/'report.md').write_text('\n'.join(lines));print('\n'.join(lines),flush=True);return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('pool',type=Path);parser.add_argument('baseline_directory',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv);compare(args.pool,args.baseline_directory,args.output)


if __name__=='__main__':main()

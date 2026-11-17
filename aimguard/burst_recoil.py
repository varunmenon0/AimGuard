"""Fixed same-weapon burst co-variation experiment; no physical recoil correction."""
import argparse
from collections import Counter
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.baseline import digest,write_json
from aimguard.core import angle_delta
from aimguard.measurement_audit import clean
from aimguard.recoil_event_audit import FIELDS,weapon_id
from aimguard.tracking_models import with_abstentions


def burst_groups(windows,tickrate):
    if not np.isfinite(tickrate) or tickrate<=0:raise ValueError('Invalid tickrate')
    groups=[]
    for window in windows:
        shots=np.asarray(window['shot_ticks'],dtype=int)
        if (np.diff(shots)<=0).any():raise ValueError('Shot ticks must increase')
        for part in np.split(shots,np.flatnonzero(np.diff(shots)/tickrate>.2)+1):
            if len(part)>=3:groups.append(dict(shot_ticks=part.tolist(),weapon=window['weapon'],segment_id=window['segment_id']))
    return groups


def burst_features(frame,burst):
    if frame.tick.duplicated().any():raise ValueError('Duplicate burst samples')
    first,last=burst['shot_ticks'][0],burst['shot_ticks'][-1]
    part=frame.set_index('tick').reindex(range(first-1,last+3))
    if part[FIELDS].isna().any().any():return None,'missing_exact_support'
    if not part.active_weapon_name.map(weapon_id).eq(burst['weapon']).all():return None,'weapon_changed_or_mismatched'
    try:punch=np.asarray(part.aim_punch_angle.tolist(),dtype=float);view=part[['pitch','yaw']].to_numpy(dtype=float)
    except (ValueError,TypeError):return None,'invalid_numeric_support'
    if punch.shape!=(len(part),3) or not np.isfinite(punch).all() or not np.isfinite(view).all():return None,'invalid_numeric_support'
    a=np.diff(view,axis=0);a[:,1]=angle_delta(a[:,1]);b=np.diff(punch[:,:2],axis=0)
    if len(a)<8:return None,'insufficient_intervals'
    energy_view=float((a*a).sum());energy_punch=float((b*b).sum())
    if energy_view<=1e-8 or energy_punch<=1e-8:return None,'insufficient_view_or_punch_variation'
    gain=float(-(a*b).sum()/energy_punch)
    residual=float(((a+gain*b)**2).sum()/energy_view)
    cosine=float((a*b).sum()/np.sqrt(energy_view*energy_punch))
    return dict(features=[gain,residual,cosine],intervals=len(a),view_energy=energy_view,punch_energy=energy_punch),None


def aggregate(results):
    valid=[r['features'] for r in results if r is not None]
    return np.median(valid,axis=0).tolist() if len(valid)>=5 else None


def run(pool,output):
    from demoparser2 import DemoParser
    pool,output=map(Path,(pool,output));base=json.loads((pool/'comparison.json').read_text());source=json.loads((pool/'inputs.json').read_text())
    if base['inputs_sha256']!=digest(pool/'inputs.json') or base['protocol_sha256']!=digest(pool/'protocol.json'):raise ValueError('Pool receipts differ')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='inspected_burst_recoil_development',minimum_shots=3,maximum_gap_seconds=.2,
        support='Exact consecutive ticks from first shot-1 to last shot+2, same live segment and weapon',minimum_intervals=8,minimum_case_bursts=5,
        new_features=['observed_opposing_projection_gain','relative_projection_residual','global_component_cosine'],
        aggregation='Componentwise median across valid same-weapon bursts; no inferred firing mode or cross-weapon calibration',
        transform='log1p original four features; identity signed burst features; training-only scaling',
        threshold=.5,hyperparameters=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0),
        source_sha256={n:digest(pool/n) for n in ('inputs.json','comparison.json','protocol.json')},
        code_sha256={n:digest(Path(__file__).with_name(n)) for n in ('burst_recoil.py','recoil_event_audit.py','tracking_models.py','development_models.py')},
        dependencies={n:importlib.metadata.version(n) for n in ('demoparser2','numpy','pandas','scikit-learn')},
        note='One fixed recipe, no parameter/threshold search. Projection is observed component co-variation, not mouse input, recoil correction, actual compensation or cheat activation. Missing case coverage abstains. No holdout use or model promotion.'))
    rows=[];vectors=[]
    for i,row in enumerate(source['cases'],1):
        directory=pool/'analysis'/f'job_{i:04d}';report=json.loads((directory/'report.json').read_text());trackpath=pool/'tracking'/f'case_{i:04d}.json';track=json.loads(trackpath.read_text())
        if digest(directory/'report.json')!=row['report_sha256'] or digest(trackpath)!=row['tracking_sha256']:raise ValueError('Case receipts differ')
        for name,h in track['input_sha256'].items():
            if digest(directory/name)!=h:raise ValueError('Canonical input changed')
        demo=Path(report['source'])
        if digest(demo)!=report['source_sha256']:raise ValueError('Demo changed')
        groups=burst_groups(report['engagements'],report['assumed_tickrate_hz']);ticks=sorted({t for g in groups for t in range(g['shot_ticks'][0]-1,g['shot_ticks'][-1]+3)})
        frame=pd.read_csv(directory/'telemetry.csv').set_index('tick')
        probe=DemoParser(str(demo)).parse_ticks(FIELDS,ticks=ticks,players=[int(report['steamid'])]) if ticks else pd.DataFrame(columns=FIELDS+['tick'])
        if probe.tick.duplicated().any():raise ValueError('Duplicate shooter ticks')
        expected=frame.reindex(probe.tick)
        for key in ('yaw','pitch'):
            if not np.array_equal(probe[key].to_numpy(dtype=np.float32),expected[key].to_numpy(dtype=np.float32),equal_nan=True):raise ValueError('Angles do not reproduce')
        missing=[f for f in FIELDS if f not in probe];results=[];records=[];counts=Counter()
        for g in groups:
            support=frame.reindex(range(g['shot_ticks'][0]-1,g['shot_ticks'][-1]+3));result=None
            if missing:reason='missing_property'
            elif not (support.active.eq(True)&support.phase_status.eq('live')&support.segment_id.eq(g['segment_id'])).all():reason='outside_same_live_segment'
            else:result,reason=burst_features(probe.loc[probe.tick.between(g['shot_ticks'][0]-1,g['shot_ticks'][-1]+2)],g)
            results.append(result);counts[reason or 'eligible']+=1;records.append(dict(g,measurement=result,unavailable_reason=reason))
        features=aggregate(results);vector=[*np.log1p(row['features']),*features] if features is not None and row['features'] is not None else None
        record=dict(case_id=row['case_id'],label=row['label'],features=vector,burst_features=features,coverage=dict(counts),weapons=dict(Counter(g['weapon'] for g,r in zip(groups,results) if r is not None)),bursts=records,raw_probe=clean(probe.to_dict('records')))
        write_json(output/f'case_{i:04d}.json',record);rows.append({k:v for k,v in record.items() if k not in ('bursts','raw_probe')});vectors.append(vector)
        print(f"{i}/{len(source['cases'])} {row['case_id']}: {counts['eligible']}/{len(groups)} eligible bursts",flush=True)
    write_json(output/'inputs.json',dict(cases=rows,groups=source['groups']))
    ids=[r['case_id'] for r in rows];g={cid:k for k,cs in source['groups'].items() for cid in cs};model=with_abstentions(vectors,[int(r['label']=='cheating') for r in rows],[g[cid] for cid in ids],ids,'identity')
    for r in model['predictions']:
        if r['status']=='abstained':r['error']='Insufficient eligible burst evidence or independent training groups'
    matched=with_abstentions([v[:4] if v is not None else None for v in vectors],[int(r['label']=='cheating') for r in rows],[g[cid] for cid in ids],ids,'identity')
    for r in matched['predictions']:
        if r['status']=='abstained':r['error']='Matched burst-coverage baseline: unavailable burst evidence'
    result=dict(models=dict(original=base['models']['v06_speed_and_tracking'],matched_coverage_baseline=matched,with_burst=model),protocol_sha256=digest(output/'protocol.json'),inputs_sha256=digest(output/'inputs.json'),promotion_status='not_frozen_or_deployed');write_json(output/'comparison.json',result)
    lines=['# Same-weapon burst dynamics development experiment','','| Recipe | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,m in result['models'].items():
        c=m['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {m['metrics']['abstentions']} |")
    lines+=['','Different coverage is not improved specificity. Abstentions are not legitimate negatives. Development only; no causal recoil or activation claim.'];(output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines));return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pool',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);run(a.pool,a.output)


if __name__=='__main__':main()

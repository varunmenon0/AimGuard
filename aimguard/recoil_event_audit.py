"""Validate recorded recoil/counter timing around published live shot events."""
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

WEAPON_NAMES={'AK-47':'ak47','Desert Eagle':'deagle','Glock-18':'glock','USP-S':'usp_silencer','M4A1-S':'m4a1_silencer','M4A4':'m4a1','P2000':'hkp2000','Galil AR':'galilar','SG 553':'sg556','SSG 08':'ssg08','Dual Berettas':'elite','R8 Revolver':'revolver','Five-SeveN':'fiveseven','CZ75-Auto':'cz75a','MP5-SD':'mp5sd','PP-Bizon':'bizon','Tec-9':'tec9','MAC-10':'mac10','MAG-7':'mag7','Sawed-Off':'sawedoff','SCAR-20':'scar20','UMP-45':'ump45'}


def weapon_id(value):
    return WEAPON_NAMES.get(str(value),str(value).lower().removeprefix('weapon_'))


FIELDS=['yaw','pitch','aim_punch_angle','shots_fired','active_weapon_name']


def shot_dynamics(frame,shot,weapon):
    """Exact five-tick support only; observed components, not bullet-ray correction."""
    if frame.tick.duplicated().any():raise ValueError('Duplicate recoil probe tick')
    part=frame.set_index('tick').reindex(range(shot-2,shot+3))
    if part[FIELDS].isna().any().any():return dict(status='unavailable',reason='missing_exact_samples_or_fields')
    names=part.active_weapon_name.map(weapon_id)
    if not names.eq(weapon).all():return dict(status='unavailable',reason='weapon_changed_or_mismatched')
    punch=np.asarray(part.aim_punch_angle.tolist(),dtype=float);counter=part.shots_fired.to_numpy(dtype=float)
    view=part[['pitch','yaw']].to_numpy(dtype=float)
    if punch.shape!=(5,3) or not np.isfinite(punch).all() or not np.isfinite(view).all() or not np.isfinite(counter).all() or (counter<0).any() or (counter%1).any():return dict(status='unavailable',reason='invalid_numeric_fields')
    view_delta=np.diff(view,axis=0);view_delta[:,1]=angle_delta(view_delta[:,1]);punch_delta=np.diff(punch[:,:2],axis=0)
    steps=np.diff(counter);cosines=[]
    for a,b in zip(view_delta,punch_delta):
        scale=float(np.linalg.norm(a)*np.linalg.norm(b))
        cosines.append(float(np.clip(a@b/scale,-1,1)) if scale>1e-9 else None)
    return dict(status='available',interval_end_offsets=[-1,0,1,2],counter_deltas=steps.tolist(),
        positive_counter_offsets=[offset for offset,d in zip([-1,0,1,2],steps) if d>0],counter_reset=bool((steps<0).any()),
        punch_step_magnitudes=np.linalg.norm(punch_delta,axis=1).tolist(),view_step_magnitudes=np.linalg.norm(view_delta,axis=1).tolist(),
        recorded_component_cosines=cosines,
        note='Pitch/yaw view increments compared with punch components0/1 as recorded; component relationship only. No validated camera/bullet correction, compensation or cheat assertion.')


def run(pool,output):
    from demoparser2 import DemoParser
    pool,output=map(Path,(pool,output));base=json.loads((pool/'comparison.json').read_text());source=json.loads((pool/'inputs.json').read_text())
    if base['inputs_sha256']!=digest(pool/'inputs.json') or base['protocol_sha256']!=digest(pool/'protocol.json'):raise ValueError('Pool source receipt differs')
    prediction={r['case_id']:r for r in base['models']['v06_speed_and_tracking']['predictions']}
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='descriptive_recoil_event_audit',source_sha256={n:digest(pool/n) for n in ('inputs.json','comparison.json','protocol.json')},
        code_sha256=digest(__file__),dependencies={n:importlib.metadata.version(n) for n in ('demoparser2','numpy','pandas')},
        properties=FIELDS,offsets=[-2,-1,0,1,2],selection='Every published live shot, exact selected player; require all five samples in the published segment and unchanged matching weapon.',
        note='No model fitting, threshold search, activation labels, recoil correction or holdout access. Consecutive shots have overlapping support, not independent samples.'))
    rows=[]
    for index,row in enumerate(source['cases'],1):
        directory=pool/'analysis'/f'job_{index:04d}';report=json.loads((directory/'report.json').read_text());trackpath=pool/'tracking'/f'case_{index:04d}.json';tracking=json.loads(trackpath.read_text())
        if digest(directory/'report.json')!=row['report_sha256'] or digest(trackpath)!=row['tracking_sha256']:raise ValueError('Case receipts differ')
        for name,h in tracking['input_sha256'].items():
            if digest(directory/name)!=h:raise ValueError('Canonical source changed')
        frame=pd.read_csv(directory/'telemetry.csv');demo=Path(report['source'])
        if digest(demo)!=report['source_sha256']:raise ValueError('Demo hash differs')
        shots=[(int(s),w['weapon'],w['segment_id']) for w in report['engagements'] for s in w['shot_ticks']]
        requested=sorted({tick for s,_,_ in shots for tick in range(s-2,s+3)})
        probe=DemoParser(str(demo)).parse_ticks(FIELDS,ticks=requested,players=[int(report['steamid'])])
        if probe.tick.duplicated().any():raise ValueError('Duplicate shooter rows')
        expected=frame.set_index('tick').reindex(probe.tick)
        for key in ('yaw','pitch'):
            if not np.array_equal(probe[key].to_numpy(dtype=np.float32),expected[key].to_numpy(dtype=np.float32),equal_nan=True):raise ValueError('Probe angles differ from telemetry')
        missing=[key for key in FIELDS if key not in probe]
        events=[];counts=Counter();offset_counts=Counter();cosines=[]
        indexed=frame.set_index('tick')
        for s,weapon,segment in shots:
            support=indexed.reindex(range(s-2,s+3))
            if missing:d=dict(status='unavailable',reason='missing_property')
            elif not (support.active.eq(True)&support.segment_id.eq(segment)&support.phase_status.eq('live')).all():d=dict(status='unavailable',reason='outside_same_live_segment')
            else:d=shot_dynamics(probe.loc[probe.tick.between(s-2,s+2)],s,weapon)
            events.append(dict(tick=s,weapon=weapon,segment_id=segment,**d));counts[d['status']]+=1
            if d['status']=='available':
                counts['counter_rise_near_event']+=bool(d['positive_counter_offsets']);counts['counter_rise_at_event']+=0 in d['positive_counter_offsets'];counts['counter_reset']+=d['counter_reset']
                offset_counts.update(d['positive_counter_offsets']);cosines.extend(c for c in d['recorded_component_cosines'] if c is not None)
            else:counts[d['reason']]+=1
        record=dict(case_id=row['case_id'],label=row['label'],default_flagged=prediction[row['case_id']]['flagged'],counts=dict(counts),counter_rise_offsets={str(k):v for k,v in sorted(offset_counts.items())},
            median_recorded_component_cosine=float(np.median(cosines)) if cosines else None,missing_properties=missing,
            raw_probe=clean(probe.to_dict('records')),events=events,report_sha256=row['report_sha256'],demo_sha256=report['source_sha256'])
        rows.append(record);write_json(output/f'case_{index:04d}.json',record);print(f"{index}/{len(source['cases'])} {row['case_id']}: {counts['available']}/{len(shots)} exact stable-weapon shots",flush=True)
    write_json(output/'summary.json',dict(cases=[{k:v for k,v in r.items() if k not in ('raw_probe','events')} for r in rows],protocol_sha256=digest(output/'protocol.json'),models_changed=False,
        note='Observed counter/punch timing and component correlation only. No recoil correction or classifier validity established.'))
    lines=['# Recoil and shot-event dynamics audit','','| Case | Label | Available shots | Counter rise nearby | Counter rise at event | Median component cosine |','| --- | --- | ---: | ---: | ---: | ---: |']
    for r in rows:
        c=r['counts'];lines.append(f"| {r['case_id']} | {r['label']} | {c.get('available',0)} | {c.get('counter_rise_near_event',0)} | {c.get('counter_rise_at_event',0)} | {r['median_recorded_component_cosine']} |")
    (output/'report.md').write_text('\n'.join(lines)+'\n');return rows


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pool',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);run(a.pool,a.output)


if __name__=='__main__':main()

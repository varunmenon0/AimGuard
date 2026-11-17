"""Descriptive shot-timing support audit; no recoil correction or classifier changes."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.baseline import digest,write_json
from aimguard.combat import interval_motion
from aimguard.measurement_audit import clean


def window_motion(frame,window,tickrate):
    ticks=frame.tick.to_numpy(dtype=float)
    if len(ticks)<3 or not np.isfinite(frame[['tick','yaw','pitch']]).all().all() or (np.diff(ticks)<=0).any():raise ValueError('Invalid motion support')
    motion=interval_motion(frame,window['shot_ticks'],tickrate);speed=motion['speed'];dt=motion['dt'];accel=np.diff(speed)/((dt[:-1]+dt[1:])/2)
    near=abs(motion['shot_offset_seconds'])<=.1;acc=near[:-1]&near[1:];first=window['shot_ticks'][0]
    # Every supporting sample, not just the interval endpoint, must precede the shot.
    points=(ticks>=first-.1*tickrate)&(ticks<first);pre=points[:-1]&points[1:];pre_acc=pre[:-1]&pre[1:]
    legacy=window['movement_context']['near_shot']
    for name,actual in [('p95_speed',np.percentile(speed[near],95) if near.any() else None),('mean_accel',float(abs(accel[acc]).mean()) if acc.any() else None)]:
        expected=legacy[name]
        if (expected is None)!=(actual is None) or actual is not None and not np.isclose(actual,expected,rtol=1e-6,atol=1e-6):raise ValueError('Original movement feature does not reproduce')
    return dict(engagement_id=window['engagement_id'],first_shot_tick=first,shot_count=len(window['shot_ticks']),
        near_speed_intervals=int(near.sum()),near_speed_at_or_after_first=int((near&(ticks[1:]>=first)).sum()),
        near_acceleration_samples=int(acc.sum()),near_acceleration_at_or_after_first=int((acc&(ticks[2:]>=first)).sum()),
        original_features=[legacy['p95_speed'],legacy['mean_accel']],
        pre_first_features=[float(np.percentile(speed[pre],95)) if pre.any() else None,float(abs(accel[pre_acc]).mean()) if pre_acc.any() else None],
        pre_speed_intervals=int(pre.sum()),pre_acceleration_samples=int(pre_acc.sum()))


def run(pool,output):
    from demoparser2 import DemoParser
    pool,output=map(Path,(pool,output));result=json.loads((pool/'comparison.json').read_text());source=json.loads((pool/'inputs.json').read_text())
    if result['inputs_sha256']!=digest(pool/'inputs.json') or result['protocol_sha256']!=digest(pool/'protocol.json'):raise ValueError('Pool source receipt differs')
    predictions={r['case_id']:r for r in result['models']['v06_speed_and_tracking']['predictions']}
    false_flags=[r['case_id'] for r in predictions.values() if r['status']=='scored' and r['flagged'] and r['label']=='legitimate']
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='descriptive_shot_motion_audit',source_comparison_sha256=digest(pool/'comparison.json'),
        source_inputs_sha256=digest(pool/'inputs.json'),code_sha256=digest(__file__),
        selection='Timing support for all development windows. Recoil-field probe: first three chronological windows in each default false flag, ±16 ticks around first shot, selected player only.',
        pre_definition='All support ticks in [first shot - 100ms, first shot); same recorded window/segment. No interpolation or guessed recoil correction.',
        note='Post-shot presence does not establish recoil causation. Pre-first-shot does not guarantee recoil-free input. No classifier fit, label change or reserved-control access.'))
    rows=[]
    for index,row in enumerate(source['cases'],1):
        directory=pool/'analysis'/f'job_{index:04d}';report=json.loads((directory/'report.json').read_text());track=json.loads((pool/'tracking'/f'case_{index:04d}.json').read_text())
        if digest(directory/'report.json')!=row['report_sha256'] or digest(pool/'tracking'/f'case_{index:04d}.json')!=row['tracking_sha256']:raise ValueError('Case report/tracking receipt differs')
        for name,h in track['input_sha256'].items():
            if digest(directory/name)!=h:raise ValueError('Canonical source changed')
        frame=pd.read_csv(directory/'telemetry.csv');windows=[]
        for w in report['engagements']:
            part=frame.loc[frame.segment_id.eq(w['segment_id'])&frame.tick.between(w['start_tick'],w['end_tick'])]
            if len(part)!=w['samples'] or not part.active.all() or not part.phase_status.eq('live').all():raise ValueError('Window support differs')
            windows.append(window_motion(part,w,report['assumed_tickrate_hz']))
        counts=Counter()
        for w in windows:
            for k in ('near_speed_intervals','near_speed_at_or_after_first','near_acceleration_samples','near_acceleration_at_or_after_first'):counts[k]+=w[k]
        medians=[float(np.median([w['pre_first_features'][i] for w in windows if w['pre_first_features'][i] is not None])) if any(w['pre_first_features'][i] is not None for w in windows) else None for i in range(2)]
        record=dict(case_id=row['case_id'],label=row['label'],default_false_flag=row['case_id'] in false_flags,counts=dict(counts),original_case_features=row['features'][:2],pre_first_case_features=medians,windows=windows)
        if row['case_id'] in false_flags:
            requested=sorted({int(t) for w in report['engagements'][:3] for t in frame.loc[frame.tick.between(w['shot_ticks'][0]-16,w['shot_ticks'][0]+16),'tick']})
            demo=Path(report['source'])
            if digest(demo)!=report['source_sha256']:raise ValueError('Replay hash differs')
            probe=DemoParser(str(demo)).parse_ticks(['yaw','pitch','aim_punch_angle','shots_fired'],ticks=requested,players=[int(report['steamid'])])
            if probe.tick.duplicated().any():raise ValueError('Duplicate shooter probe ticks')
            expected=frame.set_index('tick').reindex(probe.tick)
            for key in ('yaw','pitch'):
                if not np.array_equal(probe[key].to_numpy(dtype=np.float32),expected[key].to_numpy(dtype=np.float32)):raise ValueError('Probe does not reproduce recorded angles')
            record['recoil_probe']=dict(requested_ticks=requested,returned_ticks=probe.tick.astype(int).tolist(),
                missing_properties=[k for k in ('aim_punch_angle','shots_fired') if k not in probe],rows=clean(probe.to_dict('records')),
                note='Observed field values only; no subtraction or causal attribution to view-angle motion.')
        rows.append(record);print(row['case_id'],flush=True)
    write_json(output/'audit.json',dict(cases=rows,protocol_sha256=digest(output/'protocol.json'),models_changed=False))
    lines=['# Shot-motion measurement audit','','No model changes. Near-shot motion can include shot and post-shot samples; observed recoil fields do not certify recoil-corrected view angles.','',
        '| False flag | Speed intervals at/after first shot | Acceleration at/after first shot | Original speed / accel | Pre-first speed / accel |','| --- | --- | --- | --- | --- |']
    for r in rows:
        if not r['default_false_flag']:continue
        c=r['counts'];lines.append(f"| {r['case_id']} | {c['near_speed_at_or_after_first']}/{c['near_speed_intervals']} | {c['near_acceleration_at_or_after_first']}/{c['near_acceleration_samples']} | {r['original_case_features']} | {r['pre_first_case_features']} |")
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True);return rows


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pool',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);run(a.pool,a.output)


if __name__=='__main__':main()

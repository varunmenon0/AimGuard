"""Diagnostic horizontal opponent alignment; no visibility or target inference."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.baseline import digest, write_json
from aimguard.core import angle_delta

FIELDS = ['X','Y','yaw','health','life_state','team_num']


def bearing_error(shooter_xy, yaw, opponent_xy):
    """Signed shortest horizontal bearing minus recorded yaw, in degrees."""
    a,b=np.asarray(shooter_xy,dtype=float),np.asarray(opponent_xy,dtype=float)
    if a.shape!=(2,) or b.shape!=(2,) or not np.isfinite(np.r_[a,b,yaw]).all():
        raise ValueError('Finite XY positions and yaw required')
    delta=b-a
    if np.linalg.norm(delta)<=1e-9:
        return None
    return float(angle_delta(np.degrees(np.arctan2(delta[1],delta[0]))-yaw))


def alive(row):
    return row['life_state']==0 and row['health']>0 and row['team_num'] in (2,3)


def shot_alignment(frame, steamid, shot_tick, pre_tick):
    """Compare the same opponent at two exact ticks, never interpolate or switch."""
    required=set(FIELDS+['tick','steamid'])
    if not required.issubset(frame.columns):
        raise ValueError('Missing geometry columns')
    if pre_tick>=shot_tick:
        raise ValueError('Pre-shot tick must precede shot tick')
    frame=frame.copy()
    frame['steamid']=frame['steamid'].astype(str)
    for key in FIELDS+['tick']:
        frame[key]=pd.to_numeric(frame[key],errors='coerce')
    if frame.duplicated(['tick','steamid']).any():
        raise ValueError('Ambiguous duplicate player/tick geometry')
    frame=frame.set_index(['tick','steamid'])
    result=dict(shot_tick=int(shot_tick),pre_tick=int(pre_tick),status='unavailable',candidates=[])
    try:
        shooter=frame.loc[(shot_tick,str(steamid))]
    except KeyError:
        result['reason']='missing_shooter'; return result
    if not alive(shooter) or not np.isfinite(shooter[FIELDS].to_numpy(dtype=float)).all():
        result['reason']='invalid_shooter'; return result
    current=frame.xs(shot_tick)
    for opponent_id,opponent in current.iterrows():
        if opponent_id==str(steamid) or not alive(opponent) or opponent['team_num']==shooter['team_num']:
            continue
        if not np.isfinite(opponent[FIELDS].to_numpy(dtype=float)).all():
            continue
        error=bearing_error(shooter[['X','Y']],shooter['yaw'],opponent[['X','Y']])
        if error is None:
            continue
        candidate=dict(opponent_id=opponent_id,signed_yaw_error_degrees=error,
                       absolute_yaw_error_degrees=abs(error),pre_absolute_yaw_error_degrees=None,
                       error_reduction_degrees=None,pre_status='missing_pair')
        try:
            before=frame.loc[(pre_tick,str(steamid))]
            target=frame.loc[(pre_tick,opponent_id)]
        except KeyError:
            result['candidates'].append(candidate);continue
        if (alive(before) and alive(target) and before['team_num']==shooter['team_num']
            and target['team_num']==opponent['team_num']
            and np.isfinite(before[FIELDS].to_numpy(dtype=float)).all()
            and np.isfinite(target[FIELDS].to_numpy(dtype=float)).all()):
            pre_error=bearing_error(before[['X','Y']],before['yaw'],target[['X','Y']])
            if pre_error is not None:
                candidate.update(pre_absolute_yaw_error_degrees=abs(pre_error),
                                 error_reduction_degrees=abs(pre_error)-abs(error),pre_status='available')
        else:
            candidate['pre_status']='invalid_pair'
        result['candidates'].append(candidate)
    if result['candidates']:
        result.update(status='available',reason=None)
        # This is a geometric candidate, not an assertion of the intended target.
        nearest=min(result['candidates'],key=lambda c:(c['absolute_yaw_error_degrees'],c['opponent_id']))
        result['nearest_horizontal_candidate']=nearest.copy()
    else:
        result['reason']='no_valid_alive_opponent'
    return result


def analyze(manifest_path,analysis_root,output):
    from demoparser2 import DemoParser
    import importlib.metadata
    manifest=json.loads(Path(manifest_path).read_text())
    if manifest.get('role')!='development':
        raise ValueError('Geometry diagnostics require development data')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    summaries=[]
    for index,case in enumerate(manifest['cases'],1):
        report_path=Path(analysis_root)/f'job_{index:04d}'/'report.json'
        report=json.loads(report_path.read_text())
        if (report['steamid']!=case['steamid'] or report['source_sha256']!=case['demo_sha256']
            or digest(case['demo'])!=case['demo_sha256']):
            raise ValueError('Replay/report identity mismatch')
        rate=float(report['assumed_tickrate_hz'])
        if not np.isfinite(rate) or rate<=0:
            raise ValueError('Invalid assumed tickrate')
        offset=max(1,round(.1*rate))
        windows=report['engagements']
        shots=sorted({tick for w in windows for tick in w['shot_ticks']})
        # Use only pre-shot pairs covered by the same validated alive segment/window.
        valid_pre={tick for w in windows for tick in w['shot_ticks'] if tick-offset>=w['start_tick']}
        ticks=sorted(set(shots)|{tick-offset for tick in valid_pre})
        frame=DemoParser(case['demo']).parse_ticks(FIELDS,ticks=ticks) if ticks else pd.DataFrame(columns=FIELDS+['tick','steamid'])
        by_tick={tick:part for tick,part in frame.groupby('tick')}
        records=[]
        for tick in shots:
            pieces=[by_tick[t] for t in (tick-offset,tick) if t in by_tick and (t==tick or tick in valid_pre)]
            pair=pd.concat(pieces) if pieces else frame.iloc[:0]
            records.append(shot_alignment(pair,case['steamid'],tick,tick-offset))
        available=[r['nearest_horizontal_candidate'] for r in records if r['status']=='available']
        pairs=[r for r in available if r['pre_status']=='available']
        summary=dict(case_id=case['case_id'],label=case['label'],shots=len(shots),
            geometry_available=len(available),paired_before_shot=len(pairs),
            unavailable_reasons=dict(Counter(r['reason'] for r in records if r['status']!='available')),
            median_nearest_horizontal_error_degrees=float(np.median([r['absolute_yaw_error_degrees'] for r in available])) if available else None,
            median_same_candidate_error_reduction_degrees=float(np.median([r['error_reduction_degrees'] for r in pairs])) if pairs else None)
        summaries.append(summary)
        write_json(output/f'case_{index:04d}.json',dict(summary=summary,shots=records,
            demo_sha256=case['demo_sha256'],report_sha256=digest(report_path),assumed_tickrate_hz=rate,
            pre_offset_ticks=offset,actual_pre_offset_seconds=offset/rate))
        print(f"{case['case_id']}: {len(available)}/{len(shots)} shots with geometry; {len(pairs)} pairs",flush=True)
    write_json(output/'summary.json',dict(role='development_geometry_diagnostic',cases=summaries,
        manifest_sha256=digest(manifest_path),code_sha256=digest(__file__),
        dependencies={name:importlib.metadata.version(name) for name in ('numpy','pandas','demoparser2')},
        definition='XY bearing to each alive opposing player at exact shot tick; same candidate at rounded 100ms pre-shot tick. Nearest chosen by absolute horizontal bearing error at shot.',
        limitations=['No visibility/occlusion test','Not intended-target attribution','Not head/hitbox alignment; no vertical geometry',
            'No recoil correction or subtick/lag compensation','Pre-shot differences include opponent and shooter translation',
            'Opponents already dead at shot tick excluded, including lethal-tick state changes',
            'Two endpoints do not establish a continuous tracking trajectory','No classifier training or threshold selection']))
    return summaries


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path);parser.add_argument('analysis_root',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    analyze(args.manifest,args.analysis_root,args.output)


if __name__=='__main__':
    main()

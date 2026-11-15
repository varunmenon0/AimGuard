"""Fixed-opponent horizontal trajectories and window-level damage association."""
import argparse
from collections import Counter
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.baseline import digest, write_json
from aimguard.core import angle_delta
from aimguard.gameplay import identity_strings
from aimguard.target_geometry import FIELDS, shot_alignment


def prepare(frame):
    required=set(FIELDS+['tick','steamid'])
    if not required.issubset(frame.columns):
        raise ValueError('Missing tracking columns')
    result=frame.copy()
    result['steamid']=identity_strings(result['steamid'])
    for key in FIELDS+['tick']:
        result[key]=pd.to_numeric(result[key],errors='coerce')
    if not np.isfinite(result['tick']).all() or (result['tick']%1!=0).any():
        raise ValueError('Tracking ticks must be finite integers')
    if result.duplicated(['tick','steamid']).any():
        raise ValueError('Duplicate player/tick tracking identity')
    return result.sort_values(['tick','steamid']).reset_index(drop=True)


def same_shooter_inputs(actual, expected):
    # Float32 coordinates were serialized to shortest round-tripping CSV decimals.
    # Reconstruct source precision rather than tolerating arbitrary differences.
    coordinates = ['X', 'Y', 'yaw']
    states = ['health', 'life_state', 'team_num']
    return (np.array_equal(actual[coordinates].to_numpy(dtype=np.float32),
                           expected[coordinates].to_numpy(dtype=np.float32), equal_nan=True)
            and np.array_equal(actual[states].to_numpy(dtype=float),
                               expected[states].to_numpy(dtype=float), equal_nan=True))


def matching_damage(events, window, steamid):
    """Observed damage recipient within this window, not a bullet assignment."""
    matches=[]
    for event in events:
        if (event['event_type']=='player_hurt' and event.get('attacker_steamid')==str(steamid)
            and event.get('segment_id')==window['segment_id']
            and window['start_tick']<=event['tick']<=window['end_tick']
            and str(event.get('weapon','')).lower().removeprefix('weapon_')==window['weapon']
            and event.get('dmg_health',0) is not None and event['dmg_health']>0):
            victim=event.get('user_steamid')
            if isinstance(victim,str) and victim.isdigit() and int(victim)>0 and victim!=str(steamid):
                matches.append(dict(tick=int(event['tick']),opponent_id=victim,damage=float(event['dmg_health'])))
    return matches


def damage_recipients(events, window, steamid):
    return sorted({event['opponent_id'] for event in matching_damage(events,window,steamid)})


def fixed_track(frame, steamid, opponent_id, ticks, shot_ticks, tickrate, deaths=()):
    """Track one identity, splitting on every missing/invalid/nonconsecutive tick."""
    if not np.isfinite(tickrate) or tickrate<=0:
        raise ValueError('Invalid tracking tickrate')
    ticks=np.asarray(ticks,dtype=int)
    if len(ticks)==0 or (np.diff(ticks)<=0).any():
        raise ValueError('Tracking ticks must increase strictly')
    if str(steamid)==str(opponent_id):
        raise ValueError('Opponent must differ from shooter')
    shooter=frame.loc[frame.steamid.eq(str(steamid))].set_index('tick').reindex(ticks)
    opponent=frame.loc[frame.steamid.eq(str(opponent_id))].set_index('tick').reindex(ticks)
    def valid_rows(part):
        return (np.isfinite(part[FIELDS].to_numpy(dtype=float)).all(axis=1)
                &part.life_state.eq(0).to_numpy()&part.health.gt(0).to_numpy()
                &part.team_num.isin([2,3]).to_numpy())
    valid=valid_rows(shooter)&valid_rows(opponent)&shooter.team_num.ne(opponent.team_num).to_numpy()
    for victim,death_tick in deaths:
        if str(victim) in (str(steamid),str(opponent_id)) and ticks[0]<=death_tick<=ticks[-1]:
            valid &= ticks<death_tick
    dx=opponent.X.to_numpy()-shooter.X.to_numpy()
    dy=opponent.Y.to_numpy()-shooter.Y.to_numpy()
    valid &= np.hypot(dx,dy)>1e-9
    bearing=np.degrees(np.arctan2(dy,dx))
    yaw=shooter.yaw.to_numpy(dtype=float)
    error=angle_delta(bearing-yaw)
    # Team changes split a track even if the players remain opponents.
    consecutive=(np.diff(ticks)==1)&valid[:-1]&valid[1:]
    consecutive &= (np.diff(shooter.team_num.to_numpy())==0)&(np.diff(opponent.team_num.to_numpy())==0)
    yaw_rate=np.full(len(ticks),np.nan);bearing_rate=yaw_rate.copy()
    yaw_rate[1:]=np.where(consecutive,angle_delta(np.diff(yaw))*tickrate,np.nan)
    bearing_rate[1:]=np.where(consecutive,angle_delta(np.diff(bearing))*tickrate,np.nan)
    relative_rate=yaw_rate-bearing_rate
    intervals=np.isfinite(relative_rate)
    segment=np.full(len(ticks),-1,dtype=int)
    next_segment=-1
    for i in range(len(ticks)):
        if valid[i]:
            if i==0 or not consecutive[i-1]:
                next_segment+=1
            segment[i]=next_segment
    def nullable(values):
        return [float(v) if np.isfinite(v) else None for v in values]
    error=np.where(valid,error,np.nan)
    near=np.array([min(abs(int(t)-int(s)) for s in shot_ticks)/tickrate<=.1 for t in ticks]) if shot_ticks else np.zeros(len(ticks),dtype=bool)
    def summary(mask):
        points=mask&valid
        supporting=intervals&mask&np.r_[False,mask[:-1]]
        correlation=None
        a,b=yaw_rate[supporting],bearing_rate[supporting]
        if len(a)>=3 and np.std(a)>1e-9 and np.std(b)>1e-9:
            correlation=float(np.corrcoef(a,b)[0,1])
        return dict(valid_samples=int(points.sum()),valid_intervals=int(supporting.sum()),
            covered_seconds=float(supporting.sum()/tickrate),
            median_absolute_error_degrees=float(np.median(abs(error[points]))) if points.any() else None,
            median_absolute_relative_rate_dps=float(np.median(abs(relative_rate[supporting]))) if supporting.any() else None,
            yaw_bearing_rate_correlation=correlation)
    return dict(opponent_id=str(opponent_id),ticks=ticks.tolist(),segment_ids=segment.tolist(),
        signed_error_degrees=nullable(error),yaw_rate_dps=nullable(yaw_rate),bearing_rate_dps=nullable(bearing_rate),
        full_window=summary(np.ones(len(ticks),dtype=bool)),near_shot=summary(near),
        excluded_samples=int((~valid).sum()),segments=next_segment+1)


def candidate_at_tick(frame, steamid, tick, deaths):
    """Exact alive-only snapshot, with death events applied before selection."""
    dead={victim for victim,death_tick in deaths if death_tick<=tick}
    snapshot=frame.loc[frame.tick.eq(tick)&~frame.steamid.isin(dead)]
    result=shot_alignment(snapshot,steamid,tick,tick-1)
    return result.get('nearest_horizontal_candidate',{}).get('opponent_id')


def analyze(manifest_path, analysis_root, output):
    from demoparser2 import DemoParser
    manifest=json.loads(Path(manifest_path).read_text())
    if manifest.get('role')!='development':
        raise ValueError('Tracking requires explicitly designated development data')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    summaries=[]
    for index,case in enumerate(manifest['cases'],1):
        directory=Path(analysis_root)/f'job_{index:04d}'
        report=json.loads((directory/'report.json').read_text())
        if (report['steamid']!=case['steamid'] or report['source_sha256']!=case['demo_sha256']
            or digest(case['demo'])!=case['demo_sha256']):
            raise ValueError('Tracking report/demo identity mismatch')
        telemetry=pd.read_csv(directory/'telemetry.csv',dtype={'steamid':str})
        if not telemetry.steamid.eq(case['steamid']).all() or telemetry.tick.duplicated().any():
            raise ValueError('Tracking telemetry identity mismatch')
        events=json.loads((directory/'events.json').read_text())
        windows=report['engagements'];parts=[]
        for window in windows:
            part=telemetry.loc[telemetry.segment_id.eq(window['segment_id'])&telemetry.tick.between(window['start_tick'],window['end_tick'])]
            if len(part)!=window['samples'] or not part.active.all():
                raise ValueError('Tracking window telemetry mismatch')
            parts.append(part)
        ticks=sorted({int(t) for part in parts for t in part.tick})
        parser=DemoParser(case['demo'])
        frame=prepare(parser.parse_ticks(FIELDS,ticks=ticks)) if ticks else pd.DataFrame(columns=FIELDS+['tick','steamid'])
        selected=frame.loc[frame.steamid.eq(case['steamid'])].set_index('tick')
        # Check that replay re-extraction reproduces the selected player's inputs.
        if ticks:
            expected=telemetry.set_index('tick').loc[ticks]
            actual=selected.reindex(ticks)
            if not same_shooter_inputs(actual,expected):
                raise ValueError('Replay geometry differs from saved shooter telemetry')
        death_frame=parser.parse_event('player_death')
        deaths=list(zip(identity_strings(death_frame['user_steamid']),death_frame['tick'])) if len(death_frame) else []
        records=[];counts=Counter()
        # Index once; window slicing avoids scanning the full replay for every track.
        frame=frame.set_index('tick',drop=False).sort_index()
        for window,part in zip(windows,parts):
            local=frame.loc[window['start_tick']:window['end_tick']].reset_index(drop=True)
            damage=matching_damage(events,window,case['steamid'])
            recipients=sorted({event['opponent_id'] for event in damage})
            first=window['shot_ticks'][0]
            local_deaths=[(victim,int(tick)) for victim,tick in deaths if window['start_tick']<=tick<=window['end_tick']]
            nearest=candidate_at_tick(local,case['steamid'],first,local_deaths)
            before=candidate_at_tick(local,case['steamid'],first-1,local_deaths)
            opponents=sorted(set(recipients)|{p for p in (nearest,before) if p is not None})
            association='none' if not recipients else ('single_damage_recipient' if len(recipients)==1 else 'multiple_damage_recipients')
            counts[association]+=1
            if recipients and nearest:
                counts['damage_windows_with_geometric_candidate']+=1
                counts['nearest_in_damage_recipients']+=int(nearest in recipients)
            if recipients and before:
                counts['damage_windows_with_pre_shot_candidate']+=1
                counts['pre_shot_nearest_in_damage_recipients']+=int(before in recipients)
            tracks=[]
            for opponent in opponents:
                track=fixed_track(local,case['steamid'],opponent,part.tick.tolist(),window['shot_ticks'],report['assumed_tickrate_hz'],local_deaths)
                track['association_sources']=(['window_damage_recipient'] if opponent in recipients else [])+(['nearest_at_first_shot'] if opponent==nearest else [])+(['nearest_before_first_shot'] if opponent==before else [])
                tracks.append(track)
                counts['tracks']+=1
                counts['tracks_with_valid_intervals']+=int(track['full_window']['valid_intervals']>0)
            records.append(dict(engagement_id=window['engagement_id'],weapon=window['weapon'],
                shot_ticks=window['shot_ticks'],round_id=window['round_id'],association=association,
                damage_recipients=recipients,damage_events=damage,nearest_at_first_shot=nearest,nearest_before_first_shot=before,tracks=tracks))
        summary=dict(case_id=case['case_id'],label=case['label'],windows=len(windows),**dict(counts))
        summaries.append(summary)
        write_json(output/f'case_{index:04d}.json',dict(summary=summary,windows=records,
            assumed_tickrate_hz=report['assumed_tickrate_hz'],demo_sha256=case['demo_sha256'],
            input_sha256={name:digest(directory/name) for name in ('report.json','telemetry.csv','events.json')}))
        print(f"{case['case_id']}: {counts['tracks_with_valid_intervals']}/{counts['tracks']} tracks with consecutive samples",flush=True)
    write_json(output/'summary.json',dict(role='development_tracking_diagnostic',cases=summaries,
        manifest_sha256=digest(manifest_path),
        code_sha256={name:digest(Path(__file__).with_name(name)) for name in ('target_tracking.py','target_geometry.py','core.py','gameplay.py')},
        dependencies={name:importlib.metadata.version(name) for name in ('numpy','pandas','demoparser2')},
        definition='Fixed opponent per validated firearm window. Damage recipients require exact attacker, weapon, segment and positive damage. Separate geometric candidates selected at first shot and exact preceding tick; both retained without using later damage to choose either. Derivatives require consecutive valid ticks with unchanged teams. Death ticks latch exclusion through window end.',
        limitations=['Window damage recipients are not per-bullet intended-target annotations',
            'Multiple recipients retained separately; no target switching or guessed assignment',
            'No visibility, vertical/hitbox geometry, recoil or lag/subtick correction',
            'Relative bearing includes shooter and opponent translation',
            'First-shot geometric selection can disagree with later damage because targets change',
            'Overlapping windows and repeated tracks are not independent examples',
            'Match labels do not identify cheat subtype or activation ticks',
            'Exploratory development only; no model trained or detection threshold changed']))
    return summaries


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path);parser.add_argument('analysis_root',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    analyze(args.manifest,args.analysis_root,args.output)


if __name__=='__main__':
    main()

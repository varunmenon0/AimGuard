"""v0.6 live-match analysis: phase-gate samples before grouping shots or features."""
import argparse
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard import gameplay as legacy
from aimguard.baseline import digest
from aimguard.batch import validate_windows
from aimguard.combat import selected_fire,weapon_names
from aimguard.phase_audit import global_phase,WARMUP,STARTED

FEATURE_VERSION='0.6.0'
PHASE_POLICY='explicit-server-phase-v1'


def apply_phase_gate(player,events,quality,phase_frame,tickrate):
    """Preserve legacy exclusions; split segments around every new phase exclusion."""
    if not {WARMUP,STARTED}.issubset(phase_frame):raise ValueError('Required server phase properties missing; refusing unverified gameplay')
    states=global_phase(phase_frame);result=player.copy();before=result.active.to_numpy(dtype=bool)
    warm=pd.Series(pd.array([states.get(int(t),{}).get(WARMUP) for t in result.tick],dtype='boolean'),index=result.index)
    started=pd.Series(pd.array([states.get(int(t),{}).get(STARTED) for t in result.tick],dtype='boolean'),index=result.index)
    live=(warm.eq(False)&started.eq(True)).fillna(False).to_numpy(dtype=bool)
    status=np.select([warm.fillna(False).to_numpy(dtype=bool),started.eq(False).fillna(False).to_numpy(dtype=bool),live],
                     ['warmup','match_not_started','live'],default='unknown')
    active=before&live;old_segments=result.segment_id.to_numpy()
    boundary=active&(np.r_[True,~active[:-1]]|np.r_[True,np.diff(old_segments)!=0])
    result['phase_warmup']=warm;result['phase_match_started']=started;result['phase_status']=status
    result.loc[before&~live,'exclusion_reason']=['phase_'+s for s in status[before&~live]]
    result['active']=active;result['segment_id']=np.where(active,np.cumsum(boundary)-1,-1)
    matched=legacy.assign_event_segments(events,result)
    updated=dict(quality)
    updated['round_event_intervals_before_phase_gate']=updated.pop('active_round_intervals',[])
    updated['legacy_active_samples']=int(before.sum())
    updated['phase_status_counts']={str(k):int(v) for k,v in pd.Series(status).value_counts().items()}
    updated['phase_excluded_previously_active']={str(k):int(v) for k,v in pd.Series(status[before&~live]).value_counts().items()}
    updated['active_samples']=int(active.sum());updated['active_sample_fraction']=float(active.mean())
    updated['segments']=int(boundary.sum())
    updated['sample_counts_by_reason']={str(k):int(v) for k,v in result.exclusion_reason.value_counts().items()}
    same=active[1:]&active[:-1]&~boundary[1:]
    updated['active_duration_seconds']=float((np.diff(result.tick.to_numpy())[same]/tickrate).sum())
    updated['events_outside_active_segments']={name:int((matched.event_type.eq(name)&matched.segment_id.eq(-1)).sum()) for name in legacy.COMBAT_EVENTS}
    return result,matched,updated


def analyze_frames(frame,events,phase_frame,steamid,tickrate=64.,pre_s=.5,post_s=.5,shot_gap_s=.5,weapon_mode='firearms',near_shot_s=.1):
    player,matched,quality=legacy.segment_gameplay(frame,events,steamid,tickrate)
    player,matched,quality=apply_phase_gate(player,matched,quality,phase_frame,tickrate)
    windows,skipped=legacy.extract_engagements(player,matched,tickrate,pre_s,post_s,shot_gap_s,weapon_mode,near_shot_s)
    matched['selected_weapon_fire']=selected_fire(matched,weapon_mode)
    report=dict(feature_version=FEATURE_VERSION,phase_policy=PHASE_POLICY,steamid=steamid,assumed_tickrate_hz=tickrate,
        configuration=dict(pre_seconds=pre_s,post_seconds=post_s,shot_gap_seconds=shot_gap_s,weapon_mode=weapon_mode,
                           near_shot_seconds=near_shot_s,phase_policy=PHASE_POLICY),
        phase_definition='Every active recorded sample explicitly has warmup=false and match-started=true, in addition to original round/life/team/angle checks. Unknown/conflicting flags are excluded. Segments, event links, groups and features are rebuilt after gating.',
        analysis_status='complete' if windows else 'insufficient_live_evidence',data_quality=quality,engagement_count=len(windows),engagements=windows,
        grouped_shots_in_published_windows=sum(w['shot_count'] for w in windows),skipped_engagements=skipped,
        weapon_filter=dict(matched_fire_events=int(matched.event_type.eq('weapon_fire').sum()),
            selected_fire_events=int(matched.selected_weapon_fire.sum()),
            selected_fire_events_in_active_segments=int((matched.selected_weapon_fire&matched.segment_id.ge(0)).sum()),
            excluded_by_weapon=weapon_names(matched.loc[matched.event_type.eq('weapon_fire')&~matched.selected_weapon_fire]).value_counts().to_dict()),
        source_event_counts={name:len(events.get(name,[])) for name in legacy.ROUND_EVENTS+legacy.COMBAT_EVENTS},
        note='Phase-checked descriptive analysis, not a cheating verdict. v0.5 frozen models are incompatible. Insufficient evidence is not a legitimate classification.')
    violations=validate_windows(player,matched,report)
    for w in windows:
        part=player.loc[player.tick.between(w['start_tick'],w['end_tick'])]
        if not part.phase_status.eq('live').all():violations.append(dict(engagement_id=w['engagement_id'],reasons=['non_live_phase']))
    if violations:raise ValueError(f'Phase-checked window validation failed: {violations}')
    report['structural_violations']=violations
    return player,matched,report


def analyze_demo(demo,steamid,output,tickrate=64.,pre_s=.5,post_s=.5,shot_gap_s=.5,max_plots=0,weapon_mode='firearms',near_shot_s=.1):
    from demoparser2 import DemoParser
    demo,output=Path(demo),Path(output)
    if output.exists():raise ValueError('Use a new output directory')
    if not isinstance(steamid,str) or not steamid.isdigit():raise ValueError('SteamID must be an exact numeric string')
    if not isinstance(max_plots,int) or isinstance(max_plots,bool) or max_plots<0:raise ValueError('max-plots must be a nonnegative integer')
    legacy.positive_finite(tickrate=tickrate,shot_gap_s=shot_gap_s,near_shot_s=near_shot_s)
    if not all(np.isfinite(v) and v>=0 for v in (pre_s,post_s)):raise ValueError('pre/post seconds must be finite and nonnegative')
    frame,events=legacy.load_gameplay_demo(demo,steamid)
    requested=sorted(set(map(int,legacy.checked_ticks(frame,'telemetry'))))
    phases=DemoParser(str(demo)).parse_ticks([WARMUP,STARTED],ticks=requested,players=[int(steamid)])
    player,matched,report=analyze_frames(frame,events,phases,steamid,tickrate,pre_s,post_s,shot_gap_s,weapon_mode,near_shot_s)
    report.update(source=str(demo.resolve()),source_sha256=digest(demo),
        dependencies={name:importlib.metadata.version(name) for name in ('demoparser2','numpy','pandas','matplotlib')},
        runtime_sha256={name:digest(Path(__file__).with_name(name)) for name in ('phase_gameplay.py','phase_audit.py','gameplay.py','combat.py','core.py')})
    report['configuration']['max_plots']=max_plots
    output.mkdir(parents=True,exist_ok=False)
    player.to_csv(output/'telemetry.csv',index=False);(output/'events.json').write_text(matched.to_json(orient='records',indent=2)+'\n')
    report['plots']=legacy.plot_engagements(player,report['engagements'],output,tickrate,max_plots) if max_plots else []
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    from aimguard.review import build_review
    build_review(output,output/'review.html')
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('demo',type=Path);parser.add_argument('--steamid',required=True)
    parser.add_argument('--tickrate',type=float,default=64.);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--pre-seconds',type=float,default=.5);parser.add_argument('--post-seconds',type=float,default=.5)
    parser.add_argument('--shot-gap-seconds',type=float,default=.5);parser.add_argument('--near-shot-seconds',type=float,default=.1)
    parser.add_argument('--weapon-mode',choices=['firearms','all'],default='firearms');parser.add_argument('--max-plots',type=int,default=0)
    args=parser.parse_args(argv)
    report=analyze_demo(args.demo,args.steamid,args.output,args.tickrate,args.pre_seconds,args.post_seconds,args.shot_gap_seconds,args.max_plots,args.weapon_mode,args.near_shot_seconds)
    print(f"v{FEATURE_VERSION}: {report['data_quality']['active_samples']} live active samples, {report['engagement_count']} rebuilt windows, status {report['analysis_status']}")
    return 0 if report['analysis_status']=='complete' else 2


if __name__=='__main__':raise SystemExit(main())

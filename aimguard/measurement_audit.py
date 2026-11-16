"""Small post-evaluation combat/field audit; no model fitting or precise eye assumptions."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.baseline import digest,write_json
from aimguard.core import angle_delta
from aimguard.gameplay import identity_strings
from aimguard.target_geometry import alive,bearing_error
from aimguard.target_tracking import candidate_at_tick,matching_damage,prepare,same_shooter_inputs
from aimguard.tracking_baseline import load_model,score

SAMPLE=['R-002','R-014','R-013','R-001','R-003','R-017']
PROBES=['CCSPlayerPawn.m_vecViewOffset','CCSPlayerPawn.m_vecViewOffset[0]',
    'CCSPlayerPawn.m_vecViewOffset[1]','CCSPlayerPawn.m_vecViewOffset[2]',
    'CCSPlayerPawn.m_vHeadConstraintOffset','CCSPlayerPawn.CCSPlayer_CameraServices.m_vecCsViewPunchAngle',
    'CCSPlayerPawn.CBodyComponentBaseAnimGraph.m_nHitboxSet','aim_punch_angle','duck_amount',
    'is_scoped','active_weapon_name','spotted','approximate_spotted_by']
BASE=['X','Y','Z','yaw','pitch','health','life_state','team_num']


def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,np.ndarray)):return [clean(v) for v in value]
    if isinstance(value,np.generic):return clean(value.item())
    if value is None or value is pd.NA:return None
    if isinstance(value,float) and not np.isfinite(value):return None
    return value


def origin_geometry(shooter,target,yaw,pitch):
    """Source-convention view direction versus body-origin ray, explicitly a proxy."""
    shooter,target=np.asarray(shooter,dtype=float),np.asarray(target,dtype=float)
    if shooter.shape!=(3,) or target.shape!=(3,) or not np.isfinite(np.r_[shooter,target,yaw,pitch]).all():
        raise ValueError('Finite XYZ/yaw/pitch required')
    if abs(pitch)>90:raise ValueError('Pitch outside playable angle range')
    delta=target-shooter;distance=float(np.linalg.norm(delta));horizontal=float(np.hypot(delta[0],delta[1]))
    if distance<=1e-9:return None
    y,p=np.deg2rad([yaw,pitch]);view=np.array([np.cos(p)*np.cos(y),np.cos(p)*np.sin(y),-np.sin(p)])
    proxy=float(np.degrees(np.arccos(np.clip(np.dot(view,delta/distance),-1,1))))
    bearing_yaw=float(np.degrees(np.arctan2(delta[1],delta[0]))) if horizontal>1e-9 else None
    return dict(observed_origin_delta_xyz=delta.tolist(),horizontal_distance_units=horizontal,origin_distance_units=distance,height_delta_units=float(delta[2]),
        origin_bearing_pitch_degrees=float(np.degrees(np.arctan2(-delta[2],horizontal))),
        horizontal_error_degrees=abs(float(angle_delta(bearing_yaw-yaw))) if bearing_yaw is not None else None,
        origin_proxy_angular_error_degrees=proxy,
        geometry_kind='body-origin proxy; not eye-to-head/hitbox aim error')


def select_windows(report,tracking,per_category=3):
    if len(report['engagements'])!=len(tracking['windows']):raise ValueError('Window count mismatch')
    selected=[];counts=Counter()
    for published,window in zip(report['engagements'],tracking['windows']):
        if any(published[key]!=window[key] for key in ('engagement_id','weapon','shot_ticks')):
            raise ValueError('Window identity mismatch')
        after=[e for e in window['damage_events'] if e['tick']>=window['shot_ticks'][0]]
        category='damage_at_or_after_first_shot' if after else 'no_damage_at_or_after_first_shot'
        if counts[category]>=per_category:continue
        counts[category]+=1
        selected.append((published,window,category))
    return selected


def probe(parser,prop,ticks):
    try:
        frame=parser.parse_ticks([prop],ticks=ticks)
    except Exception as exc:
        return dict(status='parser_error',error_type=type(exc).__name__,error=str(exc)),None
    if prop not in frame:
        return dict(status='requested_column_omitted',returned_columns=list(frame.columns)),None
    values=[clean(value) for value in frame[prop].tolist()]
    nonnull=[value for value in values if value is not None]
    numeric=[]
    for value in nonnull:
        if prop=='approximate_spotted_by':continue
        if isinstance(value,(int,float,bool)):numeric.append(float(value))
        elif isinstance(value,list) and all(isinstance(v,(int,float,bool)) for v in value):numeric.extend(map(float,value))
    result=dict(status='returned',rows=len(values),nonnull=len(nonnull),examples=nonnull[:3])
    if numeric:result.update(numeric_min=min(numeric),numeric_max=max(numeric),nonzero_numeric_values=sum(value!=0 for value in numeric))
    frame=frame.copy();frame['steamid']=identity_strings(frame['steamid'])
    if frame.duplicated(['tick','steamid']).any():raise ValueError('Duplicate optional-property player/tick')
    return result,frame.set_index(['tick','steamid'])[prop].to_dict()


def snapshot(frame,steamid,tick,deaths):
    part=frame.loc[frame.tick.eq(tick)].copy();dead={victim for victim,t in deaths if t<=tick}
    if not part.steamid.eq(steamid).any():return dict(status='unavailable',reason='missing_exact_shooter_sample',candidates=[])
    if steamid in dead:return dict(status='unavailable',reason='shooter_death_event_latched',candidates=[])
    part=part.loc[~part.steamid.isin(dead)]
    player=part.loc[part.steamid.eq(steamid)]
    if len(player)!=1:return dict(status='unavailable',reason='missing_or_dead_shooter',candidates=[])
    shooter=player.iloc[0]
    if not alive(shooter) or not np.isfinite(shooter[BASE].to_numpy(dtype=float)).all():
        return dict(status='unavailable',reason='invalid_shooter',candidates=[])
    candidates=[]
    for _,target in part.iterrows():
        if target.steamid==steamid or not alive(target) or target.team_num==shooter.team_num:continue
        if not np.isfinite(target[['X','Y','Z']].to_numpy(dtype=float)).all():continue
        geometry=origin_geometry(shooter[['X','Y','Z']],target[['X','Y','Z']],shooter.yaw,shooter.pitch)
        if geometry is not None:candidates.append(dict(opponent_id=target.steamid,**geometry))
    nearest=min(candidates,key=lambda r:(r['origin_proxy_angular_error_degrees'],r['opponent_id']))['opponent_id'] if candidates else None
    return dict(status='available',tick=int(tick),recorded_yaw=float(shooter.yaw),recorded_pitch=float(shooter.pitch),
        candidates=candidates,nearest_origin_proxy_candidate=nearest,
        eye_to_head_error_degrees=None,validated_visibility=None)


def audit(model_directory,reserved_path,evaluation_root,output):
    from demoparser2 import DemoParser
    model_directory,reserved_path,evaluation_root,output=map(Path,(model_directory,reserved_path,evaluation_root,output))
    bundle=load_model(model_directory);reserved=json.loads(reserved_path.read_text());evaluation=json.loads((evaluation_root/'evaluation.json').read_text())
    if evaluation['model_sha256']!=digest(model_directory/'model.json') or evaluation['reserved_manifest_sha256']!=digest(reserved_path):
        raise ValueError('Audit source receipts mismatch')
    rows={r['case_id']:(i,r) for i,r in enumerate(evaluation['predictions'],1)}
    cases={c['case_id']:c for c in reserved['cases']}
    if not set(SAMPLE)<=set(rows)&set(cases):raise ValueError('Fixed audit sample missing')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'plan.json',dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(),case_ids=SAMPLE,
        selection='Three false flags: high score R-002, high acceleration R-014, near cutoff R-013; two legitimate unflagged comparisons R-001/R-003; first cheating-labeled flagged case R-017. Descriptive sample, no accuracy inference.',
        window_selection='First three windows with matching positive damage at/after first shot, plus first three without. Earlier padding damage is separate.',
        probes=PROBES,code_sha256=digest(__file__),evaluation_sha256=digest(evaluation_root/'evaluation.json'),
        angle_convention_source='https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/mathlib/mathlib_base.cpp',
        parser_reference='https://github.com/LaihoE/demoparser',
        note='Only observed fields and body-origin geometry. No invented eye/head height, spotted-as-visibility inference, recoil correction or model fitting.'))
    summaries=[]
    for case_id in SAMPLE:
        index,row=rows[case_id];case=cases[case_id]
        if any(row[key]!=case[key] for key in ('steamid','match_id','label')) or row['status']!='scored':raise ValueError('Audit case identity/status mismatch')
        value=score(bundle,[row['features'][name] for name in bundle['feature_names']])
        if not np.isclose(value,row['baseline_score'],atol=1e-12,rtol=0) or row['flagged']!=(value>=bundle['threshold']):
            raise ValueError('Audit frozen decision mismatch')
        directory=evaluation_root/f'case_{index:03d}';report_path=directory/'report.json';tracking_path=directory/'tracking.json'
        if digest(report_path)!=row['report_sha256'] or digest(tracking_path)!=row['tracking_sha256'] or digest(case['demo'])!=case['demo_sha256']:
            raise ValueError('Audit replay/analysis checksum mismatch')
        report=json.loads(report_path.read_text());tracking=json.loads(tracking_path.read_text());events=json.loads((directory/'events.json').read_text())
        selected=select_windows(report,tracking);ticks=set()
        for published,window,_ in selected:
            if matching_damage(events,published,case['steamid'])!=window['damage_events']:raise ValueError('Audit damage link changed')
            ticks.update(t for shot in window['shot_ticks'] for t in (shot-1,shot))
            ticks.update(t for event in window['damage_events'] for t in (event['tick']-1,event['tick']))
        ticks=sorted(ticks);parser=DemoParser(case['demo']);fields=parser.list_updated_fields()
        relevant=[field for field in fields if any(term in field.lower() for term in ('viewoffset','eye','headconstraint','hitbox','punch','spotted'))]
        frame=prepare(parser.parse_ticks(BASE,ticks=ticks))
        if digest(directory/'telemetry.csv')!=tracking['input_sha256']['telemetry.csv']:raise ValueError('Saved telemetry checksum changed')
        saved=pd.read_csv(directory/'telemetry.csv',usecols=['tick',*BASE]).set_index('tick').reindex(ticks)
        extracted=frame.loc[frame.steamid.eq(case['steamid'])].set_index('tick').reindex(ticks)
        if not same_shooter_inputs(extracted,saved) or not np.array_equal(extracted[['Z','pitch']].to_numpy(dtype=np.float32),saved[['Z','pitch']].to_numpy(dtype=np.float32),equal_nan=True):
            raise ValueError('Sparse audit extraction differs from saved shooter telemetry')
        death_frame=parser.parse_event('player_death')
        deaths=list(zip(identity_strings(death_frame.user_steamid),death_frame.tick)) if len(death_frame) else []
        availability={};optional={}
        for prop in PROBES:availability[prop],optional[prop]=probe(parser,prop,ticks)
        windows=[];counts=Counter()
        for published,window,category in selected:
            local_deaths=[(victim,int(t)) for victim,t in deaths if published['start_tick']<=t<=published['end_tick']]
            first=window['shot_ticks'][0];before=first-1
            local_frame=frame.loc[frame.tick.between(published['start_tick'],published['end_tick'])]
            nearest=candidate_at_tick(local_frame,case['steamid'],before,local_deaths)
            if nearest!=window['nearest_before_first_shot']:raise ValueError('Frozen horizontal candidate failed reproduction')
            anchors=[dict(kind='pre_first_shot',tick=before),dict(kind='first_shot',tick=first)]
            for event in window['damage_events']:
                anchors.extend([dict(kind='pre_damage',tick=event['tick']-1,damage_recipient=event['opponent_id']),
                                dict(kind='damage',tick=event['tick'],damage_recipient=event['opponent_id'])])
            samples=[]
            for anchor in anchors:
                inside=published['start_tick']<=anchor['tick']<=published['end_tick']
                snap=snapshot(local_frame,case['steamid'],anchor['tick'],local_deaths) if inside else dict(status='unavailable',reason='outside_published_window',candidates=[])
                snap['within_published_window']=inside
                if anchor['kind']=='pre_first_shot':
                    counts['pre_shot_available']+=int(snap['status']=='available')
                    if nearest is not None and snap.get('nearest_origin_proxy_candidate') is not None:
                        counts['comparable_initial_ranks']+=1
                        counts['initial_rank_differs_under_origin_proxy']+=int(nearest!=snap['nearest_origin_proxy_candidate'])
                observation=dict(anchor,**snap)
                observation['saved_shooter_sample_present']=anchor['tick'] in saved.index and bool(np.isfinite(saved.loc[anchor['tick'],'life_state']))
                observation['optional_candidate_fields']={candidate['opponent_id']:{prop:clean(values.get((anchor['tick'],candidate['opponent_id']))) if values is not None else None for prop,values in optional.items()} for candidate in snap['candidates']}
                observation['optional_shooter_fields']={prop:clean(values.get((anchor['tick'],case['steamid']))) if values is not None else None for prop,values in optional.items()}
                samples.append(observation)
            damage_after=[event for event in window['damage_events'] if event['tick']>=first]
            if damage_after:
                recipients={event['opponent_id'] for event in damage_after}
                initial=next(sample for sample in samples if sample['kind']=='pre_first_shot')
                counts['initial_horizontal_in_damage_recipient_set']+=int(nearest in recipients)
                counts['initial_origin_proxy_in_damage_recipient_set']+=int(initial.get('nearest_origin_proxy_candidate') in recipients)
            raw_damage=[event for event in events if event['event_type']=='player_hurt' and event.get('attacker_steamid')==case['steamid']
                and event.get('segment_id')==published['segment_id'] and (event.get('dmg_health') or 0)>0
                and published['start_tick']<=event['tick']<=published['end_tick'] and str(event.get('weapon','')).removeprefix('weapon_')==window['weapon']]
            windows.append(dict(engagement_id=window['engagement_id'],weapon=window['weapon'],category=category,shot_ticks=window['shot_ticks'],
                frozen_horizontal_candidate=nearest,damage_at_or_after_first_shot=damage_after,
                padding_damage_before_first_shot=[event for event in window['damage_events'] if event['tick']<first],
                damage_event_details=clean([{key:event.get(key) for key in ('tick','user_steamid','dmg_health','hitgroup')} for event in raw_damage]),samples=samples,
                review_status='telemetry_audited_not_rendered_gameplay',eye_geometry='unavailable_unverified',visibility='unverified'))
            counts[category]+=1
        summary=dict(case_id=case_id,label=case['label'],frozen_score=row['baseline_score'],frozen_flag=row['flagged'],windows=len(windows),**dict(counts))
        summaries.append(summary)
        write_json(output/f'{case_id}.json',clean(dict(summary=summary,property_availability=availability,relevant_updated_fields=relevant,windows=windows,
            demo_path=str(Path(case['demo']).resolve()),shooter_telemetry_reproduced=True,telemetry_sha256=digest(directory/'telemetry.csv'),demo_sha256=case['demo_sha256'],report_sha256=digest(report_path),tracking_sha256=digest(tracking_path))))
        print(f'{case_id}: {len(windows)} windows; field probes complete',flush=True)
    result=dict(role='post_evaluation_measurement_audit',cases=summaries,case_sha256={case['case_id']:digest(output/(case['case_id']+'.json')) for case in summaries},plan_sha256=digest(output/'plan.json'),
        dependencies={name:importlib.metadata.version(name) for name in ('demoparser2','numpy','pandas')},
        eye_head_geometry_validated=False,visibility_validated=False,model_changed=False,
        limitations=['Body-origin ray is not eye-to-head or hitbox geometry',
            'Source SDK pitch convention is a diagnostic contract, not a CS2 eye-position validation',
            'Spotted/mask, hitbox-set index and head-constraint fields are not independently validated visibility/head positions',
            'Damage labels recipients and hitgroups, not intended target on every shot',
            'Telemetry audit cannot substitute for rendered CS2 gameplay annotation',
            'Small selected sample gives no accuracy/generalization estimate'])
    write_json(output/'summary.json',result);return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('model_directory','reserved_path','evaluation_root'):parser.add_argument(name,type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args(argv)
    audit(args.model_directory,args.reserved_path,args.evaluation_root,args.output)


if __name__=='__main__':main()

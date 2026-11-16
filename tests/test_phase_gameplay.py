import json
import numpy as np
import pandas as pd
import pytest
from aimguard import phase_gameplay as phase
from aimguard.phase_audit import WARMUP,STARTED
from aimguard.baseline import report_features


def inputs(shots=(35,70,90),warmup_until=60,unknown=()):
    tick=np.arange(180)
    frame=pd.DataFrame(dict(tick=tick,steamid='123',yaw=tick*.2,pitch=np.sin(tick/20),health=100,life_state=0,team_num=2,name='fixture'))
    events=dict(round_start=pd.DataFrame(dict(tick=[0])),round_freeze_end=pd.DataFrame(dict(tick=[10])),round_end=pd.DataFrame(dict(tick=[170])),
        weapon_fire=pd.DataFrame(dict(tick=shots,user_steamid=['123']*len(shots),weapon=['ak47']*len(shots))))
    flags=pd.DataFrame({'tick':tick,WARMUP:tick<warmup_until,STARTED:tick>=warmup_until}).loc[~pd.Series(tick).isin(unknown)]
    return frame,events,flags


def test_gate_rebuilds_groups_and_event_segments_before_any_features():
    frame,events,flags=inputs(unknown=range(80,85))
    player,matched,report=phase.analyze_frames(frame,events,flags,'123')
    assert [w['shot_ticks'] for w in report['engagements']]==[[70],[90]]
    assert not player.loc[player.tick.lt(60),'active'].any()
    assert player.loc[player.tick.between(80,84),'phase_status'].eq('unknown').all()
    assert player.loc[79,'segment_id']!=player.loc[85,'segment_id']
    assert matched.loc[matched.tick.eq(35),'segment_id'].item()==-1
    assert matched.loc[matched.tick.eq(70),'segment_id'].item()!=matched.loc[matched.tick.eq(90),'segment_id'].item()
    assert report['structural_violations']==[]
    assert report['data_quality']['phase_excluded_previously_active']=={'warmup':50,'unknown':5}
    assert sum(report['data_quality']['sample_counts_by_reason'].values())==len(player)
    for window in report['engagements']:
        part=player.loc[player.tick.between(window['start_tick'],window['end_tick'])]
        assert part.active.all() and part.phase_status.eq('live').all()


def test_pre_phase_angles_cannot_contaminate_live_feature_values():
    frame,events,flags=inputs()
    _,_,before=phase.analyze_frames(frame,events,flags,'123')
    frame.loc[frame.tick.lt(60),'yaw']=np.where(frame.loc[frame.tick.lt(60),'tick']%2,170.,-170.)
    _,_,after=phase.analyze_frames(frame,events,flags,'123')
    assert before['engagements']==after['engagements']


def test_phase_gate_never_reactivates_death_latched_samples():
    frame,events,flags=inputs(shots=(70,100,140),warmup_until=0)
    events['player_death']=pd.DataFrame(dict(tick=[95],user_steamid=['123'],attacker_steamid=['456']))
    frame.loc[100:119,['health','life_state']]=[0,2]
    player,matched,report=phase.analyze_frames(frame,events,flags,'123')
    assert not player.loc[95:119,'active'].any() and player.loc[120,'active']
    assert matched.loc[matched.event_type.eq('weapon_fire')&matched.tick.eq(100),'segment_id'].item()==-1


def test_missing_phase_properties_fail_closed_and_all_warmup_is_insufficient_not_legitimate():
    frame,events,flags=inputs(warmup_until=999)
    with pytest.raises(ValueError,match='phase properties'):phase.analyze_frames(frame,events,flags.drop(columns=[WARMUP]),'123')
    player,matched,report=phase.analyze_frames(frame,events,flags,'123')
    assert not player.active.any() and report['engagements']==[]
    assert report['analysis_status']=='insufficient_live_evidence'
    assert report['weapon_filter']['selected_fire_events_in_active_segments']==0
    assert 'flagged' not in report


def test_new_reports_reject_legacy_frozen_feature_protocol():
    frame,events,flags=inputs()
    _,_,report=phase.analyze_frames(frame,events,flags,'123')
    assert report['feature_version']=='0.6.0' and report['configuration']['phase_policy']==phase.PHASE_POLICY
    with pytest.raises(ValueError,match='Feature version'):report_features(report)


def test_new_analyzer_exports_phase_rows_review_and_refuses_reused_output(tmp_path,monkeypatch):
    frame,events,flags=inputs();demo=tmp_path/'fixture.dem';demo.write_bytes(b'fixture')
    monkeypatch.setattr(phase.legacy,'load_gameplay_demo',lambda *a:(frame,events))
    import demoparser2
    class Parser:
        def __init__(self,*a):pass
        def parse_ticks(self,*a,**k):return flags
    monkeypatch.setattr(demoparser2,'DemoParser',Parser)
    output=tmp_path/'analysis';report=phase.analyze_demo(demo,'123',output)
    exported=pd.read_csv(output/'telemetry.csv')
    assert exported.loc[exported.active,'phase_status'].eq('live').all()
    assert (output/'review.html').exists() and report['runtime_sha256']['phase_gameplay.py']
    assert json.load(open(output/'report.json'))['feature_version']=='0.6.0'
    with pytest.raises(ValueError,match='new output'):phase.analyze_demo(demo,'123',output)


def test_batch_isolates_failed_jobs_and_does_not_call_legacy_analyzer(tmp_path,monkeypatch):
    from aimguard import phase_batch
    jobs=[dict(demo='bad.dem',steamid='1',tickrate=64),dict(demo='good.dem',steamid='2',tickrate=64)]
    manifest=tmp_path/'jobs.json';manifest.write_text(json.dumps(jobs))
    def analyze(demo,steamid,output,**kwargs):
        if steamid=='1':raise ValueError('Missing phase properties')
        return dict(analysis_status='complete',source_sha256='verified',feature_version='0.6.0',engagement_count=1,structural_violations=[],
            data_quality=dict(round_event_anomalies=[],active_samples=100,phase_excluded_previously_active={'warmup':10}))
    monkeypatch.setattr(phase_batch,'analyze_demo',analyze)
    result=phase_batch.run_batch(manifest,tmp_path/'batch')
    assert result['counts']=={'passed':1,'warning':0,'error':1}
    assert result['jobs'][0]['error']=='Missing phase properties' and result['jobs'][1]['feature_version']=='0.6.0'

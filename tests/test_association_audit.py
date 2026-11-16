import json
import pytest
from aimguard.association_audit import audit, audit_event, observation


def track(player,errors,segments=None,ticks=None):
    return dict(opponent_id=player,ticks=ticks or [10,11,12,13],
        signed_error_degrees=errors,segment_ids=segments or [0,0,0,0])


def window(candidate='a',recipient_errors=None):
    return dict(shot_ticks=[10],nearest_at_first_shot=candidate,
        tracks=[track('a',[1,2,3,4]),track('b',recipient_errors or [5,4,2,1])])


def test_uninterrupted_pairwise_order_reversal_is_descriptive_not_a_target_verdict():
    result=audit_event(window(),dict(tick=14,opponent_id='b'))
    assert result['classification']=='pairwise_rank_reversal'
    assert result['initial_recipient_minus_candidate_degrees']==4
    assert result['pre_damage_recipient_minus_candidate_degrees']==-3
    assert 'intended_target' not in result


def test_original_candidate_can_remain_closer_despite_damage_to_another_player():
    result=audit_event(window(recipient_errors=[5,6,7,8]),dict(tick=14,opponent_id='b'))
    assert result['classification']=='initial_candidate_still_closer'


def test_interruption_prevents_temporal_order_interpretation():
    value=window();value['tracks'][1]['segment_ids']=[0,-1,1,1]
    assert audit_event(value,dict(tick=14,opponent_id='b'))['classification']=='pair_interrupted'


def test_exact_pre_damage_sample_required_without_nearest_fallback():
    value=window();value['tracks'][1]=track('b',[5,4,2],ticks=[10,11,12],segments=[0,0,0])
    assert audit_event(value,dict(tick=14,opponent_id='b'))['classification']=='pre_damage_pair_unavailable'


@pytest.mark.parametrize('event_tick',[9,10,11])
def test_early_damage_has_no_later_pre_damage_comparison(event_tick):
    assert audit_event(window(),dict(tick=event_tick,opponent_id='b'))['classification']=='no_later_pre_damage_sample'


def test_agreement_missing_candidate_tie_and_inconsistent_initial_ranking():
    assert audit_event(window(),dict(tick=14,opponent_id='a'))['classification']=='initial_agreement'
    assert audit_event(window(candidate=None),dict(tick=14,opponent_id='b'))['classification']=='no_initial_candidate'
    assert audit_event(window(recipient_errors=[5,5,5,4]),dict(tick=14,opponent_id='b'))['classification']=='pairwise_tie'
    assert audit_event(window(recipient_errors=[0,0,0,0]),dict(tick=14,opponent_id='b'))['classification']=='initial_ranking_inconsistent'


def test_invalid_tracks_are_not_silently_accepted():
    value=track('b',[1,2,3,4],ticks=[10,11,11,13])
    with pytest.raises(ValueError,match='increase strictly'):
        observation(value,10)
    with pytest.raises(ValueError,match='bearing error'):
        observation(track('b',[float('nan'),1,2,3]),10)
    assert observation(track('b',[None,1,2,3]),10) is None


def test_audit_rejects_manifest_mismatch_before_creating_output(tmp_path):
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps(dict(role='development',cases=[])))
    (tmp_path/'summary.json').write_text(json.dumps(dict(manifest_sha256='wrong')))
    with pytest.raises(ValueError,match='manifest checksum'):
        audit(manifest,tmp_path,tmp_path,tmp_path/'output')
    assert not (tmp_path/'output').exists()


def test_pre_shot_anchor_retains_victim_excluded_at_lethal_shot_tick():
    value=window();value['nearest_before_first_shot']='b'
    event=dict(tick=10,opponent_id='b')
    assert audit_event(value,event)['classification']=='no_later_pre_damage_sample'
    before=audit_event(value,event,'pre_shot_tick')
    assert before['classification']=='initial_agreement'
    assert before['anchor_tick']==9


def test_complete_audit_verifies_sources_and_preserves_both_anchor_results(tmp_path):
    from aimguard.baseline import digest
    analysis=tmp_path/'analysis';source=analysis/'job_0001';source.mkdir(parents=True)
    tracking=tmp_path/'tracking';tracking.mkdir()
    manifest=tmp_path/'manifest.json'
    case=dict(case_id='E-05',label='cheating',steamid='1',demo_sha256='demo-hash')
    manifest.write_text(json.dumps(dict(role='development',cases=[case])))
    published=dict(engagement_id=0,segment_id=0,start_tick=9,end_tick=14,shot_ticks=[10],round_id=1,weapon='ak47')
    event=dict(event_type='player_hurt',tick=14,attacker_steamid='1',user_steamid='2',segment_id=0,weapon='ak47',dmg_health=20)
    (source/'events.json').write_text(json.dumps([event]))
    (source/'telemetry.csv').write_text('fixture')
    (source/'report.json').write_text(json.dumps(dict(steamid='1',source_sha256='demo-hash',engagements=[published])))
    value=window();value.update(published)
    value['tracks'][0]['opponent_id']='3';value['tracks'][1]['opponent_id']='2'
    value.update(nearest_at_first_shot='3',nearest_before_first_shot='2',
        damage_events=[dict(tick=14,opponent_id='2',damage=20.)])
    case_summary=dict(case_id='E-05',label='cheating')
    record=dict(summary=case_summary,demo_sha256='demo-hash',windows=[value],
        input_sha256={name:digest(source/name) for name in ('report.json','telemetry.csv','events.json')})
    (tracking/'case_0001.json').write_text(json.dumps(record))
    (tracking/'summary.json').write_text(json.dumps(dict(cases=[case_summary],manifest_sha256=digest(manifest))))
    result=audit(manifest,analysis,tracking,tmp_path/'output')
    assert result['shot_tick']=={'pairwise_rank_reversal':1}
    assert result['pre_shot_tick']=={'initial_agreement':1}
    saved=json.loads((tmp_path/'output'/'audit.json').read_text())
    assert saved['cases'][0]['unique_damage_records']==1
    assert saved['occurrences'][0]['pre_shot_audit']['anchor_tick']==9
    (source/'events.json').write_text('[]')
    with pytest.raises(ValueError,match='input checksum'):
        audit(manifest,analysis,tracking,tmp_path/'blocked')
    assert not (tmp_path/'blocked').exists()

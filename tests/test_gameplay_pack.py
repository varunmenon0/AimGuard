import csv
import json
import pytest
from aimguard.baseline import digest
from aimguard.gameplay_pack import choose_control,clip_bounds,import_reviews


def test_clip_bounds_use_ticks_and_preserve_context_without_running_game():
    assert clip_bounds(1000,64,2000)==(488,1256)
    assert clip_bounds(200,64,300)==(96,300)
    for tick,rate,last in ((10,64,100),(100,0,200),(100,float('nan'),200),(200,64,100)):
        with pytest.raises(ValueError):clip_bounds(tick,rate,last)


def controls():
    windows=[];tracks=[];events=[]
    for i,weapon in enumerate(('ak47','usp_silencer','deagle')):
        window=dict(engagement_id=i,round_id=1,segment_id=0,shot_ticks=[20+i*40],weapon=weapon,start_tick=i*40,end_tick=30+i*40)
        windows.append(window)
        track=dict(window,nearest_before_first_shot='a',tracks=[dict(opponent_id='a',ticks=list(range(i*40,i*40+26)),segment_ids=[0]*26,
            signed_error_degrees=[2.]*26,yaw_rate_dps=[5.]*26,bearing_rate_dps=[2.]*26)])
        tracks.append(track);events.append(dict(event_type='player_death',attacker_steamid='1',segment_id=0,tick=22+i*40,weapon=weapon))
    return dict(engagements=windows,assumed_tickrate_hz=64),dict(windows=tracks),events


def test_controls_match_exact_weapon_then_family_then_chronology():
    report,tracking,events=controls()
    assert choose_control(report,tracking,events,'1','deagle')==dict(window_index=2,kill_tick=102,weapon_match='exact')
    assert choose_control(report,tracking,events,'1','glock')==dict(window_index=1,kill_tick=62,weapon_match='family')
    assert choose_control(report,tracking,events,'1','awp')==dict(window_index=0,kill_tick=22,weapon_match='unmatched')


def test_control_selection_rejects_wrong_attacker_weapon_segment_and_identity():
    report,tracking,events=controls()
    for event in events:event['attacker_steamid']='2'
    with pytest.raises(ValueError,match='No eligible'):choose_control(report,tracking,events,'1','deagle')
    report,tracking,events=controls();tracking['windows'][0]['engagement_id']=99
    with pytest.raises(ValueError,match='identity'):choose_control(report,tracking,events,'1','deagle')


def fixture(tmp_path):
    queue=tmp_path/'queue';queue.mkdir();pack=tmp_path/'pack';pack.mkdir()
    event=dict(review_id='A:0',case_id='A',engagement_id=0,round_id=1,demo='/local/demo.dem',demo_sha256='abc',steamid='1',
        start_tick=10,first_shot_tick=20,end_tick=30,review_status='pending',review_source='unreviewed',observed_behavior='unreviewed',
        assistance_assessment='unreviewed',evidence_reference='',evidence_note='',reviewer='')
    def write_csv(path,row):
        with path.open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(row));writer.writeheader();writer.writerow(row)
    template=queue/'event-review-template.csv';write_csv(template,event)
    (queue/'review-queue.json').write_text(json.dumps(dict(role='pending_behavior_review',events=[event],template_sha256=digest(template))))
    (queue/'comparison.json').write_text(json.dumps(dict(review_queue_sha256=digest(queue/'review-queue.json'))))
    row=dict(review_alias='R01',demo_file='D01.dem',steamid='1',player_name='Player',start_tick=96,event_tick=1000,end_tick=1256,weapon='deagle',
        playback_status='pending',pov_confirmed='',xray_disabled='',game_build='',visibility='unreviewed',observed_behavior='unreviewed',
        assistance_assessment='unreviewed',evidence_reference='',evidence_note='',reviewer='')
    write_csv(pack/'review-template.csv',row)
    (pack/'selection-private.json').write_text(json.dumps(dict(selection=[dict(review_alias='R01',event_review_id='A:0')])))
    (pack/'pack.json').write_text(json.dumps(dict(events=[row],template_sha256=digest(pack/'review-template.csv'),
        private_selection_sha256=digest(pack/'selection-private.json'),source_queue_sha256=digest(queue/'review-queue.json'))))
    return pack,queue,row,write_csv


def test_pending_and_unavailable_playback_never_create_negative_labels(tmp_path):
    pack,queue,row,write_csv=fixture(tmp_path)
    path=tmp_path/'annotations.csv';write_csv(path,row)
    result=import_reviews(pack,queue,path,tmp_path/'pending')
    assert result['reviewed']==0 and result['pending']==1 and result['training_labels_created'] is False
    row.update(playback_status='unavailable',reviewer='Reviewer',evidence_note='CS2 unavailable')
    write_csv(path,row);result=import_reviews(pack,queue,path,tmp_path/'unavailable')
    assert result['reviewed']==0 and json.load(open(tmp_path/'unavailable/import-receipt.json'))['unavailable_playback']==1


def test_completed_gameplay_review_requires_explicit_view_and_evidence_and_remains_observation(tmp_path):
    pack,queue,row,write_csv=fixture(tmp_path)
    row.update(playback_status='reviewed',pov_confirmed='yes',xray_disabled='yes',game_build='recorded build',visibility='mixed',
        observed_behavior='aim_correction',assistance_assessment='not_assessable',reviewer='Reviewer',evidence_reference='clip R01',evidence_note='Audio context unclear.')
    path=tmp_path/'annotations.csv';write_csv(path,row);result=import_reviews(pack,queue,path,tmp_path/'observations')
    assert result['reviewed']==1 and not result['training_labels_created'] and result['cheat_activation_ground_truth'] is None
    assert result['observations'][0]['review_source']=='rendered_gameplay'
    assert 'visibility: mixed' in result['observations'][0]['evidence_note']


@pytest.mark.parametrize('bad',['tick','xray','pov','build','reviewer','confirmed','pending_assessment'])
def test_unverified_view_unsupported_claim_or_changed_metadata_fails(tmp_path,bad):
    pack,queue,row,write_csv=fixture(tmp_path)
    row.update(playback_status='reviewed',pov_confirmed='yes',xray_disabled='yes',game_build='build',visibility='visible',
        observed_behavior='tracking',assistance_assessment='suspicious',reviewer='Reviewer',evidence_reference='clip',evidence_note='Observed correction')
    if bad=='tick':row['event_tick']=999
    elif bad=='xray':row['xray_disabled']='no'
    elif bad=='pov':row['pov_confirmed']='no'
    elif bad=='build':row['game_build']=''
    elif bad=='reviewer':row['reviewer']=''
    elif bad=='confirmed':row['assistance_assessment']='confirmed_cheat'
    else:row['playback_status']='pending'
    path=tmp_path/'annotations.csv';write_csv(path,row)
    with pytest.raises(ValueError):import_reviews(pack,queue,path,tmp_path/'output')
    assert not (tmp_path/'output/observations.json').exists()


def test_source_pack_receipts_cannot_be_silently_replaced(tmp_path):
    pack,queue,row,write_csv=fixture(tmp_path);(pack/'selection-private.json').write_text('{}')
    path=tmp_path/'annotations.csv';write_csv(path,row)
    with pytest.raises(ValueError,match='receipt'):import_reviews(pack,queue,path,tmp_path/'output')

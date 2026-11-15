import numpy as np
import pandas as pd
import pytest
from aimguard.target_tracking import damage_recipients, fixed_track, prepare


def sample(tick,player,x,y,yaw=0,team=3,health=100,state=0):
    return dict(tick=tick,steamid=player,X=x,Y=y,yaw=yaw,team_num=team,health=health,life_state=state)


def trajectory(angles, ticks=None):
    ticks=list(range(len(angles))) if ticks is None else ticks
    rows=[]
    for tick,angle in zip(ticks,angles):
        rows.extend([sample(tick,'1',0,0,yaw=angle,team=2),
            sample(tick,'2',10*np.cos(np.deg2rad(angle)),10*np.sin(np.deg2rad(angle)))])
    return prepare(pd.DataFrame(rows))


def test_perfect_horizontal_tracking_has_zero_error_and_matching_rates():
    frame=trajectory([0,1,3,6,10])
    result=fixed_track(frame,'1','2',list(range(5)),[2],64)
    assert result['signed_error_degrees']==pytest.approx([0]*5)
    assert result['yaw_rate_dps'][1:]==pytest.approx([64,128,192,256])
    assert result['bearing_rate_dps'][1:]==pytest.approx([64,128,192,256])
    assert result['full_window']['yaw_bearing_rate_correlation']==pytest.approx(1)
    assert result['full_window']['median_absolute_relative_rate_dps']==pytest.approx(0)


def test_missing_tick_and_missing_opponent_split_derivatives():
    frame=trajectory([0,1,3,4],[0,1,3,4])
    result=fixed_track(frame,'1','2',[0,1,3,4],[3],64)
    assert result['yaw_rate_dps']==[None,64,None,64]
    assert result['segment_ids']==[0,0,1,1]
    frame=frame.loc[~(frame.tick.eq(3)&frame.steamid.eq('2'))]
    result=fixed_track(frame,'1','2',[0,1,3,4],[3],64)
    assert result['segment_ids']==[0,0,-1,1]
    assert result['yaw_rate_dps'][3] is None


def test_wrap_is_shortest_signed_movement_and_stationary_correlation_is_null():
    result=fixed_track(trajectory([179,-179,-178]),'1','2',[0,1,2],[1],64)
    assert result['yaw_rate_dps']==[None,128,64]
    assert result['signed_error_degrees']==pytest.approx([0,0,0])
    result=fixed_track(trajectory([0,0,0,0,0]),'1','2',list(range(5)),[2],64)
    assert result['full_window']['yaw_bearing_rate_correlation'] is None


def test_death_event_latches_even_when_health_and_state_lag():
    result=fixed_track(trajectory([0,1,2,3,4]),'1','2',list(range(5)),[2],64,[('2',2)])
    assert result['segment_ids']==[0,0,-1,-1,-1]
    assert result['signed_error_degrees'][2:]==[None,None,None]
    assert result['full_window']['valid_intervals']==1


def test_team_changes_and_non_alive_samples_break_tracking():
    frame=trajectory([0,1,2,3])
    frame.loc[(frame.tick>=2)&frame.steamid.eq('1'),'team_num']=3
    frame.loc[(frame.tick>=2)&frame.steamid.eq('2'),'team_num']=2
    result=fixed_track(frame,'1','2',[0,1,2,3],[1],64)
    assert result['yaw_rate_dps']==[None,64,None,64]
    frame.loc[frame.tick.eq(1)&frame.steamid.eq('2'),'life_state']=2
    result=fixed_track(frame,'1','2',[0,1,2,3],[1],64)
    assert result['signed_error_degrees'][1] is None


def test_window_damage_association_requires_exact_attacker_weapon_and_segment():
    window=dict(segment_id=1,start_tick=10,end_tick=30,weapon='ak47')
    event=dict(event_type='player_hurt',attacker_steamid='76561199000000001',user_steamid='76561199000000002',
               segment_id=1,tick=20,weapon='weapon_ak47',dmg_health=20)
    events=[event,dict(event,user_steamid='76561199000000003'),dict(event,attacker_steamid='76561199000000000',user_steamid='4'),
        dict(event,weapon='hegrenade',user_steamid='5'),dict(event,segment_id=2,user_steamid='6'),
        dict(event,tick=31,user_steamid='7'),dict(event,dmg_health=0,user_steamid='8')]
    assert damage_recipients(events,window,'76561199000000001')==['76561199000000002','76561199000000003']


def test_fixed_identity_does_not_follow_closer_other_opponent():
    frame=trajectory([0,10,20])
    extra=pd.DataFrame([sample(t,'3',10,0) for t in range(3)])
    frame=prepare(pd.concat([frame,extra]))
    result=fixed_track(frame,'1','2',[0,1,2],[1],64)
    assert result['opponent_id']=='2'
    assert result['signed_error_degrees']==pytest.approx([0,0,0])


def test_duplicate_player_ticks_fail_before_tracking():
    frame=trajectory([0,1])
    with pytest.raises(ValueError,match='Duplicate'):
        prepare(pd.concat([frame,frame.iloc[[0]]]))


def test_near_shot_intervals_need_both_endpoints_inside_radius():
    ticks=list(range(20))
    result=fixed_track(trajectory(ticks),'1','2',ticks,[10],64)
    assert result['near_shot']['valid_samples']==13
    assert result['near_shot']['valid_intervals']==12


def test_csv_roundtrip_uses_source_precision_but_rejects_real_coordinate_change():
    from io import StringIO
    from aimguard.target_tracking import same_shooter_inputs
    actual=trajectory([1]).iloc[[0]].drop(columns=['steamid','tick'])
    actual['X']=np.array([1022.590027],dtype=np.float32)
    expected=pd.read_csv(StringIO(actual.to_csv(index=False)))
    assert same_shooter_inputs(actual,expected)
    expected.loc[0,'X']+=.01
    assert not same_shooter_inputs(actual,expected)


def test_imprecise_float_identifiers_are_rejected():
    frame=trajectory([0])
    frame['steamid']=float(76561199000000001)
    with pytest.raises(ValueError,match='imprecise floats'):
        prepare(frame)

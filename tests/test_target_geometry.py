import numpy as np
import pandas as pd
import pytest
from aimguard.target_geometry import bearing_error, shot_alignment


def row(tick,player,x,y,yaw=0,team=3,health=100,state=0):
    return dict(tick=tick,steamid=player,X=x,Y=y,yaw=yaw,team_num=team,health=health,life_state=state)


def test_bearings_cardinal_directions_and_yaw_wrap():
    assert bearing_error([0,0],0,[10,0])==0
    assert bearing_error([0,0],0,[0,10])==90
    assert bearing_error([0,0],0,[0,-10])==-90
    assert bearing_error([0,0],179,[-10,-.1])==pytest.approx(1.5729387)
    assert bearing_error([0,0],0,[0,0]) is None
    with pytest.raises(ValueError):
        bearing_error([np.nan,0],0,[1,0])


def test_pre_shot_pair_follows_same_opponent_not_nearest_at_each_tick():
    frame=pd.DataFrame([row(10,'s',0,0,team=2),row(4,'s',0,0,team=2),
        row(10,'a',10,0),row(4,'a',0,10),
        row(10,'b',0,10),row(4,'b',10,0)])
    result=shot_alignment(frame,'s',10,4)
    nearest=result['nearest_horizontal_candidate']
    assert nearest['opponent_id']=='a'
    assert nearest['absolute_yaw_error_degrees']==0
    assert nearest['pre_absolute_yaw_error_degrees']==90
    assert nearest['error_reduction_degrees']==90


def test_dead_teammates_nonfinite_and_colocated_players_are_excluded():
    frame=pd.DataFrame([row(10,'s',0,0,team=2),row(10,'mate',10,0,team=2),
        row(10,'dead',10,0,state=2),row(10,'zero_health',10,0,health=0),
        row(10,'invalid',np.inf,0),row(10,'same_place',0,0),row(10,'valid',10,10)])
    result=shot_alignment(frame,'s',10,4)
    assert [r['opponent_id'] for r in result['candidates']]==['valid']
    assert result['nearest_horizontal_candidate']['pre_status']=='missing_pair'


def test_missing_exact_tick_is_not_interpolated():
    frame=pd.DataFrame([row(9,'s',0,0,team=2),row(9,'a',10,0)])
    result=shot_alignment(frame,'s',10,4)
    assert result['status']=='unavailable'
    assert result['reason']=='missing_shooter'


def test_duplicate_identity_and_team_switch_are_not_silently_accepted():
    base=[row(10,'s',0,0,team=2),row(10,'a',10,0),row(4,'s',0,0,team=3),row(4,'a',10,0)]
    result=shot_alignment(pd.DataFrame(base),'s',10,4)
    assert result['nearest_horizontal_candidate']['pre_status']=='invalid_pair'
    with pytest.raises(ValueError,match='duplicate'):
        shot_alignment(pd.DataFrame(base+[base[0]]),'s',10,4)

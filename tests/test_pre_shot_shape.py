import numpy as np
import pandas as pd
import pytest
from aimguard.pre_shot_shape import window_shape, case_shape


def frame(yaw=None,pitch=None):
    return pd.DataFrame(dict(tick=range(50),yaw=np.arange(50,dtype=float) if yaw is None else yaw,
        pitch=np.zeros(50) if pitch is None else pitch,active=True,segment_id=0,life_state=0,health=100,team_num=2)).set_index('tick')


def window():return dict(engagement_id=0,shot_ticks=[40],start_tick=0,segment_id=0)


def test_straight_two_axis_motion_has_unit_efficiency_and_constant_speed():
    result,reason=window_shape(frame(pitch=np.arange(50)*.2),window(),64)
    assert reason is None and result['start_tick']==8 and result['end_tick']==39 and result['valid_intervals']==31
    assert result['features']==pytest.approx([1,0,0,0],abs=1e-7)


def test_shape_detects_direction_changes_without_needing_opponents():
    result,_=window_shape(frame(yaw=np.arange(50)%2),window(),64)
    assert result['features'][0]==pytest.approx(1/31)
    assert result['features'][1]==pytest.approx(np.pi)


def test_stationary_legitimate_preaim_is_retained_without_invented_motion():
    result,reason=window_shape(frame(yaw=np.zeros(50)),window(),64)
    assert reason is None and result['features']==[0.,0.,0.,1.]


def test_post_shot_and_earlier_out_of_period_changes_cannot_affect_shape():
    telemetry=frame();before,_=window_shape(telemetry,window(),64)
    telemetry.loc[40:,['yaw','pitch']]=[100,-80]
    telemetry.loc[:7,['yaw','pitch']]=[-100,80]
    after,_=window_shape(telemetry,window(),64)
    assert before==after


def test_yaw_wrap_uses_shortest_steps_and_pitch_stays_unwrapped():
    yaw=((np.arange(50)+170+180)%360)-180
    result,_=window_shape(frame(yaw=yaw),window(),64)
    reference,_=window_shape(frame(),window(),64)
    assert result['features']==pytest.approx(reference['features'])


def test_missing_exact_endpoint_gap_and_inactive_samples_are_not_interpolated():
    result,reason=window_shape(frame().drop(39),window(),64)
    assert result is None and reason=='invalid_exact_pre_shot_endpoint'
    for column,value in [('active',False),('segment_id',1),('life_state',2),('health',0),('pitch',91)]:
        telemetry=frame();telemetry.loc[30,column]=value
        result,reason=window_shape(telemetry,window(),64)
        assert result is None and reason=='insufficient_contiguous_pre_shot_intervals'


def test_case_coverage_keeps_exclusions_and_abstains_under_five_windows():
    windows=[window()]*4;values,coverage=case_shape(frame(),windows,64)
    assert values is None and coverage['eligible_windows']==4
    values,coverage=case_shape(frame(),windows+[dict(window(),shot_ticks=[10])],64)
    assert values is None and coverage['excluded_windows']=={'insufficient_contiguous_pre_shot_intervals':1}
    values,coverage=case_shape(frame(),windows+[window()],64)
    assert values==pytest.approx([1,0,0,0],abs=1e-7) and coverage['eligible_windows']==5


def test_invalid_tickrate_and_duplicate_ticks_fail():
    with pytest.raises(ValueError,match='tickrate'):window_shape(frame(),window(),0)
    duplicate=pd.concat([frame(),frame().iloc[[0]]])
    with pytest.raises(ValueError,match='Duplicate'):window_shape(duplicate,window(),64)

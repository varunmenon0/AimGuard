import copy
import numpy as np
import pandas as pd
import pytest
from aimguard.combat import movement_context
from aimguard.shot_motion_audit import window_motion


def data():
    frame=pd.DataFrame(dict(tick=np.arange(80,121),yaw=np.linspace(0,20,41),pitch=np.zeros(41)))
    w=dict(engagement_id=0,shot_ticks=[100,105],movement_context=movement_context(frame,[100,105],64,.1))
    return frame,w


def test_pre_first_support_excludes_shot_and_post_shot_changes():
    frame,w=data();original=copy.deepcopy(w);a=window_motion(frame,w,64)
    frame.loc[frame.tick>=100,'pitch']=50*np.sin(frame.loc[frame.tick>=100,'tick'])
    w['movement_context']=movement_context(frame,w['shot_ticks'],64,.1);b=window_motion(frame,w,64)
    assert a['pre_first_features']==b['pre_first_features']
    assert a['original_features']!=b['original_features']
    assert original['shot_ticks']==w['shot_ticks']
    assert a['near_speed_at_or_after_first']>0 and a['near_acceleration_at_or_after_first']>0


def test_every_pre_derivative_support_sample_is_before_shot_and_inside_radius():
    frame,w=data();r=window_motion(frame,w,64)
    # At64Hz, integer sample support inside[93.6,100) is94..99: five speeds,four accelerations.
    assert r['pre_speed_intervals']==5 and r['pre_acceleration_samples']==4
    frame=frame.loc[frame.tick>=100];w['movement_context']=movement_context(frame,w['shot_ticks'],64,.1)
    r=window_motion(frame,w,64)
    assert r['pre_first_features']==[None,None]


def test_changed_source_features_or_invalid_ticks_rejected():
    frame,w=data();w['movement_context']['near_shot']['p95_speed']=999
    with pytest.raises(ValueError,match='reproduce'):window_motion(frame,w,64)
    frame,w=data();frame.loc[1,'tick']=frame.loc[0,'tick']
    with pytest.raises(ValueError):window_motion(frame,w,64)

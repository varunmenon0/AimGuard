import numpy as np
import pandas as pd
import pytest

from aimguard.final_error_audit import movement
from aimguard.two_tick_development import group_vector


def frame(held=False,wrapped=False):
    ticks=np.arange(65)
    yaw=(ticks//2*2 if held else ticks)*12/64
    if wrapped:yaw=(yaw+179+180)%360-180
    return pd.DataFrame(dict(tick=ticks,yaw=yaw,pitch=np.zeros(len(ticks))))


def test_two_tick_motion_preserves_units_and_wraps_without_artificial_acceleration():
    for wrapped in (False,True):
        result=movement(frame(wrapped=wrapped),dict(shot_ticks=[32]),64)
        assert result['two_tick_features'][0]==pytest.approx(12)
        assert result['two_tick_features'][1]==pytest.approx(0,abs=1e-8)


def test_held_alternating_samples_are_described_without_interpolation():
    result=movement(frame(held=True),dict(shot_ticks=[32]),64)
    assert .4<result['held_fraction']<.6 and result['alternation_fraction']==1
    assert result['two_tick_features']==pytest.approx([12,0],abs=1e-8)


def test_motion_cannot_smooth_over_a_missing_tick():
    with pytest.raises(ValueError,match='Nonconsecutive'):
        movement(frame().drop(index=30),dict(shot_ticks=[32]),64)


def test_named_groups_preserve_shared_members_and_reject_bad_partitions():
    assert group_vector({'0':['A','B'],'new-N-001':['C']},['C','A','B'])==['new-N-001','0','0']
    with pytest.raises(ValueError,match='Duplicate'):
        group_vector({'0':['A'],'new-N-001':['A']},['A'])
    with pytest.raises(ValueError,match='partition'):
        group_vector({'0':['A']},['A','B'])

import numpy as np
import pandas as pd
import pytest
from aimguard.recoil_event_audit import shot_dynamics


def frame():
    return pd.DataFrame(dict(tick=[98,99,100,101,102],yaw=[0]*5,pitch=[0,-1,-2,-3,-4],
        aim_punch_angle=[[i,0,0] for i in range(5)],shots_fired=[0,0,1,1,1],active_weapon_name=['weapon_ak47']*5))


def test_known_opposed_components_and_event_counter_alignment():
    r=shot_dynamics(frame(),100,'ak47')
    assert r['status']=='available' and r['positive_counter_offsets']==[0]
    assert r['recorded_component_cosines']==pytest.approx([-1]*4)
    f=frame();f['shots_fired']=[0,0,0,1,1]
    assert shot_dynamics(f,100,'ak47')['positive_counter_offsets']==[1]


def test_missing_or_switched_support_is_unavailable_not_zero():
    f=frame().drop(index=0)
    assert shot_dynamics(f,100,'ak47')['status']=='unavailable'
    f=frame();f.loc[2,'active_weapon_name']='awp'
    assert shot_dynamics(f,100,'ak47')['reason']=='weapon_changed_or_mismatched'
    f=frame();f.at[2,'aim_punch_angle']=[np.nan,0,0]
    assert shot_dynamics(f,100,'ak47')['reason']=='invalid_numeric_fields'


def test_stationary_components_have_undefined_cosine_and_resets_are_retained():
    f=frame();f['pitch']=0;f['shots_fired']=[2,2,0,1,1]
    r=shot_dynamics(f,100,'ak47')
    assert r['recorded_component_cosines']==[None]*4 and r['counter_reset']
    assert r['positive_counter_offsets']==[1]


def test_wrap_and_duplicate_identity_handling():
    f=frame();f['yaw']=[179,-179,-177,-175,-173]
    r=shot_dynamics(f,100,'ak47');assert r['view_step_magnitudes']==pytest.approx([np.sqrt(5)]*4)
    f.loc[1,'tick']=98
    with pytest.raises(ValueError):shot_dynamics(f,100,'ak47')


def test_parser_display_names_match_event_identifiers_without_merging_distinct_guns():
    from aimguard.recoil_event_audit import weapon_id
    assert weapon_id('M4A4')=='m4a1' and weapon_id('M4A1-S')=='m4a1_silencer'
    f=frame();f['active_weapon_name']='AK-47'
    assert shot_dynamics(f,100,'ak47')['status']=='available'
    f['active_weapon_name']='M4A1-S'
    assert shot_dynamics(f,100,'m4a1')['status']=='unavailable'

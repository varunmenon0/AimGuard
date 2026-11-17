import numpy as np
import pandas as pd
import pytest
from aimguard.burst_recoil import burst_groups,burst_features,aggregate


def sample():
    ticks=np.arange(3,19);p=np.linspace(0,3,len(ticks))
    return pd.DataFrame(dict(tick=ticks,pitch=-2*p,yaw=np.zeros(len(ticks)),aim_punch_angle=[[v,0,0] for v in p],shots_fired=[1]*len(ticks),active_weapon_name=['AK-47']*len(ticks))),dict(shot_ticks=[4,10,16],weapon='ak47',segment_id=0)


def test_known_projection_gain_and_orthogonal_motion():
    f,b=sample();r,reason=burst_features(f,b)
    assert reason is None and r['features']==pytest.approx([2,0,-1],abs=1e-12)
    f['yaw']=f['pitch'];f['pitch']=0
    r,_=burst_features(f,b);assert r['features']==pytest.approx([0,1,0])


def test_gaps_weapon_changes_and_constant_punch_do_not_create_clean_evidence():
    f,b=sample();assert burst_features(f.drop(index=3),b)[1]=='missing_exact_support'
    f.loc[4,'active_weapon_name']='AWP';assert burst_features(f,b)[1]=='weapon_changed_or_mismatched'
    f,b=sample();f['aim_punch_angle']=[[0,0,0] for _ in range(len(f))]
    assert burst_features(f,b)[1]=='insufficient_view_or_punch_variation'


def test_fixed_grouping_preserves_weapon_segment_and_requires_three_shots():
    windows=[dict(shot_ticks=[10,16,22,60,66],weapon='ak47',segment_id=1),dict(shot_ticks=[70,76,82],weapon='mp9',segment_id=2)]
    g=burst_groups(windows,64);assert len(g)==2
    assert g[0]['shot_ticks']==[10,16,22] and g[1]['weapon']=='mp9' and g[1]['segment_id']==2
    with pytest.raises(ValueError):burst_groups(windows,0)


def test_five_valid_bursts_required_without_zero_imputation():
    assert aggregate([None]*5) is None
    assert aggregate([dict(features=[1,2,3])]*4+[None]) is None
    assert aggregate([dict(features=[1,2,3])]*5+[dict(features=[9,10,11])])==[1,2,3]

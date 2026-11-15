import copy
import numpy as np
import pytest
from aimguard.acquisition_dynamics import window_dynamics,case_dynamics


def window(errors,yaw_steps=None,bearing_steps=None):
    n=len(errors);yaw_steps=np.array(yaw_steps if yaw_steps is not None else -np.diff(errors))
    bearing_steps=np.array(bearing_steps if bearing_steps is not None else np.zeros(n-1))
    return dict(shot_ticks=[n],nearest_before_first_shot='a',tracks=[dict(opponent_id='a',ticks=list(range(n+5)),
        segment_ids=[0]*(n+5),signed_error_degrees=list(errors)+[0]*5,
        yaw_rate_dps=[None,*list(yaw_steps*64),*([0]*5)],bearing_rate_dps=[None,*list(bearing_steps*64),*([0]*5)])])


def test_abrupt_closure_has_higher_concentration_than_smooth_acquisition():
    abrupt,_=window_dynamics(window([12.]*10+[0.]*22),64)
    smooth,_=window_dynamics(window(np.linspace(12,0,32)),64)
    assert abrupt['is_transition'] and smooth['is_transition']
    assert abrupt['concentration']==1
    assert smooth['concentration']==pytest.approx(1/31)
    assert abrupt['settling_speed_ratio']==0


def test_opponent_motion_alone_does_not_create_player_supported_transition():
    error=np.linspace(12,0,32)
    result,_=window_dynamics(window(error,yaw_steps=np.zeros(31),bearing_steps=np.diff(error)),64)
    assert not result['is_transition'] and result['player_supported_closure_degrees']==pytest.approx(0,abs=1e-10)
    assert result['concentration'] is None


def test_already_aligned_stationary_aim_is_not_a_snap():
    result,_=window_dynamics(window([.1]*32),64)
    assert not result['is_transition'] and result['settling_speed_ratio'] is None


def test_late_acquisition_does_not_impute_missing_settling_as_zero():
    result,_=window_dynamics(window([12.]*31+[0.]),64)
    assert result['is_transition'] and result['concentration']==1
    assert result['settling_speed_ratio'] is None
    assert result['unavailable_reason']=='insufficient_post_peak_pre_shot_intervals'


def test_missing_or_interrupted_pre_shot_coverage_is_explicit():
    value=window([12.]*10+[0.]*22);value['tracks'][0]['segment_ids'][20:]=[1]*17
    assert window_dynamics(value,64)[1]=='insufficient_contiguous_pre_shot_intervals'
    value=window([12.]*10+[0.]*22);value['tracks'][0]['ticks'][31]=31.5
    with pytest.raises(ValueError,match='integers'):window_dynamics(value,64)


def test_post_shot_values_and_other_opponents_do_not_change_dynamics():
    value=window([12.]*10+[0.]*22);expected,_=window_dynamics(value,64)
    other=copy.deepcopy(value['tracks'][0]);other['opponent_id']='b';value['tracks'].append(other)
    for key in ('signed_error_degrees','yaw_rate_dps','bearing_rate_dps'):value['tracks'][0][key][32:]=[None]*5
    assert window_dynamics(value,64)[0]==expected


def test_case_coverage_requires_observed_transitions_not_just_precise_windows():
    static=window([.1]*32);snap=window([12.]*10+[0.]*22)
    assert case_dynamics([static]*10,64)[0] is None
    assert case_dynamics([snap]*2+[static]*3,64)[0] is None
    values,counts=case_dynamics([snap]*3+[static]*2,64)
    assert values==[.6,1.,0.] and counts['usable_transitions']==3


def test_yaw_wrap_does_not_create_a_large_closure():
    result,_=window_dynamics(window([179.]*16+[-179.]*16,yaw_steps=[0.]*15+[-2.]+[0.]*15),64)
    assert not result['is_transition'] and result['net_error_reduction_degrees']==0


def test_wrong_baseline_protocol_is_rejected_before_output_or_fit(tmp_path,monkeypatch):
    import json
    import aimguard.acquisition_dynamics as module
    from aimguard.baseline import digest
    pool=tmp_path/'pool';base=tmp_path/'baseline';pool.mkdir();base.mkdir()
    (pool/'manifest.json').write_text(json.dumps(dict(role='development',features_inspected=True,cases=[])))
    manifest_hash=digest(pool/'manifest.json')
    (pool/'pool-receipt.json').write_text(json.dumps(dict(manifest_sha256=manifest_hash,groups={})))
    (base/'protocol.json').write_text(json.dumps(dict(manifest_sha256=manifest_hash,threshold=.4,hyperparameters={})))
    (base/'inputs.json').write_text(json.dumps(dict(groups={})))
    (base/'comparison.json').write_text(json.dumps(dict(protocol_sha256=digest(base/'protocol.json'),inputs_sha256=digest(base/'inputs.json'))))
    monkeypatch.setattr(module,'with_abstentions',lambda *a:pytest.fail('Must not fit changed protocol'))
    output=tmp_path/'comparison'
    with pytest.raises(ValueError,match='classifier protocol differs'):module.compare(pool,base,output)
    assert not output.exists()

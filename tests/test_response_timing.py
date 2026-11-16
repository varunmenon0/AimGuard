import copy
import json
import numpy as np
import pytest
from aimguard.response_timing import window_response,case_response,compare


def window(delay=0):
    ticks=np.arange(90);bearing=np.random.default_rng(3).normal(0,30,len(ticks));yaw=np.roll(bearing,delay)
    track=dict(opponent_id='2',ticks=ticks.tolist(),segment_ids=[0]*len(ticks),yaw_rate_dps=yaw.tolist(),bearing_rate_dps=bearing.tolist())
    return dict(shot_ticks=[64],nearest_before_first_shot='2',tracks=[track])


def test_known_immediate_and_delayed_signals_have_correct_lag_direction():
    immediate,reason=window_response(window(),64)
    assert reason is None and immediate['correlations'][0]==pytest.approx(1)
    assert immediate['features'][1]>0
    delayed,reason=window_response(window(6),64)
    assert delayed['correlations'][1]==pytest.approx(1)
    assert delayed['features'][1]<0 and delayed['lag_ticks']==6
    leading,_=window_response(window(-6),64)
    assert leading['correlations'][2]==pytest.approx(1)
    assert leading['features'][2]<0


def test_only_pre_shot_samples_used_and_no_input_mutation():
    w=window();original=copy.deepcopy(w);a,_=window_response(w,64)
    assert w==original and a['last_support_tick']==63
    for key in ('yaw_rate_dps','bearing_rate_dps'):
        w['tracks'][0][key][64:]=[float('nan')]*26
    assert window_response(w,64)[0]==a


def test_constant_angles_missing_candidate_and_gaps_are_not_zero_evidence():
    w=window();w['tracks'][0]['bearing_rate_dps']=[10]*90
    assert window_response(w,64)==(None,'insufficient_angular_rate_variation')
    w=window();w['nearest_before_first_shot']=None
    assert window_response(w,64)[0] is None
    w=window();w['tracks'][0]['segment_ids'][63]=-1
    assert window_response(w,64)[0] is None
    w=window();w['tracks'][0]['yaw_rate_dps'][60]=None
    assert window_response(w,64)==(None,'insufficient_common_pre_shot_support')


def test_five_window_coverage_and_componentwise_medians():
    ws=[window(0),window(0),window(6),window(-6),window(6)]
    values,coverage=case_response(ws,64)
    assert coverage['eligible_windows']==5
    assert np.allclose(values,np.median([window_response(w,64)[0]['features'] for w in ws],axis=0))
    assert case_response(ws[:4],64)[0] is None


def test_invalid_support_and_source_receipts_rejected(tmp_path):
    w=window();w['tracks'][0]['ticks'][30]=29
    with pytest.raises(ValueError):window_response(w,64)
    with pytest.raises(ValueError):window_response(window(),0)
    for name,value in [('comparison.json',{'protocol_sha256':'wrong'}),('protocol.json',{}),('inputs.json',{})]:
        (tmp_path/name).write_text(json.dumps(value))
    with pytest.raises(ValueError,match='receipt'):compare(tmp_path,tmp_path/'out')
    assert not (tmp_path/'out').exists()

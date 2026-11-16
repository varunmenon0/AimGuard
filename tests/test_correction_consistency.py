import numpy as np
import pytest
from aimguard.correction_consistency import correction_fit, case_feedback


def window(gain=8., tickrate=64, shooter_moves=True, shot=40):
    ticks = np.arange(shot)
    error = 20.*(1-gain/tickrate)**ticks
    relative = np.r_[0., -np.diff(error)*tickrate]
    yaw = relative if shooter_moves else np.zeros(shot)
    bearing = yaw-relative
    return dict(nearest_before_first_shot='a', shot_ticks=[shot], tracks=[dict(opponent_id='a',
        ticks=ticks.tolist(), segment_ids=[0]*shot, signed_error_degrees=error.tolist(),
        yaw_rate_dps=yaw.tolist(), bearing_rate_dps=bearing.tolist())])


def test_proportional_correction_recovers_known_gain_and_fit_without_post_shot_samples():
    w = window(); result, reason = correction_fit(w, 64)
    assert reason is None and result['positive_fit']
    assert result['gain'] == pytest.approx(8.)
    assert result['r_squared'] == pytest.approx(1.)
    assert result['end_tick']==39 and result['start_tick']>=8
    # Changes after the exact pre-shot endpoint cannot influence measurements.
    track = w['tracks'][0]
    for key in ('ticks', 'segment_ids', 'signed_error_degrees', 'yaw_rate_dps', 'bearing_rate_dps'):
        track[key].extend([40, 41] if key=='ticks' else [999, 999])
    after, _ = correction_fit(w, 64)
    assert after == result


def test_opponent_only_closure_and_static_precision_do_not_create_positive_fits():
    result, _ = correction_fit(window(shooter_moves=False), 64)
    assert result['player_supported_closure_degrees'] < 1e-10
    assert not result['qualifying_transition'] and not result['positive_fit']
    w = window(); track=w['tracks'][0]
    track['signed_error_degrees']=[.1]*40
    track['yaw_rate_dps']=[0]*40; track['bearing_rate_dps']=[0]*40
    result, _ = correction_fit(w, 64)
    assert not result['positive_fit']


def test_gain_consistency_is_across_windows_not_number_of_samples_or_labels():
    values, coverage = case_feedback([window() for _ in range(5)], 64)
    assert values == pytest.approx([1., 0., 1.])
    assert coverage['usable_transitions']==5
    varied, _ = case_feedback([window(gain=k) for k in (5, 6, 7, 8, 9)], 64)
    assert varied[1] > values[1]


def test_few_transitions_abstain_instead_of_treating_unavailable_fits_as_legitimate():
    values, counts = case_feedback([window()]*2+[window(shooter_moves=False)]*4, 64)
    assert values is None and counts['usable_transitions']==2 and counts['valid_windows']==6
    values, counts = case_feedback([window()]*4, 64)
    assert values is None and counts['valid_windows']==4


def test_missing_endpoint_and_segment_gap_cannot_be_interpolated():
    w=window(); w['tracks'][0]['ticks'][-1]=40
    result, reason=correction_fit(w, 64)
    assert result is None and reason=='missing_exact_pre_shot_endpoint'
    w=window(); w['tracks'][0]['segment_ids'][-6:]=[1]*6
    result, reason=correction_fit(w, 64)
    assert result is None and reason=='insufficient_contiguous_pre_shot_intervals'


def test_signed_error_wrap_is_not_a_correction_event():
    w=window(); w['tracks'][0]['signed_error_degrees'][-3:]=[179, -179, -178]
    result, reason=correction_fit(w, 64)
    assert result is None and reason=='horizontal_error_branch_crossing'


def test_constant_closing_velocity_has_unavailable_fit_not_perfect_r_squared():
    w=window(); track=w['tracks'][0]
    track['signed_error_degrees']=np.linspace(30, 1, 40).tolist()
    track['yaw_rate_dps']=[29/39*64]*40; track['bearing_rate_dps']=[0]*40
    result, reason=correction_fit(w, 64)
    assert reason is None and result['qualifying_transition']
    assert result['gain'] is None and result['unavailable_reason']=='insufficient_error_or_response_variation'


def test_tickrate_and_alignment_errors_fail_explicitly():
    with pytest.raises(ValueError, match='tickrate'): correction_fit(window(), 0)
    w=window(); w['tracks'][0]['yaw_rate_dps'].pop()
    with pytest.raises(ValueError, match='Misaligned'): correction_fit(w, 64)

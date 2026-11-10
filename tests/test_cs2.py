import numpy as np
import pandas as pd
import pytest
from aimguard.cs2 import normalize_ticks, window_features


def sample():
    ticks = np.arange(200)
    return pd.DataFrame({'tick': ticks, 'steamid': ['123'] * 200,
                         'yaw': (170 + ticks * .5 + 180) % 360 - 180,
                         'pitch': np.sin(ticks / 10)})


def test_normalize():
    out = normalize_ticks(sample(), '123', 64)
    assert len(out) == 200
    assert out['time_s'].iloc[0] == 0


def test_features_are_finite():
    out = window_features(normalize_ticks(sample(), '123', 64), 64)
    assert len(out) > 0
    assert all(np.isfinite(v) for row in out for k, v in row.items() if k not in ('start_tick', 'end_tick', 'samples'))


def test_unknown_player():
    with pytest.raises(ValueError, match='No ticks'):
        normalize_ticks(sample(), 'missing', 64)


def test_duplicate_ticks():
    frame = pd.concat([sample(), sample().iloc[[0]]], ignore_index=True)
    assert len(normalize_ticks(frame, '123', 64)) == 200


def test_duplicate_resolution_preserves_original_observation_order():
    rng = np.random.default_rng(0)
    frame = pd.DataFrame({'tick': rng.integers(0, 10, 100), 'steamid': '123',
                          'yaw': np.arange(100), 'pitch': 0})
    expected = frame.drop_duplicates('tick', keep='last').sort_values('tick')['yaw'].to_numpy()
    assert np.array_equal(normalize_ticks(frame, '123', 64)['yaw'], expected)


def test_window_boundary_jump_is_not_lost():
    frame = pd.DataFrame({'tick': np.arange(256), 'steamid': '123',
                          'yaw': np.r_[np.zeros(128), np.full(128, 90)], 'pitch': 0})
    windows = window_features(normalize_ticks(frame, '123', 64), 64)
    assert windows[0]['mean_speed'] == 0
    assert windows[1]['mean_speed'] > 0
    assert windows[1]['start_tick'] == 127


def test_window_alignment_uses_absolute_ticks_across_slices():
    frame = normalize_ticks(sample(), '123', 64)
    full = window_features(frame, 64)
    sliced = window_features(frame.iloc[1:], 64)
    assert full[1] == sliced[1]


@pytest.mark.parametrize('rate', [0, -1, np.nan, np.inf])
def test_reject_invalid_tickrate(rate):
    with pytest.raises(ValueError, match='finite and positive'):
        normalize_ticks(sample(), '123', rate)
    with pytest.raises(ValueError, match='finite and positive'):
        window_features(sample(), rate)

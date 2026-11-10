"""Tests for gap-aware CS2 view-angle diagnostics."""
import numpy as np
import pandas as pd
from aimguard.cs2 import trajectory_diagnostics


def make_player(ticks, yaw, pitch=None):
    if pitch is None:
        pitch = [0] * len(ticks)
    return pd.DataFrame({'tick': ticks, 'yaw': yaw, 'pitch': pitch,
                         'time_s': (np.asarray(ticks) - ticks[0]) / 64})


def test_yaw_wrap_is_short_rotation():
    out, stats = trajectory_diagnostics(make_player([0, 1, 2], [178, 179, -179]), 64)
    assert np.allclose(out['yaw_unwrapped'], [178, 179, 181])
    assert np.isclose(out['yaw_velocity_dps'].iloc[2], 128)
    assert stats['recording_gaps'] == 0


def test_actual_tick_spacing_controls_velocity():
    out, stats = trajectory_diagnostics(make_player([0, 2, 4], [0, 2, 4]), 64)
    assert np.isclose(out['yaw_velocity_dps'].iloc[1], 64)
    assert stats['median_tick_spacing'] == 2
    assert stats['estimated_missing_ticks'] == 2


def test_gaps_are_not_connected():
    out, stats = trajectory_diagnostics(make_player([0, 1, 100, 101], [179, -179, -100, -99]), 64)
    assert stats['recording_gaps'] == 1
    assert stats['segments'] == 2
    assert np.isnan(out['angular_speed_dps'].iloc[2])
    assert np.isclose(out['yaw_unwrapped'].iloc[2], -100)


def test_pitch_contributes_to_speed():
    out, _ = trajectory_diagnostics(make_player([0, 1], [0, 0], [0, 3]), 64)
    assert np.isclose(out['angular_speed_dps'].iloc[1], 192)

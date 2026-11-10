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

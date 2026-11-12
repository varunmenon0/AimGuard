import json

import numpy as np
import pandas as pd
import pytest

from aimguard.combat import movement_context, selected_fire
from aimguard.gameplay import extract_engagements, segment_gameplay
from test_gameplay import telemetry, events


def test_firearms_filter_unknown_and_non_firearms_before_grouping():
    context = events(shots=(60, 65, 70, 75, 80), deaths=())
    context['weapon_fire']['weapon'] = ['weapon_knife', 'weapon_ak47', 'weapon_flashbang', None, 'weapon_ak47']
    player, matched, _ = segment_gameplay(telemetry(), context, '123')
    windows, _ = extract_engagements(player, matched)
    assert [w['shot_ticks'] for w in windows] == [[65, 80]]
    assert windows[0]['weapon'] == 'ak47'
    legacy, _ = extract_engagements(player, matched, weapon_mode='all')
    assert sum(w['shot_count'] for w in legacy) == 5
    assert selected_fire(matched.drop(columns='weapon'), 'firearms').sum() == 0
    with pytest.raises(ValueError, match='weapon_mode'):
        extract_engagements(player, matched, weapon_mode='invalid')


def test_weapon_switch_splits_nearby_shots():
    context = events(shots=(60, 65, 70), deaths=())
    context['weapon_fire']['weapon'] = ['weapon_ak47', 'weapon_deagle', 'weapon_ak47']
    player, matched, _ = segment_gameplay(telemetry(), context, '123')
    windows, _ = extract_engagements(player, matched)
    assert [w['weapon'] for w in windows] == ['ak47', 'deagle', 'ak47']
    assert [w['shot_ticks'] for w in windows] == [[60], [65], [70]]


def test_disjoint_near_shot_regions_do_not_create_derivatives():
    speeds = np.array([1., 2., 50., 100., 300., 200., 100., 10., 12., 14., 100.])
    frame = pd.DataFrame({'tick': np.arange(12), 'yaw': np.r_[0, np.cumsum(speeds / 10)], 'pitch': 0.})
    result = movement_context(frame, [1, 9], 10, .11)
    near = result['near_shot']
    assert near['speed_intervals'] == 5
    assert near['acceleration_samples'] == 3
    assert near['jerk_samples'] == 1
    assert near['mean_accel'] == pytest.approx(np.mean([10, 20, 20]))
    assert near['p95_jerk'] == pytest.approx(0, abs=1e-8)
    assert near['mean_speed'] == pytest.approx(np.mean([1, 2, 10, 12, 14]))
    assert sum(v['covered_seconds'] for v in result.values()) == pytest.approx(1.1)
    assert sum(v['speed_intervals'] for v in result.values()) == 11


def test_empty_category_exports_null_instead_of_zero():
    frame = pd.DataFrame({'tick': np.arange(8), 'yaw': np.arange(8), 'pitch': 0.})
    result = movement_context(frame, [3], 64, 10)
    assert result['surrounding']['speed_intervals'] == 0
    assert result['surrounding']['p95_speed'] is None
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('radius', [0, -1, np.nan, np.inf])
def test_invalid_proximity_rejected(radius):
    player, matched, _ = segment_gameplay(telemetry(), events(), '123')
    with pytest.raises(ValueError, match='near_shot_s'):
        extract_engagements(player, matched, near_shot_s=radius)

"""Gameplay boundaries are safety properties of extraction, not classifier tests."""
import numpy as np
import pandas as pd
import pytest

from aimguard.gameplay import (
    extract_engagements, main, match_player_events, round_intervals, segment_gameplay,
)


def telemetry(n=256):
    tick = np.arange(n)
    return pd.DataFrame({'tick': tick, 'steamid': '123', 'yaw': tick * 0.2,
                         'pitch': np.sin(tick / 20), 'health': 100,
                         'life_state': 0, 'team_num': 2})


def events(shots=(60, 70, 140, 170, 190, 240), deaths=(150,)):
    return {
        'round_start': pd.DataFrame({'tick': [0]}),
        'round_freeze_end': pd.DataFrame({'tick': [10]}),
        'round_end': pd.DataFrame({'tick': [245]}),
        'weapon_fire': pd.DataFrame({'tick': list(shots), 'user_steamid': ['123'] * len(shots)}),
        'player_death': pd.DataFrame({'tick': list(deaths), 'user_steamid': ['123'] * len(deaths),
                                      'attacker_steamid': ['456'] * len(deaths)}),
        'player_hurt': pd.DataFrame({'tick': [65, 75, 80], 'user_steamid': ['456', '123', '789'],
                                     'attacker_steamid': ['123', '456', '456']}),
    }


def test_shot_windows_stay_inside_round_and_life():
    frame = telemetry()
    frame.loc[150:179, ['health', 'life_state']] = [0, 2]
    player, matched, report = segment_gameplay(frame, events(), '123')
    windows, skipped = extract_engagements(player, matched)
    assert not skipped
    assert report['segments'] == 2
    assert report['matched_event_counts'] == {'weapon_fire': 6, 'player_hurt': 2, 'player_death': 1}
    assert report['events_outside_active_segments']['weapon_fire'] == 1
    assert [w['shot_ticks'] for w in windows] == [[60, 70], [140], [190], [240]]
    assert windows[0]['damage_dealt_events'] == 1
    assert windows[0]['damage_taken_events'] == 1
    for window in windows:
        trajectory = player.loc[player['tick'].between(window['start_tick'], window['end_tick'])]
        assert trajectory['active'].all()
        assert trajectory['segment_id'].nunique() == 1
        assert trajectory['round_id'].nunique() == 1
        assert not (window['start_tick'] <= 150 <= window['end_tick'])
        assert window['start_tick'] >= 10
        assert window['end_tick'] < 245
        assert all(np.isfinite(v) for v in window['features'].values())


def test_death_event_blocks_lagging_alive_telemetry_until_observed_respawn():
    frame = telemetry()
    frame.loc[155:179, ['health', 'life_state']] = [0, 2]
    player, _, _ = segment_gameplay(frame, events(), '123')
    assert player.loc[149, 'active']
    assert not player.loc[150:179, 'active'].any()
    assert player.loc[180, 'active']
    assert player.loc[180, 'segment_id'] != player.loc[149, 'segment_id']


def test_death_between_recorded_samples_is_still_a_boundary():
    frame = telemetry().drop(index=150)
    player, _, _ = segment_gameplay(frame, events(), '123')
    # Without an observed dead state, remain conservative until the next round.
    assert not player.loc[player['tick'].ge(151), 'active'].any()


@pytest.mark.parametrize('column,value', [('yaw', np.nan), ('pitch', np.inf), ('health', np.nan),
                                         ('life_state', np.nan), ('life_state', np.inf),
                                         ('team_num', np.nan), ('pitch', 91)])
def test_invalid_samples_are_boundaries_not_dropped_and_joined(column, value):
    frame = telemetry().astype({column: float})
    frame.loc[90, column] = value
    player, matched, _ = segment_gameplay(frame, events(shots=(80, 100), deaths=()), '123')
    assert not player.loc[90, 'active']
    assert player.loc[89, 'segment_id'] != player.loc[91, 'segment_id']
    windows, _ = extract_engagements(player, matched)
    assert len(windows) == 2
    assert all(not (w['start_tick'] <= 90 <= w['end_tick']) for w in windows)


def test_round_boundary_splits_nearby_shots_even_if_health_stays_positive():
    context = events(shots=(120, 132), deaths=())
    context['round_start'] = pd.DataFrame({'tick': [0, 128]})
    context['round_freeze_end'] = pd.DataFrame({'tick': [10, 130]})
    context['round_end'] = pd.DataFrame({'tick': [127, 245]})
    player, matched, _ = segment_gameplay(telemetry(), context, '123')
    windows, _ = extract_engagements(player, matched)
    assert [w['shot_ticks'] for w in windows] == [[120], [132]]
    assert windows[0]['end_tick'] < 127
    assert windows[1]['start_tick'] >= 130


def test_long_recording_gap_splits_shot_windows():
    frame = telemetry().drop(index=range(90, 130))
    player, matched, report = segment_gameplay(frame, events(shots=(80, 140), deaths=()), '123')
    windows, _ = extract_engagements(player, matched)
    assert report['recording_gaps'] == 1
    assert len(windows) == 2
    assert windows[0]['end_tick'] < 90
    assert windows[1]['start_tick'] >= 130


def test_missing_freeze_end_never_assumes_active_play():
    context = events()
    context['round_freeze_end'] = pd.DataFrame(columns=['tick'])
    player, matched, report = segment_gameplay(telemetry(), context, '123')
    assert not player['active'].any()
    assert not extract_engagements(player, matched)[0]
    assert any(a['kind'] == 'round_missing_freeze_end' for a in report['round_event_anomalies'])


def test_unusual_round_sequences_have_explicit_anomalies():
    context = {
        'round_start': pd.DataFrame({'tick': [50]}),
        'round_freeze_end': pd.DataFrame({'tick': [10, 20, 60]}),
        'round_end': pd.DataFrame({'tick': [0]}),
    }
    intervals, anomalies = round_intervals(context, 100)
    assert [(r['start_tick'], r['end_tick_exclusive']) for r in intervals] == [(10, 50), (60, 100)]
    kinds = {a['kind'] for a in anomalies}
    assert kinds == {'round_end_without_active_round', 'freeze_end_without_round_start',
                     'duplicate_freeze_end', 'round_start_without_round_end', 'active_round_without_end'}


def test_sparse_window_is_reported_instead_of_silently_skipped():
    frame = telemetry().iloc[:16]
    player, matched, _ = segment_gameplay(frame, events(shots=(12,), deaths=()), '123')
    windows, skipped = extract_engagements(player, matched)
    assert not windows
    assert skipped[0]['reason'] == 'fewer_than_8_samples'


def test_matching_uses_exact_ids_and_preserves_multiple_shots_on_same_tick():
    context = events(shots=(60, 60), deaths=())
    matched = match_player_events(context, '123')
    assert matched['event_type'].eq('weapon_fire').sum() == 2
    assert matched['event_type'].eq('player_hurt').sum() == 2
    context['weapon_fire']['user_steamid'] = float(76561199104430312)
    with pytest.raises(ValueError, match='imprecise floats'):
        match_player_events(context, '123')


def test_life_state_semantics_must_agree_with_recording():
    frame = telemetry()
    frame.loc[20, 'life_state'] = 2
    with pytest.raises(ValueError, match='Life-state verification failed'):
        segment_gameplay(frame, events(), '123')


def test_gameplay_duplicate_tick_keeps_last_and_reports_loss():
    frame = pd.concat([telemetry(), telemetry().iloc[[50]].assign(health=0, life_state=2)], ignore_index=True)
    player, _, report = segment_gameplay(frame, events(deaths=()), '123')
    assert not player.loc[player['tick'].eq(50), 'active'].any()
    assert report['duplicate_samples_removed'] == 1


@pytest.mark.parametrize('rate', [0, -1, np.nan, np.inf])
def test_invalid_tickrates_are_rejected(rate):
    with pytest.raises(ValueError, match='finite and positive'):
        segment_gameplay(telemetry(), events(), '123', tickrate=rate)


def test_spectator_team_is_not_active():
    frame = telemetry()
    frame.loc[80:100, 'team_num'] = 1
    player, _, _ = segment_gameplay(frame, events(deaths=()), '123')
    assert not player.loc[80:100, 'active'].any()
    assert player.loc[79, 'segment_id'] != player.loc[101, 'segment_id']


def test_incoming_and_suicide_deaths_are_barriers_but_kills_are_not():
    context = events(shots=(60, 70), deaths=())
    context['player_death'] = pd.DataFrame({'tick': [60, 100], 'user_steamid': ['456', '123'],
                                           'attacker_steamid': ['123', '123']})
    player, matched, _ = segment_gameplay(telemetry(), context, '123')
    assert player.loc[60, 'active']
    assert not player.loc[100, 'active']
    windows, _ = extract_engagements(player, matched)
    assert windows[0]['kill_events'] == 1


def test_next_round_clears_death_latch_without_inventing_a_respawn():
    context = events(shots=(90, 140), deaths=(100,))
    context['round_start'] = pd.DataFrame({'tick': [0, 128]})
    context['round_freeze_end'] = pd.DataFrame({'tick': [10, 130]})
    context['round_end'] = pd.DataFrame({'tick': [127, 245]})
    player, _, _ = segment_gameplay(telemetry(), context, '123')
    assert not player.loc[100:126, 'active'].any()
    assert player.loc[130, 'active']


def test_empty_event_stream_produces_explicit_zero_coverage():
    player, matched, report = segment_gameplay(telemetry(), {}, '123')
    assert not player['active'].any()
    assert report['active_sample_fraction'] == 0
    assert extract_engagements(player, matched) == ([], [])


def test_invalid_tick_is_rejected_rather_than_silently_joining_data():
    frame = telemetry().astype({'tick': float})
    frame.loc[50, 'tick'] = np.nan
    with pytest.raises(ValueError, match='ticks must be finite'):
        segment_gameplay(frame, events(), '123')


def test_cli_exports_report_events_and_roundtrip_telemetry(tmp_path, monkeypatch):
    import hashlib
    import json
    from aimguard.core import extract_features

    source = tmp_path / 'fixture.dem'
    source.write_bytes(b'test source for provenance')
    frame = telemetry().astype({'yaw': 'float32', 'pitch': 'float32'})
    monkeypatch.setattr('aimguard.gameplay.load_gameplay_demo', lambda path, steamid: (frame, events()))
    output = tmp_path / 'analysis'
    main([str(source), '--steamid', '123', '--output', str(output), '--max-plots', '0'])
    report = json.loads((output / 'report.json').read_text())
    assert report['source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert report['engagement_count'] > 0
    assert report['plots'] == []
    assert report['dependencies']['demoparser2']
    records = json.loads((output / 'events.json').read_text())
    assert all(isinstance(row['user_steamid'], str) for row in records)
    exported = pd.read_csv(output / 'telemetry.csv')
    for window in report['engagements']:
        part = exported.loc[exported['tick'].between(window['start_tick'], window['end_tick'])]
        recomputed = extract_features(part['tick'].to_numpy() / 64, part['yaw'], part['pitch'])
        for key, value in recomputed.items():
            assert window['features'][key] == pytest.approx(value, rel=1e-8, abs=1e-8)

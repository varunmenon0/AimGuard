import copy
import json

import numpy as np
import pandas as pd
import pytest

from aimguard.batch import load_manifest, main, run_batch, validate_windows
from aimguard.gameplay import extract_engagements, segment_gameplay


def fixture():
    ticks = np.arange(128)
    frame = pd.DataFrame(dict(tick=ticks, steamid='123', yaw=ticks * .1,
                              pitch=0., health=100, life_state=0, team_num=2))
    events = {
        'round_start': pd.DataFrame({'tick': [0]}),
        'round_freeze_end': pd.DataFrame({'tick': [10]}),
        'round_end': pd.DataFrame({'tick': [127]}),
        'weapon_fire': pd.DataFrame({'tick': [60], 'weapon': ['weapon_ak47'], 'user_steamid': ['123']}),
        'player_hurt': pd.DataFrame(columns=['tick']),
        'player_death': pd.DataFrame(columns=['tick']),
    }
    return frame, events


def manifest(tmp_path, jobs=None):
    path = tmp_path / 'jobs.json'
    path.write_text(json.dumps(jobs if jobs is not None else [
        dict(demo='fixture.dem', steamid='123', tickrate=64)]))
    return path


def test_batch_uses_real_exports_and_isolates_missing_replay(tmp_path, monkeypatch):
    source = tmp_path / 'fixture.dem'
    source.write_bytes(b'fixture')
    from aimguard.gameplay import load_gameplay_demo

    def load(path, steamid):
        if path == source:
            return fixture()
        return load_gameplay_demo(path, steamid)

    monkeypatch.setattr('aimguard.gameplay.load_gameplay_demo', load)
    path = manifest(tmp_path, [dict(demo='missing.dem', steamid='123', tickrate=64),
                               dict(demo='fixture.dem', steamid='123', tickrate=64)])
    output = tmp_path / 'results'
    summary = run_batch(path, output, max_plots=0)
    assert summary['counts'] == dict(passed=1, warning=0, failed=0, error=1)
    assert summary['jobs'][0]['error_stage'] == 'analysis'
    assert summary['jobs'][1]['windows'] == 1
    assert summary['jobs'][1]['violations'] == []
    assert summary['distinct_successful_replays'] == 1
    assert json.loads((output / 'summary.json').read_text()) == summary
    assert (output / 'summary.md').is_file()
    assert main([str(path), '--output', str(tmp_path / 'cli'), '--max-plots', '0']) == 1
    with pytest.raises(FileExistsError):
        run_batch(path, output)


def test_zero_windows_are_warned_not_claimed_as_validation_success(tmp_path, monkeypatch):
    (tmp_path / 'fixture.dem').write_bytes(b'fixture')
    frame, events = fixture()
    events.pop('weapon_fire')
    monkeypatch.setattr('aimguard.gameplay.load_gameplay_demo', lambda *args: (frame, events))
    # The real loader supplies all event tables, even when empty.
    from aimguard.gameplay import ROUND_EVENTS, COMBAT_EVENTS
    for key in ROUND_EVENTS + COMBAT_EVENTS:
        events.setdefault(key, pd.DataFrame(columns=['tick']))
    result = run_batch(manifest(tmp_path), tmp_path / 'results', 0)
    assert result['jobs'][0]['status'] == 'warning'
    assert result['jobs'][0]['warnings'] == ['no_shooting_windows']


def test_batch_reports_violations_and_cli_exits_nonzero(tmp_path, monkeypatch):
    (tmp_path / 'fixture.dem').write_bytes(b'fixture')
    monkeypatch.setattr('aimguard.gameplay.load_gameplay_demo', lambda *args: fixture())
    monkeypatch.setattr('aimguard.batch.validate_windows', lambda *args: [
        {'engagement_id': 0, 'reasons': ['death_boundary']}])
    path = manifest(tmp_path)
    output = tmp_path / 'failed'
    assert main([str(path), '--output', str(output), '--max-plots', '0']) == 1
    result = json.loads((output / 'summary.json').read_text())
    assert result['counts']['failed'] == 1
    assert result['distinct_successful_replays'] == 0
    assert result['jobs'][0]['violations'][0]['reasons'] == ['death_boundary']


@pytest.mark.parametrize('fault,expected', [
    ('inactive', 'inactive_samples'), ('round', 'round_boundary'),
    ('segment', 'segment_boundary'), ('death', 'death_boundary'),
    ('features', 'invalid_features'), ('shots', 'unmatched_shots'),
])
def test_validator_detects_corrupted_windows(fault, expected):
    frame, source_events = fixture()
    player, events, quality = segment_gameplay(frame, source_events, '123')
    windows, _ = extract_engagements(player, events)
    report = dict(engagements=copy.deepcopy(windows), assumed_tickrate_hz=64, data_quality=quality)
    assert validate_windows(player, events, report) == []
    index = player.index[player.tick.eq(60)][0]
    if fault == 'inactive':
        player.loc[index, 'active'] = False
    elif fault == 'round':
        player.loc[index, 'round_id'] = 99
    elif fault == 'segment':
        player.loc[index, 'segment_id'] = 99
    elif fault == 'death':
        events = pd.concat([events, pd.DataFrame([dict(tick=60, event_type='player_death',
                                                      player_role='victim', segment_id=-1)])])
    elif fault == 'features':
        report['engagements'][0]['features']['mean_speed'] = np.nan
    else:
        report['engagements'][0]['shot_ticks'] = [61]
    assert expected in validate_windows(player, events, report)[0]['reasons']


@pytest.mark.parametrize('jobs', [[], {}, [dict(demo='x.dem', steamid=123, tickrate=64)],
                                    [dict(demo='x.dem', steamid='123', tickrate=0)],
                                    [dict(demo='x.dem', steamid='123', tickrate=True)]])
def test_manifest_rejects_ambiguous_or_invalid_jobs(tmp_path, jobs):
    with pytest.raises(ValueError):
        load_manifest(manifest(tmp_path, jobs))


def test_manifest_paths_are_relative_to_manifest_and_duplicates_rejected(tmp_path):
    job = dict(demo='fixture.dem', steamid='123', tickrate=64)
    assert load_manifest(manifest(tmp_path, [job]))[0]['demo'] == str(tmp_path / 'fixture.dem')
    with pytest.raises(ValueError, match='Duplicate'):
        load_manifest(manifest(tmp_path, [job, job]))


@pytest.mark.parametrize('all_null', [False, True])
def test_listed_player_without_gameplay_has_actionable_error(tmp_path, monkeypatch, all_null):
    import demoparser2
    from aimguard.gameplay import load_gameplay_demo
    source = tmp_path / 'empty-player.dem'
    source.write_bytes(b'fixture')
    ticks = pd.DataFrame({'tick': [1], 'steamid': ['123'], 'name': ['listed player']})
    if all_null:
        for key in ('yaw', 'pitch', 'health', 'life_state', 'team_num'):
            ticks[key] = np.nan

    class Parser:
        def __init__(self, path):
            pass

        def parse_ticks(self, *args, **kwargs):
            return ticks

    monkeypatch.setattr(demoparser2, 'DemoParser', Parser)
    with pytest.raises(ValueError, match='No usable gameplay telemetry'):
        load_gameplay_demo(source, '123')

"""Conservative round/life segmentation and shot-centered replay analysis.

These are shooting windows, not verified visible-enemy engagements. All round
intervals are half-open; death ticks are excluded even if health updates lag.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.core import angle_delta, extract_features

ROUND_EVENTS = ('round_start', 'round_freeze_end', 'round_end')
COMBAT_EVENTS = ('weapon_fire', 'player_hurt', 'player_death')
FEATURE_VERSION = '0.3.0'


def positive_finite(**values):
    for name, value in values.items():
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be finite and positive')


def identity_strings(series):
    """Never silently compare SteamIDs that have already lost float precision."""
    def convert(value):
        if pd.isna(value):
            return ''
        if isinstance(value, (float, np.floating)):
            if not np.isfinite(value) or abs(value) > 2**53 or value != int(value):
                raise ValueError('SteamIDs must be exact integers or strings, not imprecise floats')
            return str(int(value))
        return str(value).strip()
    return series.map(convert)


def checked_ticks(frame, label):
    if 'tick' not in frame:
        raise ValueError(f'{label} is missing tick')
    ticks = pd.to_numeric(frame['tick'], errors='coerce').to_numpy(dtype=float)
    if (not np.isfinite(ticks).all() or np.any(ticks < 0) or np.any(ticks >= 2**63)
            or np.any(ticks != np.floor(ticks))):
        raise ValueError(f'{label} ticks must be finite nonnegative integers')
    return ticks.astype('int64')


def round_intervals(events, stop_tick):
    """Require a freeze-end to open play; report malformed sequences explicitly."""
    transitions = []
    priority = {'round_end': 0, 'round_start': 1, 'round_freeze_end': 2}
    for name in ROUND_EVENTS:
        frame = events.get(name, pd.DataFrame(columns=['tick']))
        transitions.extend((int(t), priority[name], name) for t in checked_ticks(frame, name))
    transitions.sort()
    intervals, anomalies = [], []
    phase, round_id, start = 'idle', 0, None

    def note(kind, tick):
        anomalies.append({'kind': kind, 'tick': int(tick)})

    def close(tick):
        if start is not None and tick > start:
            intervals.append({'round_id': round_id, 'start_tick': start, 'end_tick_exclusive': tick})

    for tick, _, name in transitions:
        if name == 'round_start':
            if phase == 'active':
                close(tick)
                note('round_start_without_round_end', tick)
            elif phase == 'frozen':
                note('round_start_without_freeze_end', tick)
            round_id += 1
            phase, start = 'frozen', None
        elif name == 'round_freeze_end':
            if phase == 'active':
                note('duplicate_freeze_end', tick)
                continue
            if phase == 'idle':
                # A freeze-end establishes active play even if its start is absent.
                round_id += 1
                note('freeze_end_without_round_start', tick)
            phase, start = 'active', tick
        else:
            if phase == 'active':
                close(tick)
            else:
                note('round_end_without_active_round', tick)
            if phase == 'frozen':
                note('round_missing_freeze_end', tick)
            phase, start = 'idle', None
    if phase == 'active':
        close(stop_tick)
        note('active_round_without_end', stop_tick)
    elif phase == 'frozen':
        note('round_missing_freeze_end', stop_tick)
    return intervals, anomalies


def match_player_events(events, steamid):
    """Match the shooter's ID, and both attacker/victim roles for hurt/death."""
    selected = []
    for name in COMBAT_EVENTS:
        frame = events.get(name, pd.DataFrame()).copy()
        if frame.empty:
            continue
        required = {'tick', 'user_steamid'}
        if name != 'weapon_fire':
            required.add('attacker_steamid')
        if not required.issubset(frame):
            raise ValueError(f'{name} missing columns: {sorted(required.difference(frame.columns))}')
        frame['tick'] = checked_ticks(frame, name)
        victim = identity_strings(frame['user_steamid']).eq(str(steamid))
        attacker = (identity_strings(frame['attacker_steamid']).eq(str(steamid))
                    if name != 'weapon_fire' else pd.Series(False, index=frame.index))
        role = np.where(victim & attacker, 'attacker_and_victim',
                        np.where(attacker, 'attacker', 'victim'))
        frame['player_role'] = 'shooter' if name == 'weapon_fire' else role
        frame['event_type'] = name
        for col in frame.columns:
            if col.endswith('steamid'):
                frame[col] = identity_strings(frame[col])
        selected.append(frame.loc[victim | attacker])
    if not selected:
        return pd.DataFrame(columns=['tick', 'event_type', 'player_role'])
    return pd.concat(selected, ignore_index=True).sort_values('tick', kind='stable').reset_index(drop=True)


def segment_gameplay(frame, events, steamid, tickrate=64.0, max_gap_s=0.25):
    positive_finite(tickrate=tickrate, max_gap_s=max_gap_s)
    required = {'tick', 'steamid', 'yaw', 'pitch', 'health', 'life_state', 'team_num'}
    if not required.issubset(frame):
        raise ValueError(f'Telemetry missing columns: {sorted(required.difference(frame.columns))}')
    player = frame.loc[identity_strings(frame['steamid']).eq(str(steamid))].copy()
    if player.empty:
        raise ValueError(f'No telemetry for steamid {steamid}')
    player['steamid'] = str(steamid)
    input_rows = len(player)
    player['tick'] = checked_ticks(player, 'telemetry')
    player = player.sort_values('tick', kind='stable').drop_duplicates('tick', keep='last').reset_index(drop=True)
    numeric = ['yaw', 'pitch', 'health', 'life_state', 'team_num']
    for key in numeric:
        player[key] = pd.to_numeric(player[key], errors='coerce')
    tick = player['tick'].to_numpy()
    values = player[numeric].to_numpy(dtype=float)
    finite = np.isfinite(values).all(axis=1)
    # Verified against the input recording rather than silently assuming a code.
    positive_health = player['health'].gt(0)
    finite_life_health = np.isfinite(player[['health', 'life_state']]).all(axis=1)
    inconsistent = positive_health & finite_life_health & player['life_state'].ne(0)
    if inconsistent.any():
        raise ValueError('Life-state verification failed: positive health with life_state != 0')
    valid_state = player['life_state'].isin([0, 1, 2]).to_numpy()
    valid_angles = player['pitch'].between(-90, 90).to_numpy()
    valid = finite & valid_state & valid_angles
    alive = (positive_health & player['life_state'].eq(0)).to_numpy()
    playing_team = player['team_num'].isin([2, 3]).to_numpy()
    intervals, anomalies = round_intervals(events, int(tick[-1]) + 1)
    rounds = np.full(len(player), -1, dtype=int)
    round_starts = np.full(len(player), -1, dtype=int)
    for interval in intervals:
        mask = (tick >= interval['start_tick']) & (tick < interval['end_tick_exclusive'])
        rounds[mask] = interval['round_id']
        round_starts[mask] = interval['start_tick']
    matched = match_player_events(events, steamid)
    deaths = matched.loc[matched['event_type'].eq('player_death') &
                         matched['player_role'].isin(['victim', 'attacker_and_victim']), 'tick'].to_numpy(dtype=int)
    death_counts = np.searchsorted(deaths, tick, side='right')
    blocked = np.zeros(len(player), dtype=bool)
    latched, saw_dead, previous_round, previous_count = False, False, -1, 0
    for i in range(len(player)):
        rid = rounds[i]
        if rid != previous_round:
            latched, saw_dead = False, False
            previous_count = np.searchsorted(deaths, round_starts[i], side='left') if rid >= 0 else death_counts[i]
        death_now = rid >= 0 and death_counts[i] > previous_count
        if death_now:
            latched, saw_dead = True, False
        if latched:
            if valid[i] and not alive[i]:
                saw_dead = True
            elif valid[i] and alive[i] and saw_dead and not death_now:
                latched = False
        blocked[i] = latched or death_now
        previous_round, previous_count = rid, death_counts[i]
    active = valid & alive & playing_team & (rounds >= 0) & ~blocked
    reason = np.full(len(player), 'active', dtype=object)
    # Mutually exclusive reasons for coverage reporting, in priority order.
    reason[~active] = 'death_event_latch'
    reason[~alive] = 'not_alive'
    reason[~playing_team] = 'not_playing_team'
    reason[rounds < 0] = 'outside_active_round'
    reason[~valid] = 'invalid_sample'
    gaps = np.r_[False, np.diff(tick) / tickrate > max_gap_s]
    boundary = active & (np.r_[True, ~active[:-1]] | gaps | np.r_[True, np.diff(rounds) != 0])
    player['time_s'] = (tick - tick[0]) / tickrate
    player['round_id'] = rounds
    player['active'] = active
    player['exclusion_reason'] = reason
    player['segment_id'] = np.where(active, np.cumsum(boundary) - 1, -1)
    # Preserve enough precision to recalculate derivatives after CSV round trips.
    player[['yaw', 'pitch']] = player[['yaw', 'pitch']].astype('float64')
    life_summary = []
    for state, chunk in player.groupby('life_state', dropna=False):
        health = chunk['health'].to_numpy(dtype=float)
        health = health[np.isfinite(health)]
        life_summary.append({'life_state': float(state) if np.isfinite(state) else None,
                             'samples': len(chunk), 'health_min': float(health.min()) if len(health) else None,
                             'health_max': float(health.max()) if len(health) else None})
    same_segment = active[1:] & active[:-1] & ~boundary[1:]
    active_duration = float((np.diff(tick)[same_segment] / tickrate).sum())
    report = {
        'input_samples': input_rows, 'duplicate_samples_removed': input_rows - len(player),
        'normalized_samples': len(player), 'active_samples': int(active.sum()),
        'active_sample_fraction': float(active.mean()), 'segments': int(boundary.sum()),
        'sample_counts_by_reason': {str(k): int(v) for k, v in pd.Series(reason).value_counts().items()},
        'active_duration_seconds': active_duration,
        'recording_duration_seconds': float((tick[-1] - tick[0]) / tickrate),
        'life_state_verified': bool((positive_health & finite_life_health).any()), 'life_state_summary': life_summary,
        'active_round_intervals': intervals, 'round_event_anomalies': anomalies,
        'recording_gaps': int(gaps.sum()), 'max_gap_seconds': max_gap_s,
    }
    matched = assign_event_segments(matched, player)
    report['matched_event_counts'] = {name: int(matched['event_type'].eq(name).sum()) for name in COMBAT_EVENTS}
    report['events_outside_active_segments'] = {
        name: int((matched['event_type'].eq(name) & matched['segment_id'].eq(-1)).sum()) for name in COMBAT_EVENTS}
    return player, matched, report


def assign_event_segments(events, player):
    result = events.copy()
    result['segment_id'] = -1
    bounds = player.loc[player['active']].groupby('segment_id')['tick'].agg(['min', 'max'])
    if bounds.empty or result.empty:
        return result
    positions = np.searchsorted(bounds['min'].to_numpy(), result['tick'].to_numpy(), side='right') - 1
    safe = np.maximum(positions, 0)
    inside = (positions >= 0) & (result['tick'].to_numpy() <= bounds['max'].to_numpy()[safe])
    result['segment_id'] = np.where(inside, bounds.index.to_numpy()[safe], -1)
    return result


def correction_counts(yaw, pitch, threshold=0.05):
    counts = {}
    for name, steps in [('yaw', angle_delta(np.diff(yaw))), ('pitch', np.diff(pitch))]:
        moving = np.abs(steps) >= threshold
        counts[f'{name}_reversals'] = int(np.sum(moving[:-1] & moving[1:] & (steps[:-1] * steps[1:] < 0)))
    return counts


def extract_engagements(player, events, tickrate=64.0, pre_s=0.5, post_s=0.5, shot_gap_s=0.5):
    positive_finite(tickrate=tickrate, shot_gap_s=shot_gap_s)
    for name, value in [('pre_s', pre_s), ('post_s', post_s)]:
        if not np.isfinite(value) or value < 0:
            raise ValueError(f'{name} must be finite and nonnegative')
    windows, skipped = [], []
    shots = events.loc[events['event_type'].eq('weapon_fire') & events['segment_id'].ge(0)]
    for segment_id, part in player.loc[player['active']].groupby('segment_id', sort=True):
        shot_ticks = np.sort(shots.loc[shots['segment_id'].eq(segment_id), 'tick'].to_numpy(dtype=int))
        groups = np.split(shot_ticks, np.flatnonzero(np.diff(shot_ticks) / tickrate > shot_gap_s) + 1)
        for group in groups:
            if not len(group):
                continue
            lo = max(int(part['tick'].iloc[0]), int(np.ceil(group[0] - pre_s * tickrate)))
            hi = min(int(part['tick'].iloc[-1]), int(np.floor(group[-1] + post_s * tickrate)))
            trajectory = part.loc[part['tick'].between(lo, hi)]
            info = {'segment_id': int(segment_id), 'round_id': int(part['round_id'].iloc[0]),
                    'shot_ticks': group.tolist(), 'shot_count': len(group)}
            if len(trajectory) < 8:
                skipped.append({**info, 'reason': 'fewer_than_8_samples', 'samples': len(trajectory)})
                continue
            start, end = int(trajectory['tick'].iloc[0]), int(trajectory['tick'].iloc[-1])
            # Do not publish a window whose edge shots fall outside sampled data.
            if group[0] < start or group[-1] > end:
                skipped.append({**info, 'reason': 'shot_not_bracketed_by_samples', 'samples': len(trajectory)})
                continue
            relevant = events.loc[events['segment_id'].eq(segment_id) & events['tick'].between(start, end)]
            outgoing = relevant['player_role'].isin(['attacker', 'attacker_and_victim'])
            incoming = relevant['player_role'].isin(['victim', 'attacker_and_victim'])
            features = extract_features(trajectory['tick'].to_numpy(dtype=float) / tickrate,
                                        trajectory['yaw'].to_numpy(), trajectory['pitch'].to_numpy())
            features.update(correction_counts(trajectory['yaw'].to_numpy(), trajectory['pitch'].to_numpy()))
            windows.append({**info, 'engagement_id': len(windows), 'start_tick': start, 'end_tick': end,
                            'samples': len(trajectory), 'duration_seconds': (end - start) / tickrate,
                            'damage_dealt_events': int((relevant['event_type'].eq('player_hurt') & outgoing).sum()),
                            'damage_taken_events': int((relevant['event_type'].eq('player_hurt') & incoming).sum()),
                            'kill_events': int((relevant['event_type'].eq('player_death') & outgoing).sum()),
                            'features': features})
    return windows, skipped


def load_gameplay_demo(path, steamid):
    if not path.is_file() or path.suffix.lower() != '.dem':
        raise ValueError(f'Expected an existing .dem file: {path}')
    if not str(steamid).isdigit():
        raise ValueError('steamid must be a numeric SteamID')
    from demoparser2 import DemoParser
    parser = DemoParser(str(path))
    ticks = parser.parse_ticks(['yaw', 'pitch', 'health', 'life_state', 'team_num', 'X', 'Y', 'Z'],
                               players=[int(steamid)])
    required = {'yaw', 'pitch', 'health', 'life_state', 'team_num'}
    if ticks.empty or not required.issubset(ticks) or ticks[list(required)].dropna(how='all').empty:
        raise ValueError(f'No usable gameplay telemetry for SteamID {steamid}; '
                         'a player listing alone does not establish recorded gameplay')
    events = {name: parser.parse_event(name) for name in ROUND_EVENTS + COMBAT_EVENTS}
    return ticks, events


def plot_engagements(player, windows, output, tickrate, limit=10):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    paths = []
    for window in windows[:limit]:
        part = player.loc[player['segment_id'].eq(window['segment_id']) &
                          player['tick'].between(window['start_tick'], window['end_tick'])]
        tick = part['tick'].to_numpy(dtype=float)
        time = (tick - window['shot_ticks'][0]) / tickrate
        yaw, pitch = part['yaw'].to_numpy(), part['pitch'].to_numpy()
        speed = np.r_[np.nan, np.hypot(angle_delta(np.diff(yaw)), np.diff(pitch)) / (np.diff(tick) / tickrate)]
        fig, axes = plt.subplots(3, 1, sharex=True, figsize=(10, 7))
        axes[0].plot(time, np.rad2deg(np.unwrap(np.deg2rad(yaw))))
        axes[1].plot(time, pitch)
        axes[2].plot(time, speed)
        for axis, label in zip(axes, ['Yaw (deg, unwrapped)', 'Pitch (deg)', 'Speed (deg/s)']):
            axis.set_ylabel(label)
            axis.ticklabel_format(axis='y', style='plain', useOffset=False)
            for i, shot in enumerate(window['shot_ticks']):
                axis.axvline((shot - window['shot_ticks'][0]) / tickrate, color='crimson', alpha=0.4,
                             lw=0.8, label='Weapon fire' if i == 0 else None)
        axes[0].legend(loc='best')
        axes[-1].set_xlabel('Seconds relative to first shot')
        shot_label = 'shot' if window['shot_count'] == 1 else 'shots'
        fig.suptitle(f"Shot-centered window {window['engagement_id']} | round {window['round_id']} | {window['shot_count']} {shot_label}")
        fig.tight_layout()
        filename = f"engagement_{window['engagement_id']:04d}.png"
        fig.savefig(output / filename, dpi=150)
        plt.close(fig)
        paths.append(filename)
    return paths


def analyze_demo(demo, steamid, output, tickrate=64.0, pre_s=0.5, post_s=0.5,
                 shot_gap_s=0.5, max_plots=10):
    """Run one replay/player analysis and return the exported report."""
    demo, output = Path(demo), Path(output)
    positive_finite(tickrate=tickrate, shot_gap_s=shot_gap_s)
    if not all(np.isfinite(v) and v >= 0 for v in (pre_s, post_s)):
        raise ValueError('pre/post seconds must be finite and nonnegative')
    if max_plots < 0:
        raise ValueError('max-plots must be nonnegative')
    frame, events = load_gameplay_demo(demo, steamid)
    player, matched, quality = segment_gameplay(frame, events, steamid, tickrate)
    windows, skipped = extract_engagements(player, matched, tickrate,
                                           pre_s, post_s, shot_gap_s)
    output.mkdir(parents=True, exist_ok=True)
    player.to_csv(output / 'telemetry.csv', index=False)
    (output / 'events.json').write_text(matched.to_json(orient='records', indent=2) + '\n')
    plots = plot_engagements(player, windows, output, tickrate, max_plots) if max_plots else []
    digest = hashlib.sha256()
    with demo.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    report = {
        'feature_version': FEATURE_VERSION, 'source': str(demo), 'source_sha256': digest.hexdigest(),
        'steamid': steamid, 'assumed_tickrate_hz': tickrate,
        'configuration': {'pre_seconds': pre_s, 'post_seconds': post_s,
                          'shot_gap_seconds': shot_gap_s, 'max_plots': max_plots},
        'dependencies': {name: importlib.metadata.version(name) for name in ('demoparser2', 'numpy', 'pandas', 'matplotlib')},
        'note': 'Shot-centered descriptive windows; no visibility checks, cheat classification, or punishment decisions. Padded windows may overlap.',
        'correction_definition': 'Adjacent yaw/pitch steps with opposite signs, both at least 0.05 degrees; not verified target-relative corrections.',
        'source_event_counts': {name: len(events[name]) for name in ROUND_EVENTS + COMBAT_EVENTS},
        'data_quality': quality, 'engagement_count': len(windows), 'engagements': windows,
        'grouped_shots_in_published_windows': sum(w['shot_count'] for w in windows),
        'skipped_engagements': skipped, 'plots': plots,
    }
    (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description='AimGuard v0.3 shot-centered replay diagnostics')
    ap.add_argument('demo', type=Path)
    ap.add_argument('--steamid', required=True)
    ap.add_argument('--tickrate', type=float, default=64.0, help='Explicit timing assumption; verify for the recording')
    ap.add_argument('--pre-seconds', type=float, default=0.5)
    ap.add_argument('--post-seconds', type=float, default=0.5)
    ap.add_argument('--shot-gap-seconds', type=float, default=0.5)
    ap.add_argument('--max-plots', type=int, default=10)
    ap.add_argument('--output', type=Path, default=Path('outputs/v03'))
    args = ap.parse_args(argv)
    try:
        report = analyze_demo(args.demo, args.steamid, args.output, args.tickrate,
                              args.pre_seconds, args.post_seconds, args.shot_gap_seconds,
                              args.max_plots)
    except (ValueError, ImportError) as exc:
        ap.error(str(exc))
    quality = report['data_quality']
    windows, skipped = report['engagements'], report['skipped_engagements']
    print(f"Active samples: {quality['active_samples']}/{quality['normalized_samples']}; "
          f"segments: {quality['segments']}; shot-centered windows: {len(windows)}; skipped: {len(skipped)}. Results: {args.output}")


if __name__ == '__main__':
    main()

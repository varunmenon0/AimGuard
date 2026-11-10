"""Read CS2 demo telemetry and produce descriptive (not cheat) diagnostics."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.core import extract_features


def normalize_ticks(frame: pd.DataFrame, steamid: str, tickrate: float) -> pd.DataFrame:
    if not np.isfinite(tickrate) or tickrate <= 0:
        raise ValueError('tickrate must be finite and positive')
    required = {'tick', 'steamid', 'yaw', 'pitch'}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f'Missing columns: {sorted(missing)}; available: {list(frame.columns)}')
    player = frame.loc[frame['steamid'].astype(str) == str(steamid)].copy()
    if player.empty:
        raise ValueError(f'No ticks for steamid {steamid}; check --list-players')
    for key in ('tick', 'yaw', 'pitch'):
        player[key] = pd.to_numeric(player[key], errors='coerce')
    player = player.replace([np.inf, -np.inf], np.nan).dropna(subset=['tick', 'yaw', 'pitch'])
    player = player.sort_values('tick', kind='stable').drop_duplicates('tick', keep='last')
    if player.empty:
        raise ValueError('No valid ticks after cleaning')
    player['time_s'] = (player['tick'] - player['tick'].iloc[0]) / tickrate
    return player.reset_index(drop=True)


def window_features(player: pd.DataFrame, tickrate: float, window_s: float = 2.0):
    """Absolute tick bins, with one preceding sample to retain boundary movement.

    Shared samples are context only: each intersample movement belongs to the
    bin containing its ending tick. Gaps are never interpolated.
    """
    if not np.isfinite(tickrate) or tickrate <= 0:
        raise ValueError('tickrate must be finite and positive')
    if not np.isfinite(window_s) or window_s <= 0:
        raise ValueError('window_s must be finite and positive')
    if player.empty:
        return []
    results = []
    player = player.sort_values('tick', kind='stable').reset_index(drop=True)
    window_ticks = max(1, round(window_s * tickrate))
    for _, chunk in player.groupby(player['tick'].astype('int64') // window_ticks):
        if chunk.index[0] > 0:
            chunk = pd.concat([player.iloc[[chunk.index[0] - 1]], chunk])
        if len(chunk) < 8:
            continue
        # Segment around gaps that the core extractor rejects.
        times = chunk['tick'].to_numpy(dtype=float) / tickrate
        breaks = np.flatnonzero(np.diff(times) > 0.25) + 1
        for sub in np.split(np.arange(len(chunk)), breaks):
            if len(sub) < 8:
                continue
            part = chunk.iloc[sub]
            try:
                features = extract_features(part['tick'].to_numpy(dtype=float) / tickrate,
                                            part['yaw'].to_numpy(dtype=float),
                                            part['pitch'].to_numpy(dtype=float))
            except ValueError:
                continue
            results.append({'start_tick': int(part['tick'].iloc[0]),
                            'end_tick': int(part['tick'].iloc[-1]),
                            'samples': len(part), **features})
    return results



def trajectory_diagnostics(player: pd.DataFrame, tickrate: float, max_gap_s: float = 0.25):
    """Calculate gap-aware view angles and angular speed using real tick differences.

    Speed at a sample describes movement since the preceding sample. It is NaN
    at the beginning of a segment, including after a recording gap.
    """
    if not all(np.isfinite(v) and v > 0 for v in (tickrate, max_gap_s)):
        raise ValueError('tickrate and max_gap_s must be finite and positive')
    result = player.copy().reset_index(drop=True)
    if result.empty:
        raise ValueError('No telemetry to analyze')
    tick = result['tick'].to_numpy(dtype=float)
    yaw = result['yaw'].to_numpy(dtype=float)
    pitch = result['pitch'].to_numpy(dtype=float)
    dt = np.diff(tick) / tickrate
    if np.any(dt <= 0) or not np.isfinite(dt).all():
        raise ValueError('Ticks must be finite and strictly increasing')
    gap = dt > max_gap_s
    # Discontinuities are segmented instead of connecting across absent data.
    starts = np.r_[0, np.flatnonzero(gap) + 1]
    ends = np.r_[starts[1:], len(result)]
    unwrapped = np.empty(len(result), dtype=float)
    yaw_rate = np.full(len(result), np.nan)
    pitch_rate = np.full(len(result), np.nan)
    speed = np.full(len(result), np.nan)
    for a, b in zip(starts, ends):
        unwrapped[a:b] = np.rad2deg(np.unwrap(np.deg2rad(yaw[a:b])))
        if b - a > 1:
            local_dt = np.diff(tick[a:b]) / tickrate
            dyaw = (np.diff(yaw[a:b]) + 180.0) % 360.0 - 180.0
            dpitch = np.diff(pitch[a:b])
            yaw_rate[a + 1:b] = dyaw / local_dt
            pitch_rate[a + 1:b] = dpitch / local_dt
            speed[a + 1:b] = np.hypot(dyaw, dpitch) / local_dt
    result['yaw_unwrapped'] = unwrapped
    result['yaw_velocity_dps'] = yaw_rate
    result['pitch_velocity_dps'] = pitch_rate
    result['angular_speed_dps'] = speed
    result['segment_id'] = np.cumsum(np.r_[False, gap]).astype(int)
    missing_ticks = np.maximum(np.diff(tick) - 1, 0).sum()
    stats = {
        'tickrate_hz': float(tickrate),
        'sample_count': int(len(result)),
        'first_tick': int(tick[0]),
        'last_tick': int(tick[-1]),
        'median_tick_spacing': float(np.median(np.diff(tick))) if len(tick) > 1 else None,
        'max_tick_spacing': float(np.max(np.diff(tick))) if len(tick) > 1 else None,
        'estimated_missing_ticks': int(missing_ticks),
        'recording_gaps': int(gap.sum()),
        'gap_threshold_seconds': float(max_gap_s),
        'segments': int(len(starts)),
        'valid_speed_samples': int(np.isfinite(speed).sum()),
        'note': 'Speed is derived from successive recorded view angles, not mouse input. Gaps are not interpolated.'
    }
    return result, stats


def save_diagnostic_plots(player: pd.DataFrame, output: Path):
    """Save gap-separated view-angle and angular-velocity plots."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(12, 7))
    for _, segment in player.groupby('segment_id', sort=True):
        axes[0].plot(segment['time_s'], segment['yaw_unwrapped'], lw=0.7)
        axes[1].plot(segment['time_s'], segment['pitch'], lw=0.7)
    axes[0].set_ylabel('Unwrapped yaw (degrees)')
    axes[1].set_ylabel('Pitch (degrees)')
    axes[1].set_xlabel('Time since first recorded tick (s)')
    fig.suptitle('CS2 player view angles (segmented at recording gaps)')
    fig.tight_layout()
    fig.savefig(output / 'trajectory.png', dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(12, 7))
    for _, segment in player.groupby('segment_id', sort=True):
        axes[0].plot(segment['time_s'], segment['yaw_velocity_dps'], lw=0.7)
        axes[1].plot(segment['time_s'], segment['angular_speed_dps'], lw=0.7)
    axes[0].set_ylabel('Yaw velocity (deg/s)')
    axes[1].set_ylabel('Angular speed (deg/s)')
    axes[1].set_xlabel('Time since first recorded tick (s)')
    fig.suptitle('CS2 aim movement rates (no interpolation across gaps)')
    fig.tight_layout()
    fig.savefig(output / 'angular_velocity.png', dpi=150)
    plt.close(fig)

def load_demo(path: Path):
    try:
        from demoparser2 import DemoParser
    except ImportError as exc:
        raise RuntimeError('Install dependencies: python -m pip install demoparser2 pandas matplotlib') from exc
    if not path.is_file() or path.suffix.lower() != '.dem':
        raise ValueError(f'Expected an existing .dem file: {path}')
    parser = DemoParser(str(path))
    return parser.parse_ticks(['pitch', 'yaw', 'X', 'Y', 'Z'])


def main(argv=None):
    ap = argparse.ArgumentParser(description='CS2 replay trajectory diagnostics (no cheat classification)')
    ap.add_argument('demo', type=Path)
    ap.add_argument('--list-players', action='store_true')
    ap.add_argument('--steamid', help='SteamID of player to analyze')
    ap.add_argument('--tickrate', type=float, default=64.0, help='Demo tick rate, verify for your recording (default: 64)')
    ap.add_argument('--window-seconds', type=float, default=2.0)
    ap.add_argument('--output', type=Path, default=Path('outputs/cs2'))
    args = ap.parse_args(argv)
    ticks = load_demo(args.demo)
    if args.list_players:
        players = ticks[['steamid', 'name']].drop_duplicates() if 'name' in ticks else ticks[['steamid']].drop_duplicates()
        print(players.to_string(index=False))
        return
    if not args.steamid:
        ap.error('Specify --steamid or --list-players')
    player = normalize_ticks(ticks, args.steamid, args.tickrate)
    player, diagnostics = trajectory_diagnostics(player, args.tickrate)
    features = window_features(player, args.tickrate, args.window_seconds)
    args.output.mkdir(parents=True, exist_ok=True)
    player.to_csv(args.output / 'telemetry.csv', index=False)
    (args.output / 'features.json').write_text(json.dumps({
        'source': str(args.demo), 'steamid': args.steamid, 'assumed_tickrate': args.tickrate,
        'note': 'Descriptive trajectory features only; not a cheat classification',
        'total_samples': len(player), 'feature_windows': features
    }, indent=2))
    (args.output / 'telemetry_diagnostics.json').write_text(json.dumps(diagnostics, indent=2))
    save_diagnostic_plots(player, args.output)
    print(f'Processed {len(player)} samples; {len(features)} feature windows. Results: {args.output}')


if __name__ == '__main__':
    main()

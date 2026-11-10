"""Read CS2 demo telemetry and produce descriptive (not cheat) diagnostics."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.core import extract_features


def normalize_ticks(frame: pd.DataFrame, steamid: str, tickrate: float) -> pd.DataFrame:
    if tickrate <= 0:
        raise ValueError('tickrate must be positive')
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
    player = player.sort_values('tick').drop_duplicates('tick', keep='last')
    if player.empty:
        raise ValueError('No valid ticks after cleaning')
    player['time_s'] = (player['tick'] - player['tick'].iloc[0]) / tickrate
    return player.reset_index(drop=True)


def window_features(player: pd.DataFrame, tickrate: float, window_s: float = 2.0):
    """Nonoverlapping windows; split at gaps rather than interpolating them."""
    if window_s <= 0:
        raise ValueError('window_s must be positive')
    if player.empty:
        return []
    results = []
    # Absolute tick bins keep the windows deterministic across calls.
    window_ticks = max(1, round(window_s * tickrate))
    for _, chunk in player.groupby((player['tick'].astype('int64') - int(player['tick'].iloc[0])) // window_ticks):
        chunk = chunk.sort_values('tick')
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
    features = window_features(player, args.tickrate, args.window_seconds)
    args.output.mkdir(parents=True, exist_ok=True)
    player.to_csv(args.output / 'telemetry.csv', index=False)
    (args.output / 'features.json').write_text(json.dumps({
        'source': str(args.demo), 'steamid': args.steamid, 'assumed_tickrate': args.tickrate,
        'note': 'Descriptive trajectory features only; not a cheat classification',
        'total_samples': len(player), 'feature_windows': features
    }, indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(11, 6))
    axes[0].plot(player['time_s'], player['yaw'], lw=.7)
    axes[0].set_ylabel('Yaw (degrees)')
    axes[1].plot(player['time_s'], player['pitch'], lw=.7)
    axes[1].set_ylabel('Pitch (degrees)')
    axes[1].set_xlabel('Time since first recorded tick (s)')
    fig.suptitle('CS2 player view angles (raw, not unwrapped)')
    fig.tight_layout()
    fig.savefig(args.output / 'trajectory.png', dpi=150)
    plt.close(fig)
    print(f'Processed {len(player)} samples; {len(features)} feature windows. Results: {args.output}')


if __name__ == '__main__':
    main()

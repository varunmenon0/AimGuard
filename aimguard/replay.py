"""Select a CS2 demo player and generate an offline AimGuard review."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from aimguard.cs2 import load_demo
from aimguard.gameplay import analyze_demo, identity_strings, positive_finite
from aimguard.review import build_review


def select_player(demo):
    ticks = load_demo(demo)
    players = ticks[['steamid', 'name'] if 'name' in ticks else ['steamid']].copy()
    players['steamid'] = identity_strings(players['steamid'])
    players = players.loc[players['steamid'].str.isdigit()].drop_duplicates('steamid')
    choices = list(players.to_dict('records'))
    if not choices:
        raise ValueError('No players were listed in this replay')
    for index, player in enumerate(choices, 1):
        print(f"{index:2}. {player.get('name', '')} ({player['steamid']})")
    try:
        choice = int(input('Select a player by number: '))
    except (ValueError, EOFError) as exc:
        raise ValueError('Select a listed player by number or supply --steamid') from exc
    if not 1 <= choice <= len(choices):
        raise ValueError('Player number is outside the list')
    return choices[choice - 1]['steamid']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('demo', type=Path)
    parser.add_argument('--steamid', help='Select a player directly instead of showing the menu')
    parser.add_argument('--weapon-mode', choices=['firearms', 'all'], default='firearms')
    parser.add_argument('--near-shot-seconds', type=float, default=0.1)
    parser.add_argument('--tickrate', required=True, type=float, help='Assumed ticks per second')
    parser.add_argument('--output', type=Path, required=True, help='New analysis folder')
    args = parser.parse_args(argv)
    try:
        positive_finite(tickrate=args.tickrate)
        if args.output.exists():
            raise ValueError(f'Choose a new output folder: {args.output}')
        steamid = args.steamid if args.steamid is not None else select_player(args.demo)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=args.output.parent) as temporary:
            staging = Path(temporary) / 'analysis'
            report = analyze_demo(args.demo, steamid, staging, args.tickrate, max_plots=0,
                                  weapon_mode=args.weapon_mode, near_shot_s=args.near_shot_seconds)
            build_review(staging, staging / 'review.html')
            args.output.mkdir()
            for artifact in staging.iterdir():
                artifact.rename(args.output / artifact.name)
    except (OSError, ValueError, KeyError, RuntimeError, ImportError) as exc:
        parser.error(str(exc))
    print(f"{report['engagement_count']} shooting windows. Open: {(args.output / 'review.html').resolve()}")


if __name__ == '__main__':
    main()

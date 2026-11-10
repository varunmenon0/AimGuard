"""Repeatable replay validation; failures are isolated to each manifest job."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.gameplay import analyze_demo


def validate_windows(player, events, report):
    """Check published windows against all samples, including excluded rows."""
    violations = []
    deaths = events.loc[events['event_type'].eq('player_death') &
                        events['player_role'].isin(['victim', 'attacker_and_victim']), 'tick']
    rate = report['assumed_tickrate_hz']
    max_gap = report['data_quality']['max_gap_seconds']
    for window in report['engagements']:
        part = player.loc[player['tick'].between(window['start_tick'], window['end_tick'])]
        reasons = []
        if len(part) < 8 or len(part) != window['samples']:
            reasons.append('sample_count')
        if part.empty or not part['active'].all():
            reasons.append('inactive_samples')
        if part.empty or not part['segment_id'].eq(window['segment_id']).all():
            reasons.append('segment_boundary')
        if part.empty or not part['round_id'].eq(window['round_id']).all():
            reasons.append('round_boundary')
        if not part.empty:
            if part['tick'].iloc[0] != window['start_tick'] or part['tick'].iloc[-1] != window['end_tick']:
                reasons.append('sample_bounds')
            if (np.diff(part['tick']) / rate > max_gap).any():
                reasons.append('recording_gap')
        if deaths.between(window['start_tick'], window['end_tick']).any():
            reasons.append('death_boundary')
        if not window['shot_ticks'] or not all(
                window['start_tick'] <= tick <= window['end_tick'] for tick in window['shot_ticks']):
            reasons.append('shot_bounds')
        actual = events.loc[events['event_type'].eq('weapon_fire') &
                            events['segment_id'].eq(window['segment_id']), 'tick'].tolist()
        # Compare multiplicities too: more than one shot may share a tick.
        if Counter(window['shot_ticks']) - Counter(actual):
            reasons.append('unmatched_shots')
        if not window['features'] or not np.isfinite(list(window['features'].values())).all():
            reasons.append('invalid_features')
        if reasons:
            violations.append({'engagement_id': window['engagement_id'], 'reasons': reasons})
    return violations


def load_manifest(path):
    path = Path(path).resolve()
    jobs = json.loads(path.read_text())
    if not isinstance(jobs, list) or not jobs:
        raise ValueError('Manifest must be a nonempty JSON array')
    normalized = []
    for job in jobs:
        if not isinstance(job, dict) or set(job) != {'demo', 'steamid', 'tickrate'}:
            raise ValueError('Each job must contain demo, steamid, and tickrate only')
        if not isinstance(job['demo'], str) or not job['demo']:
            raise ValueError('demo must be a nonempty path string')
        if not isinstance(job['steamid'], str) or not job['steamid'].isdigit():
            raise ValueError('steamid must be an exact numeric string')
        rate = job['tickrate']
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not np.isfinite(rate) or rate <= 0:
            raise ValueError('tickrate must be finite and positive')
        normalized.append({**job, 'demo': str((path.parent / job['demo']).resolve())})
    pairs = [(j['demo'], j['steamid']) for j in normalized]
    if len(set(pairs)) != len(pairs):
        raise ValueError('Duplicate demo/player jobs are not allowed')
    return normalized


def run_batch(manifest, output, max_plots=3):
    if max_plots < 0:
        raise ValueError('max_plots must be nonnegative')
    jobs = load_manifest(manifest)
    output = Path(output)
    # Refuse reused destinations so stale artifacts cannot look like fresh results.
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for index, job in enumerate(jobs, 1):
        destination = output / f'job_{index:04d}'
        row = {**job, 'artifacts': destination.name}
        stage = 'analysis'
        try:
            report = analyze_demo(job['demo'], job['steamid'], destination,
                                  tickrate=job['tickrate'], max_plots=max_plots)
            stage = 'validation'
            player = pd.read_csv(destination / 'telemetry.csv', dtype={'steamid': str})
            events = pd.DataFrame(json.loads((destination / 'events.json').read_text()))
            if events.empty:
                events = pd.DataFrame(columns=['tick', 'event_type', 'player_role', 'segment_id'])
            violations = validate_windows(player, events, report)
            quality = report['data_quality']
            warnings = []
            if not quality['active_samples']:
                warnings.append('no_active_samples')
            if not report['engagement_count']:
                warnings.append('no_shooting_windows')
            if quality['round_event_anomalies']:
                warnings.append('round_event_anomalies')
            row.update(status='failed' if violations else ('warning' if warnings else 'passed'),
                       source_sha256=report['source_sha256'],
                       active_samples=quality['active_samples'],
                       normalized_samples=quality['normalized_samples'],
                       active_sample_fraction=quality['active_sample_fraction'],
                       segments=quality['segments'], windows=report['engagement_count'],
                       skipped_groups=len(report['skipped_engagements']),
                       excluded_events=quality['events_outside_active_segments'],
                       round_anomalies=quality['round_event_anomalies'],
                       warnings=warnings, violations=violations)
        except Exception as exc:
            # Parser errors must not prevent the remaining matches being evaluated.
            row.update(status='error', error_stage=stage, error_type=type(exc).__name__, error=str(exc))
        results.append(row)
        print(f"{index}/{len(jobs)}: {row['status']} — {Path(job['demo']).name} / {job['steamid']}")
    summary = {
        'schema_version': 1,
        'manifest': str(Path(manifest).resolve()),
        'note': 'Structural validation only; plots require human review. No detection accuracy claims.',
        'jobs': results,
        'counts': {status: sum(r['status'] == status for r in results)
                   for status in ('passed', 'warning', 'failed', 'error')},
        'distinct_successful_replays': len({r['source_sha256'] for r in results
                                            if r['status'] in ('passed', 'warning')}),
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    lines = ['# Replay validation results', '', summary['note'], '',
             '| Job | Replay | Player | Status | Active coverage | Windows |',
             '| --- | --- | --- | --- | --- | --- |']
    for index, row in enumerate(results, 1):
        coverage = f"{row['active_sample_fraction']:.1%}" if 'active_sample_fraction' in row else '—'
        name = Path(row['demo']).name.replace('|', '\\|').replace('\n', ' ')
        lines.append(f"| {index} | {name} | {row['steamid']} | {row['status']} | {coverage} | {row.get('windows', '—')} |")
    lines += ['', 'See summary.json for exclusions, anomalies, errors, and individual window violations.',
              'Inspect each job directory for report.json and representative engagement plots.',
              'Warnings require review; they do not necessarily indicate a segmentation defect.',
              f"Distinct replay contents analyzed: {summary['distinct_successful_replays']}.", '']
    (output / 'summary.md').write_text('\n'.join(lines))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description='Batch CS2 replay validation from a JSON manifest')
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New output directory; must not exist')
    parser.add_argument('--max-plots', type=int, default=3)
    args = parser.parse_args(argv)
    try:
        summary = run_batch(args.manifest, args.output, args.max_plots)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 1 if summary['counts']['failed'] or summary['counts']['error'] else 0


if __name__ == '__main__':
    raise SystemExit(main())

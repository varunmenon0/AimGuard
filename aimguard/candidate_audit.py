"""Post-feedback audit of geometric candidate ambiguity; no fitting or target labels."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.baseline import digest, write_json
from aimguard.gameplay import identity_strings
from aimguard.target_geometry import FIELDS, shot_alignment
from aimguard.target_tracking import prepare, same_shooter_inputs

SAMPLE = ['D-3A', 'R-002', 'R-009', 'L-002', 'L-013', 'D-2A', 'E-05', 'R-020',
          'R-007', 'R-012', 'D-3B', 'E-10', 'R-017', 'D-1A']
LAGS = (0., .1, .2)


def ranked_snapshot(frame, steamid, tick, deaths):
    dead = {str(victim) for victim, death_tick in deaths if death_tick <= tick}
    local = frame.loc[frame.tick.eq(tick) & ~frame.steamid.isin(dead)]
    geometry = shot_alignment(local, steamid, tick, tick-1)
    ranked = sorted(geometry['candidates'], key=lambda row: (row['absolute_yaw_error_degrees'], row['opponent_id']))
    result = dict(tick=int(tick), status=geometry['status'], reason=geometry.get('reason'),
                  candidates=[dict(opponent_id=c['opponent_id'], error_degrees=c['absolute_yaw_error_degrees']) for c in ranked])
    if ranked:
        result.update(nearest=ranked[0]['opponent_id'], nearest_error=ranked[0]['absolute_yaw_error_degrees'],
                      runner_up_gap=ranked[1]['absolute_yaw_error_degrees']-ranked[0]['absolute_yaw_error_degrees'] if len(ranked)>1 else None)
    return result


def compare_snapshots(endpoint, earlier):
    if endpoint['status'] != 'available' or earlier['status'] != 'available':
        return dict(status='unavailable')
    previous = {c['opponent_id']: c['error_degrees'] for c in earlier['candidates']}
    if endpoint['nearest'] not in previous:
        return dict(status='unavailable', reason='endpoint_candidate_missing_earlier')
    return dict(status='available', same_nearest=endpoint['nearest']==earlier['nearest'],
                endpoint_candidate_error_earlier=previous[endpoint['nearest']],
                earlier_nearest_error=earlier['nearest_error'],
                endpoint_selection_excess_earlier=previous[endpoint['nearest']]-earlier['nearest_error'])


def summarize(windows):
    endpoints = [w['snapshots'][0] for w in windows if w['snapshots'][0]['status']=='available']
    margins = [s['runner_up_gap'] for s in endpoints if s['runner_up_gap'] is not None]
    result = dict(windows=len(windows), available_endpoints=len(endpoints),
                  median_valid_opponents=float(np.median([len(s['candidates']) for s in endpoints])) if endpoints else None,
                  median_nearest_error=float(np.median([s['nearest_error'] for s in endpoints])) if endpoints else None,
                  runner_up_available=len(margins), median_runner_up_gap=float(np.median(margins)) if margins else None)
    for index, lag in enumerate(LAGS[1:], 1):
        comparable = [w['comparisons'][index-1] for w in windows if w['comparisons'][index-1]['status']=='available']
        result[f'lag_{lag:g}'] = dict(comparable_windows=len(comparable),
            same_nearest_fraction=float(np.mean([c['same_nearest'] for c in comparable])) if comparable else None,
            median_selection_excess_earlier=float(np.median([c['endpoint_selection_excess_earlier'] for c in comparable])) if comparable else None)
    return result


def analyze(pool, baseline_directory, output):
    from demoparser2 import DemoParser
    pool, baseline_directory, output = map(Path, (pool, baseline_directory, output))
    manifest = json.loads((pool/'manifest.json').read_text()); receipt = json.loads((pool/'pool-receipt.json').read_text())
    baseline = json.loads((baseline_directory/'comparison.json').read_text())
    protocol = json.loads((baseline_directory/'protocol.json').read_text())
    inputs = json.loads((baseline_directory/'inputs.json').read_text())
    if (manifest.get('role')!='development' or manifest.get('features_inspected') is not True
        or receipt['manifest_sha256']!=digest(pool/'manifest.json') or protocol['manifest_sha256']!=digest(pool/'manifest.json')
        or baseline['protocol_sha256']!=digest(baseline_directory/'protocol.json') or baseline['inputs_sha256']!=digest(baseline_directory/'inputs.json')):
        raise ValueError('Inspected pool/baseline receipt mismatch')
    lookup = {case['case_id']:(i, case) for i, case in enumerate(manifest['cases'], 1)}
    predictions = {r['case_id']:r for r in baseline['models']['speed_and_tracking']['predictions']}
    if not set(SAMPLE).issubset(lookup): raise ValueError('Fixed diagnostic sample missing')
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'protocol.json', dict(role='post_feedback_candidate_diagnostic', sample=SAMPLE, lags_seconds=LAGS,
        recorded_at_utc=datetime.now(timezone.utc).isoformat(), code_sha256=digest(__file__),
        manifest_sha256=digest(pool/'manifest.json'), baseline_sha256=digest(baseline_directory/'comparison.json'),
        dependencies={name:importlib.metadata.version(name) for name in ('numpy', 'pandas', 'demoparser2')},
        note='Selected errors plus fixed controls; all windows included. No fit, candidate filtering or classifier revision. Nearest geometry is not intended target/visibility.'))
    cases = []
    for case_id in SAMPLE:
        index, case = lookup[case_id]; prediction = predictions[case_id]
        directory = pool/'analysis'/f'job_{index:04d}'; path = pool/'tracking'/f'case_{index:04d}.json'
        expected = receipt['cases'][index-1]; source = inputs['cases'][index-1]; old = inputs['tracking'][index-1]
        report = json.loads((directory/'report.json').read_text()); tracking = json.loads(path.read_text())
        if (any(row['case_id']!=case_id for row in (expected, source, old, tracking['summary']))
            or digest(directory/'report.json')!=expected['report_sha256'] or digest(directory/'report.json')!=source['report_sha256']
            or digest(path)!=expected['tracking_sha256'] or digest(path)!=old['tracking_sha256']
            or digest(case['demo'])!=case['demo_sha256'] or report['source_sha256']!=case['demo_sha256']
            or report['steamid']!=case['steamid'] or tracking['demo_sha256']!=case['demo_sha256']
            or prediction['label']!=case['label'] or prediction['status']!='scored'):
            raise ValueError('Source identity/checksum mismatch')
        for name in ('report.json', 'telemetry.csv', 'events.json'):
            if digest(directory/name)!=tracking['input_sha256'][name]: raise ValueError('Tracking source checksum mismatch')
        rate = report['assumed_tickrate_hz']
        if not np.isfinite(rate) or rate <= 0: raise ValueError('Invalid tickrate')
        published = report['engagements']
        if len(published)!=len(tracking['windows']): raise ValueError('Window count mismatch')
        requested = sorted({w['shot_ticks'][0]-1-round(lag*rate) for w in published for lag in LAGS
                            if w['shot_ticks'][0]-1-round(lag*rate)>=w['start_tick']})
        parser = DemoParser(case['demo']); frame = prepare(parser.parse_ticks(FIELDS, ticks=requested))
        telemetry = pd.read_csv(directory/'telemetry.csv', dtype={'steamid':str})
        actual = frame.loc[frame.steamid.eq(case['steamid'])].set_index('tick').reindex(requested)
        selected = telemetry.set_index('tick').reindex(requested)
        if not telemetry.steamid.eq(case['steamid']).all() or not same_shooter_inputs(actual, selected):
            raise ValueError('Sparse shooter extraction differs from saved telemetry')
        deaths_frame = parser.parse_event('player_death')
        deaths = list(zip(identity_strings(deaths_frame.user_steamid), deaths_frame.tick)) if len(deaths_frame) else []
        windows = []
        for w, saved in zip(published, tracking['windows']):
            if any(w[k]!=saved[k] for k in ('engagement_id','shot_ticks','weapon','round_id')):
                raise ValueError('Window identity mismatch')
            local_deaths = [(v, t) for v,t in deaths if w['start_tick']<=t<=w['end_tick']]
            snapshots = []
            for lag in LAGS:
                tick = w['shot_ticks'][0]-1-round(lag*rate)
                snapshot = ranked_snapshot(frame, case['steamid'], tick, local_deaths) if tick>=w['start_tick'] else dict(tick=tick,status='unavailable',reason='outside_window',candidates=[])
                snapshots.append(snapshot)
            if snapshots[0].get('nearest')!=saved['nearest_before_first_shot']:
                raise ValueError('Endpoint candidate does not reproduce canonical extraction')
            windows.append(dict(engagement_id=w['engagement_id'], first_shot_tick=w['shot_ticks'][0], weapon=w['weapon'],
                snapshots=snapshots, comparisons=[compare_snapshots(snapshots[0], s) for s in snapshots[1:]]))
        cohort = ('false_flag' if prediction['flagged'] else 'legitimate_control') if case['label']=='legitimate' else ('cheating_control' if prediction['flagged'] else 'missed_cheating')
        record = dict(case_id=case_id, cohort=cohort, label=case['label'], baseline_prediction=prediction, summary=summarize(windows), windows=windows,
            source_sha256=dict(demo=case['demo_sha256'],report=digest(directory/'report.json'),tracking=digest(path)),
            review=str((directory/'review.html').resolve()))
        write_json(output/f'{case_id}.json', record); cases.append({k:v for k,v in record.items() if k!='windows'})
        print(f"{case_id}: {record['summary']['available_endpoints']}/{len(windows)} exact endpoint candidates reproduced", flush=True)
    write_json(output/'summary.json', dict(cases=cases, protocol_sha256=digest(output/'protocol.json'),
        case_sha256={c['case_id']:digest(output/f"{c['case_id']}.json") for c in cases},
        note='Descriptive selected-case diagnosis, not accuracy or target-association validation. Historical decisions unchanged.'))
    lines = ['# Geometric candidate ambiguity audit', '', 'Selected errors and fixed controls; all windows. No fitting or detection changes.', '',
        '| Case | Cohort | Endpoints | Median nearest error | Median runner-up gap | Same candidate 200 ms earlier |',
        '| --- | --- | ---: | ---: | ---: | ---: |']
    def number(value): return 'unavailable' if value is None else f'{value:.3f}'
    for c in cases:
        s=c['summary'];lines.append(f"| {c['case_id']} | {c['cohort']} | {s['available_endpoints']}/{s['windows']} | {number(s['median_nearest_error'])} | {number(s['median_runner_up_gap'])} | {number(s['lag_0.2']['same_nearest_fraction'])} |")
    lines += ['', 'Nearest horizontal candidate and geometric separation do not validate intended target, visibility or eye/head geometry. Stable selection is not proof of cheating. All quantities are descriptive, with missing comparisons retained as unavailable.', '']
    (output/'report.md').write_text('\n'.join(lines)); return cases


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pool',type=Path); parser.add_argument('baseline_directory',type=Path); parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv); analyze(args.pool,args.baseline_directory,args.output)


if __name__=='__main__': main()

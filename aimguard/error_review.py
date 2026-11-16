"""Build an auditable development error queue without changing model decisions."""
import argparse
from collections import Counter
import html
import json
import re
from pathlib import Path

from aimguard.baseline import digest, write_json
from aimguard.review import build_review


def outcome(row):
    if row['status'] != 'scored':
        return 'abstained'
    positive = row['label'] == 'cheating'
    return ('true_positive' if positive else 'false_positive') if row['flagged'] else ('false_negative' if positive else 'true_negative')


def build(manifest_path, analysis_root, diagnostics, output):
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest.get('role') != 'development':
        raise ValueError('Error review requires development data')
    case_ids = [case['case_id'] for case in manifest['cases']]
    if len(set(case_ids)) != len(case_ids) or any(not re.fullmatch(r'[A-Za-z0-9_-]+', value) for value in case_ids):
        raise ValueError('Case IDs must be unique safe filename identifiers')
    diagnostics = Path(diagnostics)
    comparison = json.loads((diagnostics/'comparison.json').read_text())
    protocol = json.loads((diagnostics/'protocol.json').read_text())
    if protocol['manifest_sha256'] != digest(manifest_path):
        raise ValueError('Diagnostic manifest mismatch')
    expected = {r['case_id']:r for r in protocol['cases']}
    models = {name:{r['case_id']:r for r in model['predictions']} for name,model in comparison['models'].items()}
    records = []
    # Validate every input before creating the review directory.
    for index,case in enumerate(manifest['cases'],1):
        source = Path(analysis_root)/f'job_{index:04d}'
        report = json.loads((source/'report.json').read_text())
        if digest(source/'report.json') != expected[case['case_id']]['report_sha256']:
            raise ValueError('Diagnostic report checksum mismatch')
        if report['steamid'] != case['steamid'] or report['source_sha256'] != case['demo_sha256']:
            raise ValueError('Report identity mismatch')
        predictions = {name:rows[case['case_id']] for name,rows in models.items()}
        if any(r['label'] != case['label'] for r in predictions.values()):
            raise ValueError('Prediction label mismatch')
        windows = report['engagements']
        weapons = Counter(w['weapon'] for w in windows)
        records.append(dict(case_id=case['case_id'],label=case['label'],
            predictions={name:dict(outcome=outcome(r),score=r.get('baseline_score')) for name,r in predictions.items()},
            needs_review=any(outcome(r) in ('false_negative','false_positive','abstained') for r in predictions.values()),
            windows=len(windows),shots=sum(w['shot_count'] for w in windows),weapons=dict(weapons),
            windows_with_damage=sum(w['damage_dealt_events']>0 for w in windows),
            windows_with_kills=sum(w['kill_events']>0 for w in windows),
            eligible_windows=expected[case['case_id']]['eligible_windows'],
            data_quality=report['data_quality'],source_directory=str(source.resolve()),
            review_status='unreviewed',causal_explanation=None))
    output = Path(output)
    output.mkdir(parents=True,exist_ok=False)
    for record in records:
        build_review(Path(record['source_directory']),output/f"{record['case_id']}.html")
    write_json(output/'queue.json',dict(role='development_error_review',manifest_sha256=digest(manifest_path),
        comparison_sha256=digest(diagnostics/'comparison.json'),code_sha256=digest(__file__),cases=records,
        note='Queues errors for human inspection. No causal explanation or cheat activation inferred from match labels.'))
    lines=['# Development error review','',
        'All cases remain unreviewed until a person inspects the windows. Counts describe coverage, not the cause of errors.',
        'Prioritize cases missed by both models, then false flags and model disagreements. Match labels do not identify suspicious ticks.',
        '', '| Case | Label | Speed outcome | Timing outcome | Windows | Windows with damage | Weapons |',
        '| --- | --- | --- | --- | ---: | ---: | --- |']
    for r in sorted(records,key=lambda r:(-sum(p['outcome']=='false_negative' for p in r['predictions'].values()),not r['needs_review'],r['case_id'])):
        lines.append(f"| {r['case_id']} | {r['label']} | {r['predictions']['speed_acceleration']['outcome']} | {r['predictions']['timing_direction']['outcome']} | {r['windows']} | {r['windows_with_damage']} | {r['weapons']} |")
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    links=''.join(f'<li><a href="{html.escape(r["case_id"],quote=True)}.html">{html.escape(r["case_id"])}</a> — {"needs inspection" if r["needs_review"] else "comparison case"}</li>' for r in records)
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>AimGuard error review</title><style>body{font:16px system-ui;margin:32px;max-width:1100px}pre{white-space:pre-wrap}li{margin:8px}</style><h1>Development error review</h1><p>Aim trajectory charts, not rendered CS2 gameplay. All cases are initially unreviewed.</p><ul>'+links+'</ul><pre>'+html.escape('\n'.join(lines))+'</pre>')
    print(output/'index.html')
    return records


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('analysis_root',type=Path)
    parser.add_argument('diagnostics',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    build(args.manifest,args.analysis_root,args.diagnostics,args.output)


if __name__=='__main__':
    main()

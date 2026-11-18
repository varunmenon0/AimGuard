"""Audit local replay availability using identities and labels, never model scores."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

from aimguard.baseline import digest, write_json
from aimguard.tracking_baseline import participant_ids
from scripts.acquire_fresh_cases import metadata_labels, unique_exact_id


def classify(participants, blocked, previously_used, labels):
    """Exclude a whole match if any recorded identity overlaps earlier use."""
    overlap = sorted(set(participants) & set(blocked))
    if previously_used:
        return 'previously_used_match', overlap, []
    if overlap:
        return 'participant_overlap', overlap, []
    resolved = []
    for row in labels:
        exact = unique_exact_id(row['steamid'], participants)
        if exact is not None:
            resolved.append(dict(steamid=exact, label='cheating' if row['isCheater'] == '1' else 'legitimate',
                                 source_player_id=row['steamid'], source_label_file=row['source_label_file'],
                                 source_label_sha256=row['source_label_sha256']))
    if not resolved:
        return 'no_uniquely_resolved_source_label', overlap, []
    return 'metadata_eligible_not_yet_reserved', overlap, resolved


def walk_records(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_records(child)


def inventory(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    model_path = root/'outputs/xguardian/offline-v06/frozen/model.json'
    holdout_path = root/'data/external/xguardian/expansion-cohorts-v1/holdout.json'
    consumed_path = holdout_path.with_suffix('.consumed.json')
    original_path = root/'outputs/validation/three-matches-manifest.json'
    model = json.loads(model_path.read_text())
    holdout = json.loads(holdout_path.read_text())
    if not consumed_path.is_file():
        raise ValueError('Expected consumed-holdout receipt; audit protocol needs review')
    blocked = set(model['excluded_participants'])
    used_hashes = {c['demo_sha256'] for c in model['training']}
    for case in holdout['cases']:
        blocked.update(case['participants'])
        used_hashes.add(case['demo_sha256'])
    originals = json.loads(original_path.read_text())
    original_demos = sorted({Path(c['demo']).resolve() for c in originals})
    for demo in original_demos:
        blocked.update(participant_ids(demo))
        used_hashes.add(digest(demo))

    # Cached identities are only reused when bound to the same complete file hash.
    cached = {}
    for case in model['training'] + holdout['cases']:
        cached[case['demo_sha256']] = case['participants']
    metadata_sources = {}
    for path in sorted((root/'data/external/xguardian').rglob('*.json')):
        try:
            value = json.loads(path.read_text())
        except (ValueError, OSError):
            continue
        for case in walk_records(value):
            if case.get('demo_sha256') and case.get('participants'):
                key = case['demo_sha256']
                ids = sorted(set(map(str, case['participants'])))
                if key in cached and sorted(cached[key]) != ids:
                    raise ValueError(f'Conflicting identity receipts: {path}')
                cached[key] = ids
                metadata_sources[str(path)] = digest(path)
    plan_path = root/'data/external/xguardian/expansion-candidates-v3/plan.json'
    plan = json.loads(plan_path.read_text())
    label_paths = list(plan['label_sources'])
    for path, expected in plan['label_sources'].items():
        if digest(path) != expected:
            raise ValueError(f'Source label table changed: {path}')
    labels = metadata_labels(label_paths)
    files = sorted((root/'data').rglob('*.dem'))
    by_hash = defaultdict(list)
    for index, path in enumerate(files, 1):
        by_hash[digest(path)].append(path)
        if index % 20 == 0:
            print(f'Hashed {index}/{len(files)} local replay files', flush=True)
    rows = []
    for index, (sha, paths) in enumerate(sorted(by_hash.items()), 1):
        path = paths[0]
        match = path.name.split('_', 1)[0]
        row = dict(demo_sha256=sha, paths=[str(p) for p in paths], match_id=match,
                   size_bytes=path.stat().st_size)
        try:
            participants = cached.get(sha) or participant_ids(path)
            status, overlap, targets = classify(participants, blocked, sha in used_hashes, labels.get(match, []))
            row.update(participants=participants, status=status, overlap=overlap, labeled_targets=targets,
                       source_label_rows=len(labels.get(match, [])))
        except Exception as exc:
            row.update(status='metadata_error', error=f'{type(exc).__name__}: {exc}')
        rows.append(row)
        # Each checkpoint is immutable; the final inventory is written once.
        write_json(output/f'replay_{index:04d}.json', row)
        print(f'Checked identities {index}/{len(by_hash)}: {path.name}: {row["status"]}', flush=True)

    eligible = [r for r in rows if r['status'] == 'metadata_eligible_not_yet_reserved']
    # Eligibility against prior use does not imply independence from one another.
    edges = []
    for i, a in enumerate(eligible):
        for b in eligible[i+1:]:
            overlap = sorted(set(a['participants']) & set(b['participants']))
            if overlap:
                edges.append(dict(first=a['demo_sha256'], second=b['demo_sha256'], overlap=overlap))
    counts = dict(Counter(r['status'] for r in rows))
    summary = dict(local_file_copies=len(files), unique_replay_hashes=len(rows),
                   duplicate_copies=len(files)-len(rows), replay_status_counts=counts,
                   eligible_labeled_targets=dict(Counter(t['label'] for r in eligible for t in r['labeled_targets'])),
                   eligible_matches=len(eligible), eligible_match_overlap_pairs=len(edges),
                   excluded_identity_count=len(blocked))
    result = dict(schema_version=1, status='complete', recorded_at_utc=datetime.now(timezone.utc).isoformat(),
                  protocol='Metadata and full-file hashes only. No trajectory features, predictions or model fitting.',
                  model_sha256=digest(model_path), consumed_receipt_sha256=digest(consumed_path),
                  holdout_sha256=digest(holdout_path), original_manifest_sha256=digest(original_path),
                  code_sha256=digest(__file__), metadata_sources=metadata_sources,
                  label_sources=plan['label_sources'], summary=summary, replays=rows,
                  eligible_match_overlap_pairs=edges,
                  caveats=['Source labels are player-in-match labels; aimbot subtype/activation is unspecified.',
                           'Eligibility is provisional: reserve a participant-disjoint cohort before scoring.',
                           'All identities, including short numeric server/bot IDs, retain the existing strict exclusion policy.',
                           'Labels cannot be assigned to other players merely because they share a labeled match.',
                           'Original user-provided matches were inspected and have no verified legitimate-player labels.'])
    write_json(output/'inventory.json', result)
    lines = ['# Local evaluation data inventory', '', result['protocol'], '',
             f'- Local files: {len(files)}; distinct full-file hashes: {len(rows)}; duplicate copies: {len(files)-len(rows)}.',
             *[f'- {key}: {value} matches.' for key, value in sorted(counts.items())],
             f'- Eligible source-labeled targets: {summary["eligible_labeled_targets"]}.',
             f'- Eligible matches sharing participants with each other: {len(edges)} pairs.', '',
             'The six reserved legitimate controls have already been consumed and are excluded.', '',
             '## Per-match audit', '', '| Replay | Copies | Status | Overlapping identities | Eligible labels |',
             '| --- | ---: | --- | ---: | --- |']
    for row in rows:
        lines.append(f'| {Path(row["paths"][0]).name} | {len(row["paths"])} | {row["status"]} | '
                     f'{len(row.get("overlap", []))} | {dict(Counter(t["label"] for t in row.get("labeled_targets", [])))} |')
    lines.extend(['', '## Limits', '', *['- '+c for c in result['caveats']]])
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inventory(args.root, args.output)

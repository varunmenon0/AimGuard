"""Bind and consume an additional identity-audited cohort without changing a model."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from aimguard.baseline import digest, write_json
from aimguard.offline_detector import load, now, predict, summarize
from aimguard.gameplay import identity_strings
from aimguard.tracking_baseline import load_model as load_legacy
from scripts.audit_replay_identities import (
    CONTROLLER_ID, account_id, check_disjoint, choose_target, identity_evidence,
)
from scripts.acquire_fresh_cases import metadata_labels

ROLE = 'supplemental_identity_audited_evaluation_v1'
RUNTIME_FILES = ('aimguard/supplemental_evaluation.py', 'scripts/audit_replay_identities.py',
                 'scripts/acquire_fresh_cases.py')


def cohort_key(cases):
    keys = sorted((c['demo_sha256'], c['steamid']) for c in cases)
    return hashlib.sha256(json.dumps(keys, separators=(',', ':')).encode()).hexdigest()


def validate_cases(bundle, cases, blocked):
    """Identity and source labels only; no features are read during admission."""
    from demoparser2 import DemoParser
    used = set(); demos = set(); ids = set()
    sources = {c['source_label_file']: c['source_label_sha256'] for c in cases}
    for path, sha in sources.items():
        if digest(path) != sha:
            raise ValueError('Source label table changed')
    labels = metadata_labels(list(sources))
    for c in cases:
        if c.get('features_inspected') is not False or c['label'] not in ('legitimate', 'cheating'):
            raise ValueError('Require uninspected labeled metadata')
        if c['case_id'] in ids or c['demo_sha256'] in demos or digest(c['demo']) != c['demo_sha256']:
            raise ValueError('Duplicate case/replay or changed demo')
        if digest(c['source_label_file']) != c['source_label_sha256']:
            raise ValueError('Case label receipt changed')
        parser = DemoParser(c['demo']); info = parser.parse_player_info()
        ticks = parser.parse_ticks([CONTROLLER_ID])
        actual = identity_strings(ticks[CONTROLLER_ID])
        if not actual.equals(identity_strings(ticks['steamid'])):
            raise ValueError('Controller identity differs')
        snapshot = set(identity_strings(info['steamid'])) - {''}
        streamed = set(actual) - {''}
        team = parser.parse_event('player_team')
        bots = int((team['isbot'] == True).sum()) if hasattr(team, 'columns') and 'isbot' in team else 0
        proof = identity_evidence(snapshot, streamed, bots)
        if (sorted(snapshot | streamed) != c['participants'] or
                proof['account_participants'] != c['account_participants'] or
                proof['local_non_account_ids'] != c['local_non_account_ids']):
            raise ValueError('Audited identity receipt differs')
        check_disjoint(c['account_participants'], blocked, used)
        target = choose_target(labels.get(c['match_id'], []), c['account_participants'])
        if (target['exact_steamid'] != c['steamid'] or target['steamid'] != c['source_player_id'] or
                ('cheating' if target['isCheater'] == '1' else 'legitimate') != c['label']):
            raise ValueError('Target selection or source label differs')
        used.update(c['account_participants']); demos.add(c['demo_sha256']); ids.add(c['case_id'])
    if not cases:
        raise ValueError('Empty cohort')


def reserve(model, audit, output, registry):
    model, audit, output, registry = map(Path, (model, audit, output, registry))
    bundle = load(model)
    legacy_dir = Path('outputs/xguardian/tracking-baseline-v2/frozen')
    load_legacy(legacy_dir)
    if output.exists():
        raise ValueError('Use a new reservation directory')
    candidate_path = audit/'candidates.json'; candidates = json.loads(candidate_path.read_text())
    plan = json.loads((audit/'plan.json').read_text()); cases = candidates['cases']
    if (candidates.get('role') != 'identity_audited_candidates_not_reserved' or
            candidates.get('features_inspected') is not False or
            candidates['model_sha256'] != digest(model/'model.json') or
            candidates['threshold'] != bundle['threshold'] or
            candidates['plan_sha256'] != digest(audit/'plan.json') or
            plan['code_sha256'] != digest('scripts/audit_replay_identities.py') or
            [c['match_id'] for c in cases] != plan['candidate_match_ids']):
        raise ValueError('Audited candidate/model receipt differs or audit is incomplete')
    proof_paths = sorted(audit.glob('identity_*.json'))
    if len(proof_paths) != len(cases):
        raise ValueError('Incomplete identity evidence')
    for path, case in zip(proof_paths, cases):
        proof = json.loads(path.read_text())
        if (proof['status'] != 'metadata_checks_passed' or proof['match_id'] != case['match_id'] or
                proof['account_participants'] != case['account_participants'] or
                proof['selected_target'] != case['steamid']):
            raise ValueError('Identity audit proof differs')
    prior = Path('data/external/xguardian/expansion-cohorts-v1/holdout.json')
    consumed = prior.with_suffix('.consumed.json')
    if digest(prior) != bundle['reserved_holdout_sha256'] or json.loads(consumed.read_text())['model_sha256'] != digest(model/'model.json'):
        raise ValueError('Original consumed-cohort receipt differs')
    original = Path('outputs/validation/three-matches-inventory.json')
    blocked = {s for s in bundle['excluded_participants'] if account_id(s)}
    blocked.update(s for c in json.loads(prior.read_text())['cases'] for s in c['participants'] if account_id(s))
    blocked.update(str(c['steamid']) for c in json.loads(original.read_text()) if account_id(str(c['steamid'])))
    registry.mkdir(parents=True, exist_ok=True)
    lock = registry/'.lock'
    with lock.open('x') as handle:
        handle.write('Supplemental metadata reservation in progress\n')
    try:
        key = cohort_key(cases)
        if (registry/key).exists():
            raise ValueError('Cohort already reserved or consumed; copies do not restore freshness')
        previous = {}
        for path in sorted(registry.glob('*/reservation.json')):
            record = json.loads(path.read_text()); previous[str(path)] = digest(path)
            blocked.update(s for c in record['cases'] for s in c['account_participants'])
        validate_cases(bundle, cases, blocked)
        record = dict(role=ROLE, reserved_at_utc=now(), model_sha256=digest(model/'model.json'),
            threshold=bundle['threshold'], cohort_key=key, registry=str(registry.resolve()),
            cases=cases, excluded_account_participants=sorted(blocked),
            source_sha256={str(p.resolve()): digest(p) for p in [candidate_path, audit/'plan.json', audit/'output-scan.json', *proof_paths, prior, consumed, original]},
            runtime_sha256={p: digest(p) for p in RUNTIME_FILES}, previous_reservations=previous,
            note='Supplemental evaluation fixed before extraction. Original frozen model and six-case reservation unchanged. All errors/partial runs consume this cohort. Generic cheating labels do not establish active aimbot use.')
        output.mkdir(parents=True, exist_ok=False)
        write_json(output/'reservation.json', record)
        (registry/key).mkdir(exist_ok=False)
        write_json(registry/key/'reservation.json', record)
        # Preserve exclusion compatibility with the existing acquisition command.
        # This receipt authorizes no evaluation with the legacy model.
        exclusion = dict(model_sha256=digest(legacy_dir/'model.json'),
            purpose='supplemental_identity_audited_evaluation_exclusion_only',
            supplemental_model_sha256=record['model_sha256'], cases=cases,
            supplemental_reservation_sha256=digest(output/'reservation.json'),
            features_inspected=False,
            note='Metadata reservation only. All raw identities excluded from future acquisition; not authorization for legacy evaluation.')
        exclusion_dir = legacy_dir/'reservations'
        exclusion_dir.mkdir(exist_ok=True)
        encoded = json.dumps(exclusion, sort_keys=True).encode()
        write_json(exclusion_dir/(hashlib.sha256(encoded).hexdigest()+'.reservation.json'), exclusion)
        print(json.dumps(dict(cohort_key=key, cases=len(cases), labels=dict(Counter(c['label'] for c in cases)))), flush=True)
        return record
    finally:
        lock.unlink()


def evaluate(model, reservation, output):
    model, reservation, output = map(Path, (model, reservation, output))
    record = json.loads(reservation.read_text()); bundle = load(model)
    if record.get('role') != ROLE or record['model_sha256'] != digest(model/'model.json') or record['threshold'] != bundle['threshold']:
        raise ValueError('Reserved model/threshold differs')
    key = cohort_key(record['cases'])
    canonical = Path(record['registry'])/key
    if key != record['cohort_key'] or digest(reservation) != digest(canonical/'reservation.json'):
        raise ValueError('Reservation differs from canonical registry')
    consumed = canonical/'consumed.json'
    if consumed.exists():
        raise ValueError('Supplemental cohort consumed; do not evaluate again')
    if output.exists():
        raise ValueError('Use a new evaluation output')
    for path, sha in {**record['source_sha256'], **record['runtime_sha256']}.items():
        if digest(path) != sha:
            raise ValueError('Reserved source/runtime changed: '+path)
    validate_cases(bundle, record['cases'], set(record['excluded_account_participants']))
    receipt = dict(started_at_utc=now(), reservation_sha256=digest(reservation),
        model_sha256=record['model_sha256'], cohort_key=key, output=str(output.resolve()),
        note='Consumed before trajectory extraction, including errors and interrupted runs; source metadata remains historical.')
    write_json(consumed, receipt)
    output.mkdir(parents=True, exist_ok=False); write_json(output/'start.json', receipt)
    rows = []
    for i, case in enumerate(record['cases'], 1):
        try:
            result = predict(model, case['demo'], case['steamid'], output/f'case_{i:03d}')
        except Exception as error:
            result = dict(status='error', score=None, flagged=None, error_type=type(error).__name__, error=str(error))
        row = dict(result, case_id=case['case_id'], label=case['label']); rows.append(row)
        write_json(output/f'prediction_{i:03d}.json', row)
        print(case['case_id'], row['status'], flush=True)
    summary = summarize(rows)
    summary['caveat'] = 'Small archive convenience sample: six legitimate labels and one generic cheating label. No active-aimbot annotation. Conditional bounds assume representative independent correctly labeled cases. Unresolved cases are not correct negatives. Keep separate from development and the earlier six controls.'
    result = dict(summary=summary, predictions=rows, model_sha256=record['model_sha256'],
        reservation_sha256=digest(reservation), consumption_sha256=digest(consumed), cohort_key=key)
    write_json(output/'evaluation.json', result)
    lines = ['# Supplemental frozen-model evaluation', '', json.dumps(summary, indent=2), '',
        '| Case | Source label | Score | Decision |', '| --- | --- | ---: | --- |']
    lines.extend(f'| {r["case_id"]} | {r["label"]} | {r.get("score")} | {r["status"]} |' for r in rows)
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    load(model)
    print(json.dumps(summary), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    r = commands.add_parser('reserve'); r.add_argument('model', type=Path); r.add_argument('audit', type=Path)
    r.add_argument('--output', type=Path, required=True); r.add_argument('--registry', type=Path, required=True)
    e = commands.add_parser('evaluate'); e.add_argument('model', type=Path); e.add_argument('reservation', type=Path)
    e.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'reserve':
        reserve(args.model, args.audit, args.output, args.registry)
    else:
        evaluate(args.model, args.reservation, args.output)

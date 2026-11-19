"""Metadata admission for mixed-label, match-grouped frozen-model evaluation."""
import argparse
import hashlib
import json
from pathlib import Path

from aimguard.baseline import digest, write_json
from aimguard.gameplay import identity_strings
from aimguard.offline_detector import load
from aimguard.tracking_baseline import load_model
from scripts.acquire_fresh_cases import metadata_labels, unique_exact_id
from scripts.audit_replay_identities import CONTROLLER_ID, account_id, identity_evidence

ROLE = 'mixed_grouped_evaluation_candidates_v1'


def prior_accounts(bundle):
    blocked = {s for s in bundle['excluded_participants'] if account_id(s)}
    hold = Path('data/external/xguardian/expansion-cohorts-v1/holdout.json')
    if digest(hold) != bundle['reserved_holdout_sha256'] or not hold.with_suffix('.consumed.json').exists():
        raise ValueError('Original consumed holdout receipt differs')
    for case in json.loads(hold.read_text())['cases']:
        blocked.update(s for s in case['participants'] if account_id(s))
    for path in Path('data/external/xguardian/supplemental-evaluation-registry-v1').glob('*/reservation.json'):
        for case in json.loads(path.read_text())['cases']:
            blocked.update(case['account_participants'])
    return blocked


def validate(cases, groups, blocked):
    """Read identities and labels only. Allow both classes inside one match group."""
    from demoparser2 import DemoParser
    by_id = {c['case_id']: c for c in cases}
    if not cases or len(by_id) != len(cases):
        raise ValueError('Empty or duplicate cases')
    sources = {c['source_label_file']: c['source_label_sha256'] for c in cases}
    for path, sha in sources.items():
        if digest(path) != sha:
            raise ValueError('Source labels changed')
    labels = metadata_labels(list(sources))
    seen = set(); accounts = set(); demos = set(); group_ids = set()
    for group in groups:
        gid = group['group_id']; members = group['case_ids']
        if gid in group_ids or not members or len(set(members)) != len(members):
            raise ValueError('Duplicate or empty match group')
        if any(cid not in by_id or cid in seen for cid in members):
            raise ValueError('Missing or multiply grouped cases')
        rows = [by_id[cid] for cid in members]; first = rows[0]
        if first['demo_sha256'] in demos or digest(first['demo']) != first['demo_sha256']:
            raise ValueError('Duplicate grouped replay or changed replay')
        parser = DemoParser(first['demo']); info = parser.parse_player_info()
        ticks = parser.parse_ticks([CONTROLLER_ID]); actual = identity_strings(ticks[CONTROLLER_ID])
        if not actual.equals(identity_strings(ticks['steamid'])):
            raise ValueError('Controller identity mismatch')
        snapshot = set(identity_strings(info['steamid'])) - {''}; streamed = set(actual) - {''}
        team = parser.parse_event('player_team')
        bots = int((team['isbot'] == True).sum()) if hasattr(team, 'columns') and 'isbot' in team else 0
        proof = identity_evidence(snapshot, streamed, bots); humans = set(proof['account_participants'])
        if humans != set(group['account_participants']) or humans & (set(blocked) | accounts):
            raise ValueError('Prior or cross-group participant overlap/identity mismatch')
        targets = set()
        for case in rows:
            if case['source_label_sha256'] != sources[case['source_label_file']]:
                raise ValueError('Inconsistent source label hashes')
            if (case['group_id'] != gid or case['match_id'] != group['match_id'] or
                    case['demo_sha256'] != first['demo_sha256'] or Path(case['demo']).resolve() != Path(first['demo']).resolve() or
                    case['participants'] != sorted(snapshot | streamed) or
                    case['account_participants'] != proof['account_participants'] or
                    case['local_non_account_ids'] != proof['local_non_account_ids'] or
                    case.get('features_inspected') is not False or case['label'] not in ('legitimate', 'cheating') or
                    case['steamid'] in targets or case['steamid'] not in humans):
                raise ValueError('Case/group receipt, target, label or inspection mismatch')
            source = [r for r in labels.get(case['match_id'], []) if r['steamid'] == case['source_player_id']]
            expected = '0' if case['label'] == 'legitimate' else '1'
            if (len(source) != 1 or source[0]['isCheater'] != expected or
                    unique_exact_id(case['source_player_id'], proof['account_participants']) != case['steamid']):
                raise ValueError('Exact source label or target differs')
            targets.add(case['steamid']); seen.add(case['case_id'])
        group_ids.add(gid); accounts.update(humans); demos.add(first['demo_sha256'])
    if seen != set(by_id):
        raise ValueError('Ungrouped cases')


def register_positive(directory):
    directory = Path(directory); path = directory/'candidates.json'
    manifest = json.loads(path.read_text()); plan = json.loads((directory/'plan.json').read_text())
    model = Path('outputs/xguardian/offline-v06/frozen'); bundle = load(model)
    if (manifest['role'] != 'cheating_evaluation_candidates_not_reserved' or
            manifest['model_sha256'] != digest(model/'model.json') or manifest['threshold'] != bundle['threshold'] or
            manifest['plan_sha256'] != digest(directory/'plan.json') or
            plan['code_sha256'] != digest('scripts/acquire_cheating_cohort.py')):
        raise ValueError('Positive acquisition provenance differs')
    for file, sha in {**plan['source_label_sha256'], **plan['helper_sha256']}.items():
        if digest(file) != sha:
            raise ValueError('Positive acquisition source changed')
    if not manifest['cases']:
        return None
    if any(c['label'] != 'cheating' for c in manifest['cases']):
        raise ValueError('Expected explicit positive labels')
    validate(manifest['cases'], manifest['groups'], plan['excluded_account_participants'])
    legacy = Path('outputs/xguardian/tracking-baseline-v2/frozen'); load_model(legacy)
    record = dict(model_sha256=digest(legacy/'model.json'), purpose='positive_acquisition_exclusion_only',
        supplemental_model_sha256=manifest['model_sha256'], cases=manifest['cases'], features_inspected=False,
        candidate_sha256=digest(path), plan_sha256=digest(directory/'plan.json'),
        note='Metadata exclusion only, not evaluation authorization. Generic cheating label; subtype/activation unknown.')
    name = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()+'.reservation.json'
    target = legacy/'reservations'/name
    if not target.exists():
        write_json(target, record)
    elif json.loads(target.read_text()) != record:
        raise ValueError('Registry differs')
    receipt = dict(candidate_sha256=digest(path), registry_receipt=str(target.resolve()), registry_sha256=digest(target))
    pointer = directory/'positive-exclusion.json'
    if not pointer.exists():
        write_json(pointer, receipt)
    elif json.loads(pointer.read_text()) != receipt:
        raise ValueError('Positive exclusion receipt differs')
    return receipt


def build(negative, positives, output):
    negative, output = map(Path, (negative, output))
    if output.exists():
        raise ValueError('Use a new mixed collection directory')
    model = Path('outputs/xguardian/offline-v06/frozen'); bundle = load(model)
    negpath = negative/'collection.json'; neg = json.loads(negpath.read_text())
    if (neg['role'] != 'grouped_legitimate_evaluation_collection_not_reserved' or
            neg['model_sha256'] != digest(model/'model.json') or neg.get('features_inspected') is not False or
            len(neg['cases']) != 50 or any(c['label'] != 'legitimate' for c in neg['cases'])):
        raise ValueError('Require the unchanged unscored 50-control collection')
    verification = json.loads((negative/'verification.json').read_text())
    if verification['collection_sha256'] != digest(negpath):
        raise ValueError('Control verification differs')
    cases = [dict(c) for c in neg['cases']]
    groups = [dict(g, case_ids=list(g['case_ids'])) for g in neg['groups']]
    sources = {str(p.resolve()): digest(p) for p in [negpath, negative/'verification.json']}
    label_files = list(dict.fromkeys(c['source_label_file'] for c in cases))
    labels = metadata_labels(label_files); shared = 0
    # All explicit positives in the unscored control matches; no score-based choice.
    for group in groups:
        base = next(c for c in cases if c['group_id'] == group['group_id'])
        for row in sorted(labels.get(group['match_id'], []), key=lambda r: r['steamid']):
            exact = unique_exact_id(row['steamid'], group['account_participants'])
            if row['isCheater'] != '1' or exact is None:
                continue
            shared += 1; cid = f'P-SHARED-{shared:03d}'
            cases.append(dict(base, case_id=cid, steamid=exact, label='cheating',
                source_player_id=row['steamid'], source_label_file=row['source_label_file'],
                source_label_sha256=row['source_label_sha256'], source_case_id=None,
                source_manifest=row['source_label_file'], label_scope='Generic source cheating label; active aimbot and activation ticks unknown'))
            group['case_ids'].append(cid)
    for index, directory in enumerate(map(Path, positives), 1):
        path = directory/'candidates.json'; m = json.loads(path.read_text())
        if (m['role'] != 'cheating_evaluation_candidates_not_reserved' or
                m['model_sha256'] != neg['model_sha256'] or m.get('features_inspected') is not False):
            raise ValueError('Positive acquisition metadata differs')
        if not m['cases']:
            sources.update({str(p.resolve()): digest(p) for p in (path, directory/'plan.json')})
            continue
        receipt_path = directory/'positive-exclusion.json'; receipt = json.loads(receipt_path.read_text())
        if (m['role'] != 'cheating_evaluation_candidates_not_reserved' or m['model_sha256'] != neg['model_sha256'] or
                receipt['candidate_sha256'] != digest(path) or receipt['registry_sha256'] != digest(receipt['registry_receipt'])):
            raise ValueError('Positive source/exclusion differs')
        prefix = f'P{index}'
        for c in m['cases']:
            cases.append(dict(c, case_id=prefix+'-'+c['case_id'], group_id=prefix+'-'+c['group_id'],
                source_case_id=c['case_id'], source_manifest=str(path.resolve())))
        for g in m['groups']:
            groups.append(dict(g, group_id=prefix+'-'+g['group_id'], case_ids=[prefix+'-'+cid for cid in g['case_ids']]))
        sources.update({str(p.resolve()): digest(p) for p in (path, directory/'plan.json', receipt_path)})
    validate(cases, groups, prior_accounts(bundle))
    original = {(c['demo_sha256'], c['steamid'], c['label']) for c in neg['cases']}
    if original != {(c['demo_sha256'], c['steamid'], c['label']) for c in cases if c['label']=='legitimate'}:
        raise ValueError('Control targets changed')
    output.mkdir(parents=True, exist_ok=False)
    result = dict(role=ROLE, features_inspected=False, cases=cases, groups=groups,
        model_sha256=neg['model_sha256'], threshold=bundle['threshold'], source_sha256=sources,
        preparation_code_sha256=digest(__file__),
        note='Original 50 controls unchanged; all uniquely mapped positives in their unscored matches added to the same groups. Extra positive matches selected by source metadata only. Generic cheating labels do not confirm active aimbot use.')
    write_json(output/'collection.json', result)
    counts = {label:sum(c['label']==label for c in cases) for label in ('legitimate','cheating')}
    write_json(output/'summary.json', dict(labels=counts, match_groups=len(groups), shared_match_positive_targets=shared, scored=0))
    print(json.dumps(dict(labels=counts, match_groups=len(groups), shared_positive_targets=shared)), flush=True)
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('register-positive');r.add_argument('directory',type=Path)
    b=sub.add_parser('build');b.add_argument('negative',type=Path);b.add_argument('--positive',action='append',type=Path,default=[]);b.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.command=='register-positive': print(json.dumps(register_positive(a.directory)))
    else: build(a.negative,a.positive,a.output)

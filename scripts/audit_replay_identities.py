"""Review short-ID exclusions with identity metadata; never score a replay."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from aimguard.baseline import digest, write_json
from aimguard.gameplay import identity_strings
from aimguard.offline_detector import load
from scripts.acquire_fresh_cases import metadata_labels, unique_exact_id

PUBLIC_INDIVIDUAL_DESKTOP = 0x0110000100000000
CONTROLLER_ID = 'CCSPlayerController.m_steamID'


def account_id(value):
    """Recognize public individual desktop SteamID64, not arbitrary decimal IDs."""
    if not isinstance(value, str) or not value.isdigit():
        return False
    number = int(value)
    return number >> 32 == PUBLIC_INDIVIDUAL_DESKTOP >> 32 and number & 0xffffffff != 0


def identity_evidence(snapshot, controller, bot_events):
    """Keep every account seen in either stream; quarantine unfamiliar identities."""
    snapshot, controller = set(snapshot), set(controller)
    identities = snapshot | controller
    humans = {s for s in identities if account_id(s)}
    local = identities - humans
    if not humans:
        raise ValueError('No account identities')
    if any(not s.isdigit() or not 0 < int(s) < 65536 for s in local):
        raise ValueError('Unsupported identity type; do not silently discard it')
    if local & controller:
        raise ValueError('Non-account ID appears in controller stream; unresolved')
    if local and bot_events < len(local):
        raise ValueError('Missing corroborating bot metadata')
    return dict(account_participants=sorted(humans), local_non_account_ids=sorted(local),
                interpretation='Local non-account snapshot IDs with bot-event corroboration; not cross-match human keys. Exact bot-to-ID mapping is unavailable.')


def choose_target(rows, participants):
    resolved = []
    for row in rows:
        exact = unique_exact_id(row['steamid'], participants)
        if exact is not None and account_id(exact):
            resolved.append(dict(row, exact_steamid=exact))
    if not resolved:
        raise ValueError('No uniquely mapped account label')
    # Fixed metadata-only order: one target per match, positive first, then hash.
    return sorted(resolved, key=lambda r: (r['isCheater'] != '1',
                  hashlib.sha256((r['match_id'] + r['steamid']).encode()).hexdigest()))[0]


def check_disjoint(participants, blocked, used):
    overlap = set(participants) & (set(blocked) | set(used))
    if overlap:
        raise ValueError('Account participant overlap: ' + ','.join(sorted(overlap)))


def audit(inventory_path, output):
    from demoparser2 import DemoParser
    inventory_path, output = Path(inventory_path), Path(output)
    inventory = json.loads(inventory_path.read_text())
    if inventory.get('status') != 'complete':
        raise ValueError('Require completed inventory')
    model_dir = Path('outputs/xguardian/offline-v06/frozen')
    bundle = load(model_dir)
    if digest(model_dir/'model.json') != inventory['model_sha256']:
        raise ValueError('Inventory belongs to another model')
    holdout = Path('data/external/xguardian/expansion-cohorts-v1/holdout.json')
    if digest(holdout) != inventory['holdout_sha256'] or digest(holdout.with_suffix('.consumed.json')) != inventory['consumed_receipt_sha256']:
        raise ValueError('Consumed-control provenance differs')
    blocked_raw = set(bundle['excluded_participants'])
    for c in json.loads(holdout.read_text())['cases']:
        blocked_raw.update(c['participants'])
    original = Path('outputs/validation/three-matches-inventory.json')
    blocked_raw.update(str(c['steamid']) for c in json.loads(original.read_text()))
    blocked = {s for s in blocked_raw if account_id(s)}
    unsupported = {s for s in blocked_raw if not account_id(s) and (not s.isdigit() or not 0 < int(s) < 65536)}
    if unsupported:
        raise ValueError('Unsupported inspected identity types')
    rows = [r for r in inventory['replays'] if r['status'] == 'participant_overlap'
            and r['overlap'] and all(s.isdigit() and 0 < int(s) < 65536 for s in r['overlap'])]
    rows.sort(key=lambda r: r['match_id'])
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'plan.json', dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        inventory_sha256=digest(inventory_path), model_sha256=digest(model_dir/'model.json'),
        code_sha256=digest(__file__), threshold=bundle['threshold'],
        candidate_match_ids=[r['match_id'] for r in rows],
        selection='All short-only exclusions, match-ID order; one target/match, cheating label first then SHA256(match+source token). No feature/score selection.',
        policy='Recognize public individual desktop accounts by SteamID64 fields. Preserve all account IDs from either identity stream. Allow small non-account snapshot IDs only when absent from controller stream and corroborated by bot events. Other formats fail closed.',
        boundary='Audit and future-evaluation candidates only; no model or legacy exclusions changed. Not an authorization to bypass the original bound single-use evaluator.'))
    for path, sha in inventory['label_sources'].items():
        if digest(path) != sha:
            raise ValueError('Label source changed')
    labels = metadata_labels(list(inventory['label_sources']))

    # Scan output bytes for prior use without reading any model scores into selection.
    needles = {r['match_id']: (r['match_id'].encode(), r['demo_sha256'].encode()) for r in rows}
    prior_hits = {}; scanned = {}
    for path in sorted(Path('outputs').rglob('*.json')):
        if any(part.startswith('evaluation-inventory-') for part in path.parts) or output.resolve() in path.resolve().parents:
            continue
        data = path.read_bytes(); scanned[str(path)] = hashlib.sha256(data).hexdigest()
        for match, tokens in needles.items():
            if any(t in data for t in tokens):
                prior_hits.setdefault(match, []).append(str(path))
    cases = []; evidence = []; used = set()
    for index, row in enumerate(rows, 1):
        try:
            if row['match_id'] in prior_hits:
                raise ValueError('Prior output references: ' + str(prior_hits[row['match_id']]))
            demo = Path(row['paths'][0])
            if digest(demo) != row['demo_sha256']:
                raise ValueError('Demo changed')
            parser = DemoParser(str(demo))
            info = parser.parse_player_info()
            controller = parser.parse_ticks([CONTROLLER_ID])
            # Require the exported identity to match the actual controller field.
            actual = identity_strings(controller[CONTROLLER_ID])
            exported = identity_strings(controller['steamid'])
            if not actual.equals(exported):
                raise ValueError('Controller/exported identity mismatch')
            snapshot = set(identity_strings(info['steamid'])) - {''}
            streamed = set(actual) - {''}
            if snapshot | streamed != set(row['participants']):
                raise ValueError('Inventory identity coverage differs')
            team = parser.parse_event('player_team')
            bot_events = int((team['isbot'] == True).sum()) if hasattr(team, 'columns') and 'isbot' in team else 0
            proof = identity_evidence(snapshot, streamed, bot_events)
            humans = proof['account_participants']
            check_disjoint(humans, blocked, used)
            target = choose_target(labels.get(row['match_id'], []), humans)
            case = dict(case_id=f'I-{index:03d}', match_id=row['match_id'], demo=str(demo.resolve()),
                demo_sha256=row['demo_sha256'], steamid=target['exact_steamid'],
                label='cheating' if target['isCheater'] == '1' else 'legitimate',
                participants=sorted(snapshot | streamed), account_participants=humans,
                local_non_account_ids=proof['local_non_account_ids'], features_inspected=False,
                source_label_file=target['source_label_file'], source_label_sha256=target['source_label_sha256'],
                source_player_id=target['steamid'], label_scope='Source player-in-match label; subtype and activation unknown')
            proof.update(match_id=row['match_id'], status='metadata_checks_passed', bot_team_events=bot_events,
                snapshot_records=json.loads(info.to_json(orient='records')), controller_account_ids=sorted(streamed),
                prior_output_references=[], selected_target=case['steamid'])
            cases.append(case); used.update(humans)
        except Exception as exc:
            proof = dict(match_id=row['match_id'], status='unresolved', error=f'{type(exc).__name__}: {exc}')
        evidence.append(proof)
        write_json(output/f'identity_{index:03d}.json', proof)
        print(row['match_id'], proof['status'], flush=True)
    write_json(output/'output-scan.json', dict(files=scanned, prior_hits=prior_hits))
    manifest = dict(role='identity_audited_candidates_not_reserved', features_inspected=False,
        model_sha256=digest(model_dir/'model.json'), threshold=bundle['threshold'],
        plan_sha256=digest(output/'plan.json'), cases=cases,
        note='No scores or trajectories inspected. Needs a separately bound single-use evaluation protocol; original six-control manifest remains consumed.')
    write_json(output/'candidates.json', manifest)
    summary = dict(candidate_matches=len(rows), metadata_passed=len(cases), unresolved=len(rows)-len(cases),
        selected_labels=dict(Counter(c['label'] for c in cases)), disjoint_account_participants=len(used),
        inspected_account_exclusions=len(blocked), prior_output_json_files_scanned=len(scanned))
    write_json(output/'summary.json', summary)
    lines = ['# Short-ID identity audit', '', 'Metadata only: no scores or trajectory features.', '',
             *[f'- {k}: {v}' for k, v in summary.items()], '',
             'Small IDs are local non-account snapshot identifiers with bot-event corroboration. The parser does not expose an exact bot-to-short-ID link here, so this is not a claim of such a mapping.', '',
             'All selected account participants are disjoint from prior inspected/consumed identities and from one another across matches. Prior output references block admission. One source-labeled target is selected per match before scoring.', '',
             'The frozen model, cutoff, legacy exclusions and consumed six-control run remain unchanged. Candidates are not reserved or scored. A separate bound single-use evaluation protocol is required.']
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    load(model_dir)
    print(json.dumps(summary, indent=2), flush=True)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit(args.inventory, args.output)

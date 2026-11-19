"""Verify acquired legitimate labels and match groups without extracting features."""
import argparse
from collections import Counter
import json
from pathlib import Path

from aimguard.baseline import digest, write_json
from aimguard.offline_detector import load
from scripts.acquire_fresh_cases import metadata_labels, unique_exact_id
from scripts.acquire_legitimate_cohort import select_labels


def verify_groups(cases, groups, blocked):
    by_id = {c['case_id']: c for c in cases}
    if len(by_id) != len(cases):
        raise ValueError('Duplicate case identity')
    seen_cases = set(); seen_accounts = set(); seen_demos = set(); seen_groups = set()
    for group in groups:
        members = group['case_ids']; gid = group['group_id']
        if gid in seen_groups or not 1 <= len(members) <= 2 or len(set(members)) != len(members):
            raise ValueError('Invalid match group or player cap')
        accounts = set(group['account_participants'])
        if accounts & (set(blocked) | seen_accounts):
            raise ValueError('Cross-match or prior account overlap')
        hashes = set(); targets = set()
        for cid in members:
            if cid not in by_id or cid in seen_cases:
                raise ValueError('Missing or multiply assigned case')
            case = by_id[cid]
            if (case['group_id'] != gid or case['match_id'] != group['match_id'] or
                    set(case['account_participants']) != accounts or
                    case['steamid'] not in accounts or case['steamid'] in targets or
                    case['label'] != 'legitimate' or case.get('features_inspected') is not False):
                raise ValueError('Case/group identity, label or inspection mismatch')
            hashes.add(case['demo_sha256']); targets.add(case['steamid']); seen_cases.add(cid)
        if len(hashes) != 1 or hashes & seen_demos:
            raise ValueError('Replay must belong to exactly one match group')
        seen_groups.add(gid); seen_demos.update(hashes); seen_accounts.update(accounts)
    if seen_cases != set(by_id):
        raise ValueError('Ungrouped cases')
    return len(seen_accounts)


def report(directory):
    directory = Path(directory); manifest = json.loads((directory/'candidates.json').read_text())
    plan = json.loads((directory/'plan.json').read_text())
    if (manifest['role'] != 'grouped_legitimate_evaluation_candidates_not_reserved' or
            manifest.get('features_inspected') is not False or
            manifest['plan_sha256'] != digest(directory/'plan.json') or
            plan['code_sha256'] != digest('scripts/acquire_legitimate_cohort.py')):
        raise ValueError('Acquisition source/protocol differs')
    bundle = load('outputs/xguardian/offline-v06/frozen')
    if manifest['model_sha256'] != digest('outputs/xguardian/offline-v06/frozen/model.json') or manifest['threshold'] != bundle['threshold']:
        raise ValueError('Frozen model differs')
    for path, sha in {**plan['source_label_sha256'], **plan['helper_sha256']}.items():
        if digest(path) != sha:
            raise ValueError('Bound metadata/runtime changed')
    cases, groups = manifest['cases'], manifest['groups']
    account_count = verify_groups(cases, groups, plan['excluded_account_participants'])
    labels = metadata_labels(list(plan['source_label_sha256']))
    remaining = plan['target_legitimate_players']
    for group in groups:
        members = [c for c in cases if c['group_id'] == group['group_id']]
        selected = select_labels(labels[group['match_id']], group['account_participants'], remaining)
        if [r['exact_steamid'] for r in selected] != [c['steamid'] for c in members]:
            raise ValueError('Metadata selection order differs')
        remaining -= len(members)
        first = members[0]
        if digest(first['demo']) != first['demo_sha256']:
            raise ValueError('Replay changed')
        for c in members:
            rows = [r for r in labels[c['match_id']] if r['steamid'] == c['source_player_id']]
            if len(rows) != 1 or rows[0]['isCheater'] != '0' or unique_exact_id(c['source_player_id'], c['account_participants']) != c['steamid']:
                raise ValueError('Legitimate label/identity mismatch')
    summary = json.loads((directory/'summary.json').read_text())
    if summary['labeled_legitimate_players'] != len(cases) or summary['match_groups'] != len(groups):
        raise ValueError('Summary counts differ')
    verification = dict(candidates_sha256=digest(directory/'candidates.json'),plan_sha256=digest(directory/'plan.json'),
        legitimate_players=len(cases),match_groups=len(groups),account_participants=account_count,
        unfilled_target=max(0,remaining),runtime='frozen model unchanged',features_or_scores_extracted=False)
    write_json(directory/'verification.json',verification)
    lines = ['# Legitimate-player acquisition', '',
        f'Acquisition status: {manifest["acquisition_status"]}.', '',
        f'- Individually source-labeled legitimate players: {len(cases)} / {plan["target_legitimate_players"]}.',
        f'- Participant-disjoint match groups: {len(groups)}.',
        f'- Players per match: {dict(Counter(len(g["case_ids"]) for g in groups))}.',
        f'- Previously unseen account participants in selected matches: {account_count}.',
        f'- Additional compressed bytes cached: {summary["additional_cached_bytes"]}.',
        f'- Remaining target: {max(0,remaining)} players.', '',
        'No scoring, fitting or trajectory extraction. Candidates are not yet reserved for evaluation.', '',
        'Labels belong to the named player in that match; teammates are not assumed legitimate. Players within one match form a group and must not be counted as independent validation observations. This is an archive convenience sample with no verified skill-level annotations.', '',
        '| Group | Match | Labeled players |', '| --- | --- | ---: |']
    lines.extend(f'| {g["group_id"]} | {g["match_id"]} | {len(g["case_ids"])} |' for g in groups)
    (directory/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(verification,indent=2)); return verification


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    report(parser.parse_args().directory)

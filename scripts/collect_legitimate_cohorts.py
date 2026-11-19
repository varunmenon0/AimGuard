"""Join verified unscored acquisition slices while preserving match groups."""
import argparse
import json
from pathlib import Path

from aimguard.baseline import digest, write_json
from aimguard.offline_detector import load
from scripts.report_legitimate_cohort import verify_groups


def collect(directories, output, target=50):
    output=Path(output)
    if output.exists():
        raise ValueError('Use a new collection output')
    model=Path('outputs/xguardian/offline-v06/frozen');bundle=load(model)
    model_hash=digest(model/'model.json');cases=[];groups=[];parts=[];blocked=None
    for index,directory in enumerate(map(Path,directories),1):
        path=directory/'candidates.json';manifest=json.loads(path.read_text())
        verification=json.loads((directory/'verification.json').read_text())
        exclusion=json.loads((directory/'acquisition-exclusion.json').read_text())
        plan=json.loads((directory/'plan.json').read_text())
        if (manifest['role']!='grouped_legitimate_evaluation_candidates_not_reserved' or
                manifest.get('features_inspected') is not False or manifest['model_sha256']!=model_hash or
                manifest['threshold']!=bundle['threshold'] or verification['candidates_sha256']!=digest(path) or
                verification['plan_sha256']!=digest(directory/'plan.json') or
                exclusion['candidates_sha256']!=digest(path) or
                exclusion['registry_sha256']!=digest(exclusion['registry_receipt'])):
            raise ValueError('Acquisition verification, exclusion or model differs')
        verify_groups(manifest['cases'],manifest['groups'],plan['excluded_account_participants'])
        if blocked is None:
            blocked=set(plan['excluded_account_participants'])
        prefix=f'B{index}'
        for c in manifest['cases']:
            cases.append(dict(c,case_id=prefix+'-'+c['case_id'],group_id=prefix+'-'+c['group_id'],
                              source_case_id=c['case_id'],source_manifest=str(path.resolve())))
        for g in manifest['groups']:
            groups.append(dict(g,group_id=prefix+'-'+g['group_id'],case_ids=[prefix+'-'+cid for cid in g['case_ids']]))
        parts.append(dict(directory=str(directory.resolve()),players=len(manifest['cases']),matches=len(manifest['groups']),
                          source_sha256={str(p.resolve()):digest(p) for p in (path,directory/'plan.json',directory/'verification.json',directory/'acquisition-exclusion.json')}))
    if len(cases)!=target:
        raise ValueError(f'Expected {target} labeled players, found {len(cases)}')
    accounts=verify_groups(cases,groups,blocked or set())
    for c in cases:
        if digest(c['source_label_file'])!=c['source_label_sha256']:
            raise ValueError('Source labels changed')
    output.mkdir(parents=True,exist_ok=False)
    collection=dict(role='grouped_legitimate_evaluation_collection_not_reserved',features_inspected=False,
        model_sha256=model_hash,threshold=bundle['threshold'],cases=cases,groups=groups,parts=parts,
        excluded_account_participants=sorted(blocked or set()),code_sha256=digest(__file__),
        note='Metadata-only selection; no scores or trajectories inspected. Labels belong to individual players in their matches. Preserve match groups; players within a match are not independent validation observations. Requires a separately bound single-use group-aware evaluation protocol.')
    write_json(output/'collection.json',collection)
    write_json(output/'summary.json',dict(labeled_legitimate_players=len(cases),match_groups=len(groups),
        distinct_account_participants=accounts,scored_players=0,model_or_threshold_changed=False,
        collection_sha256=digest(output/'collection.json')))
    lines=['# Unscored legitimate-player evaluation collection','',
        f'**{len(cases)} individually source-labeled legitimate players from {len(groups)} participant-disjoint matches.**','',
        f'Selected matches contain {accounts} distinct account participants. Only the explicitly labeled targets are treated as legitimate controls.', '',
        'The existing model and 0.75 cutoff are unchanged. No player in this collection has been scored and no trajectory features have been extracted.', '',
        '| Acquisition slice | Labeled players | Match groups |','| --- | ---: | ---: |']
    lines.extend(f'| {Path(p["directory"]).name} | {p["players"]} | {p["matches"]} |' for p in parts)
    lines.extend(['','Cases within one match share a group. This is not 50 independent matches, and archive-order convenience sampling does not establish population representativeness. Skill-rating annotations are unavailable.','',
        'Every selected target has its own uniquely mapped source label. Input hashes and match groups were checked across slices, and all participants are registered for future acquisition exclusion. Raw demos and generated artifacts stay local.','',
        'Next: bind a group-aware single-use evaluation protocol to this collection and frozen model, then score all controls once. Report player flags, flagged match groups, errors and insufficient-evidence outcomes separately.'])
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    print(f'Collected {len(cases)} labeled players in {len(groups)} disjoint match groups; unscored.',flush=True)
    return collection


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directories',nargs='+',type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--target',type=int,default=50)
    a=p.parse_args();collect(a.directories,a.output,a.target)

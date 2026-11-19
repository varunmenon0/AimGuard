"""Exclude an acquired grouped cohort from future downloads without scoring it."""
import argparse
import hashlib
import json
from pathlib import Path

from aimguard.baseline import digest, write_json
from aimguard.offline_detector import load
from aimguard.tracking_baseline import load_model
from scripts.report_legitimate_cohort import verify_groups


def register(directory):
    directory = Path(directory); candidates = directory/'candidates.json'
    manifest = json.loads(candidates.read_text()); plan = json.loads((directory/'plan.json').read_text())
    verification = json.loads((directory/'verification.json').read_text())
    if (manifest['role'] != 'grouped_legitimate_evaluation_candidates_not_reserved' or
            verification['candidates_sha256'] != digest(candidates) or
            verification['plan_sha256'] != digest(directory/'plan.json')):
        raise ValueError('Require verified acquisition metadata')
    verify_groups(manifest['cases'], manifest['groups'], plan['excluded_account_participants'])
    for path, sha in plan['source_label_sha256'].items():
        if digest(path) != sha:
            raise ValueError('Source labels changed after verification')
    checked = set()
    for case in manifest['cases']:
        if case['demo'] not in checked and digest(case['demo']) != case['demo_sha256']:
            raise ValueError('Replay changed after verification')
        checked.add(case['demo'])
    model = Path('outputs/xguardian/offline-v06/frozen'); load(model)
    if manifest['model_sha256'] != digest(model/'model.json'):
        raise ValueError('Acquisition belongs to another model')
    legacy = Path('outputs/xguardian/tracking-baseline-v2/frozen'); load_model(legacy)
    record = dict(model_sha256=digest(legacy/'model.json'),
        purpose='grouped_legitimate_acquisition_exclusion_only',
        supplemental_model_sha256=manifest['model_sha256'],
        candidates_sha256=digest(candidates), verification_sha256=digest(directory/'verification.json'),
        cases=manifest['cases'], features_inspected=False,
        note='Excludes every replay participant from future acquisition. No trajectories/scores inspected; not authorization for legacy or grouped evaluation. Bind a separate group-aware evaluation protocol before scoring.')
    name=hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()+'.reservation.json'
    registry=legacy/'reservations'; registry.mkdir(exist_ok=True); target=registry/name
    if target.exists():
        if json.loads(target.read_text()) != record:
            raise ValueError('Exclusion registry collision')
    else:
        write_json(target,record)
    pointer=directory/'acquisition-exclusion.json'
    receipt=dict(registry_receipt=str(target.resolve()),registry_sha256=digest(target),
        candidates_sha256=digest(candidates),cases=len(manifest['cases']),groups=len(manifest['groups']))
    if pointer.exists():
        if json.loads(pointer.read_text()) != receipt:
            raise ValueError('Existing exclusion receipt differs')
    else:
        write_json(pointer,receipt)
    print(json.dumps(receipt)); return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    register(parser.parse_args().directory)

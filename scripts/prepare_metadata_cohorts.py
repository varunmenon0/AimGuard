"""Split new metadata-only cases before features; register every participant exclusion."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path

from aimguard.baseline import digest,write_json
from aimguard.tracking_baseline import load_model,validate_candidates


def split_cases(cases):
    """Alternate within each source label in acquisition order; never inspect features."""
    counters={'cheating':0,'legitimate':0};development=[];holdout=[]
    for case in cases:
        if case.get('features_inspected') is not False or case.get('label') not in counters:
            raise ValueError('Require uninspected cases and known source labels')
        label=case['label'];partition='development' if counters[label]%2==0 else 'holdout';counters[label]+=1
        target=development if partition=='development' else holdout
        prefix='N' if partition=='development' else 'H'
        target.append(dict(case,case_id=f'{prefix}-{len(target)+1:03d}',partition=partition))
    for key in ('steamid','match_id','demo_sha256'):
        values=[c[key] for c in cases]
        if len(values)!=len(set(values)):raise ValueError('Duplicate cohort identity')
    participants=set()
    for c in cases:
        members=set(c['participants'])
        if not members or members&participants:raise ValueError('Cohorts share replay participants')
        participants.update(members)
    return development,holdout


def prepare(model_directory,candidate_manifest,output):
    model_directory,candidate_manifest,output=map(Path,(model_directory,candidate_manifest,output))
    bundle=load_model(model_directory);manifest=json.loads(candidate_manifest.read_text())
    if manifest.get('role')!='evaluation_candidates' or manifest.get('features_inspected') is not False or not manifest['cases']:
        raise ValueError('Require newly acquired metadata-only candidates')
    output.mkdir(parents=True,exist_ok=False)
    registry=model_directory/'reservations';lock=registry/'.lock'
    with lock.open('x') as f:f.write('Metadata cohort registration in progress\n')
    try:
        previous=[];registry_hashes={};model_hash=digest(model_directory/'model.json')
        for path in sorted(registry.glob('*.reservation.json')):
            r=json.loads(path.read_text())
            if r['model_sha256']!=model_hash:raise ValueError('Exclusion registry model differs')
            previous.extend(r['cases']);registry_hashes[path.name]=digest(path)
        write_json(output/'plan.json',dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(),
            candidate_manifest_sha256=digest(candidate_manifest),code_sha256=digest(__file__),
            selection='In original acquisition order, alternate development then holdout within each source label. No features or predictions.',
            prior_registry_sha256=registry_hashes,features_inspected=False,
            note='Holdout is reserved for a future phase-clean model, not bound to or authorized for legacy model evaluation. All participants are registered for future acquisition exclusion.'))
        cases=validate_candidates(bundle,manifest['cases'],previous)
        development,holdout=split_cases(cases)
        if not development or not holdout:raise ValueError('Need both development and holdout cases')
        common=dict(schema_version=1,features_inspected=False,candidate_manifest_sha256=digest(candidate_manifest),
            plan_sha256=digest(output/'plan.json'),caveats=manifest.get('caveats',[]))
        write_json(output/'development.json',dict(common,role='development',cases=development,fresh_holdout=False))
        write_json(output/'holdout.json',dict(common,role='future_phase_evaluation_holdout',cases=holdout,fresh_holdout=True,
            note='Do not extract features, tune on, or score these cases before freezing a future model and a single-use evaluation protocol. This metadata reservation is not proof of population representativeness.'))
        all_cases=development+holdout
        registration=dict(model_sha256=model_hash,purpose='split_development_and_untouched_holdout_exclusion',
            cases=all_cases,development_manifest_sha256=digest(output/'development.json'),holdout_manifest_sha256=digest(output/'holdout.json'),
            plan_sha256=digest(output/'plan.json'),features_inspected=False,
            note='Participant exclusion registration only; not an evaluated cohort or authorization to score the holdout.')
        write_json(output/'registration.json',registration);registration_hash=digest(output/'registration.json')
        write_json(registry/f'{registration_hash}.reservation.json',registration)
        summary={name:{label:sum(c['label']==label for c in cs) for label in ('cheating','legitimate')} for name,cs in [('development',development),('holdout',holdout)]}
        write_json(output/'summary.json',dict(counts=summary,registration_sha256=registration_hash,registered_participants=len({p for c in all_cases for p in c['participants']})))
        print(json.dumps(summary),flush=True);return development,holdout
    finally:lock.unlink()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('model_directory',type=Path);p.add_argument('candidate_manifest',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(argv);prepare(a.model_directory,a.candidate_manifest,a.output)


if __name__=='__main__':main()

"""Single-use mixed-label evaluation preserving shared replay groups."""
import argparse
import hashlib
import json
from pathlib import Path

from scipy.stats import beta

from aimguard.baseline import digest, write_json
from aimguard.offline_detector import load, now, predict
from aimguard.evaluation_cohorts import ROLE, prior_accounts, validate

RESERVATION_ROLE = 'frozen_grouped_evaluation_reservation_v1'
RUNTIME = ('aimguard/grouped_evaluation.py', 'aimguard/evaluation_cohorts.py',
           'scripts/acquire_cheating_cohort.py', 'scripts/acquire_fresh_cases.py',
           'scripts/audit_replay_identities.py')


def cohort_key(cases):
    return hashlib.sha256(json.dumps(sorted((c['demo_sha256'],c['steamid']) for c in cases),separators=(',',':')).encode()).hexdigest()


def summary(rows):
    scored = [r for r in rows if r['status'] in ('not_flagged','flag_for_review')]
    negatives = [r for r in scored if r['label']=='legitimate']
    positives = [r for r in scored if r['label']=='cheating']
    negative_groups = {}
    for row in rows:
        if row['label']=='legitimate':
            negative_groups.setdefault(row['group_id'],[]).append(row)
    complete = [rs for rs in negative_groups.values() if all(r['status'] in ('not_flagged','flag_for_review') for r in rs)]
    complete_flagged = sum(any(r['flagged'] for r in rs) for rs in complete)
    bound = float(beta.ppf(.95,complete_flagged+1,len(complete)-complete_flagged)) if complete and complete_flagged<len(complete) else (1. if complete else None)
    return dict(cases=len(rows),scored=len(scored),unresolved=len(rows)-len(scored),
        legitimate_cases=len([r for r in rows if r['label']=='legitimate']),legitimate_scored=len(negatives),
        false_flags=sum(r['flagged'] for r in negatives),
        cheating_cases=len([r for r in rows if r['label']=='cheating']),cheating_scored=len(positives),
        cheating_flagged=sum(r['flagged'] for r in positives),
        match_groups=len({r['group_id'] for r in rows}),legitimate_match_groups=len(negative_groups),
        legitimate_groups_fully_scored=len(complete),legitimate_groups_unresolved=len(negative_groups)-len(complete),
        legitimate_groups_with_flags=sum(any(r.get('flagged') is True for r in rs) for rs in negative_groups.values()),
        conditional_one_sided_95_upper_group_flag_rate=bound,
        caveat='Group bound concerns any legitimate-player flag per fully scored match, not population player FPR. It assumes independent representative correctly labeled match groups; archive convenience sampling does not establish this. Shared-match players are not independent. Generic cheating labels do not confirm active aimbot use. Unresolved cases are not correct negatives; class-balanced evaluation sampling cannot establish real-world precision.')


def reserve(model, collection, output, registry):
    model,collection,output,registry=map(Path,(model,collection,output,registry));bundle=load(model)
    manifest=json.loads(collection.read_text())
    if output.exists():
        raise ValueError('Use a new reservation output')
    if (manifest.get('role')!=ROLE or manifest.get('features_inspected') is not False or
            manifest['model_sha256']!=digest(model/'model.json') or manifest['threshold']!=bundle['threshold'] or
            manifest['preparation_code_sha256']!=digest('aimguard/evaluation_cohorts.py')):
        raise ValueError('Collection/model provenance differs')
    for path,sha in manifest['source_sha256'].items():
        if digest(path)!=sha:
            raise ValueError('Collection source changed')
    registry.mkdir(parents=True,exist_ok=True);lock=registry/'.lock'
    with lock.open('x') as f:f.write('Grouped evaluation reservation\n')
    try:
        key=cohort_key(manifest['cases']);canonical=registry/'cohorts'/key
        if canonical.exists():
            raise ValueError('Cohort already reserved/consumed')
        replay_hashes=sorted({c['demo_sha256'] for c in manifest['cases']})
        for sha in replay_hashes:
            if (registry/'matches'/f'{sha}.json').exists():
                raise ValueError('Replay already reserved/consumed; changing targets or positive subset does not restore freshness')
        blocked=prior_accounts(bundle)
        for path in registry.glob('cohorts/*/reservation.json'):
            for group in json.loads(path.read_text())['groups']:
                blocked.update(group['account_participants'])
        validate(manifest['cases'],manifest['groups'],blocked)
        record=dict(role=RESERVATION_ROLE,reserved_at_utc=now(),model_sha256=manifest['model_sha256'],
            threshold=bundle['threshold'],cohort_key=key,registry=str(registry.resolve()),
            cases=manifest['cases'],groups=manifest['groups'],excluded_accounts=sorted(blocked),
            collection=str(collection.resolve()),collection_sha256=digest(collection),source_sha256=manifest['source_sha256'],
            runtime_sha256={path:digest(path) for path in RUNTIME},
            note='All original controls and metadata-selected positives fixed before extraction. Consumption covers errors/partial runs. Per-replay registry blocks normal re-use with changed positive subsets or different target players.')
        output.mkdir(parents=True,exist_ok=False);canonical.mkdir(parents=True,exist_ok=False)
        write_json(output/'reservation.json',record);write_json(canonical/'reservation.json',record)
        (registry/'matches').mkdir(exist_ok=True)
        for sha in replay_hashes:
            write_json(registry/'matches'/f'{sha}.json',dict(cohort_key=key,reservation_sha256=digest(canonical/'reservation.json')))
        print(json.dumps(dict(cases=len(record['cases']),groups=len(record['groups']),cohort_key=key)),flush=True)
        return record
    finally:
        lock.unlink()


def evaluate(model,reservation,output):
    model,reservation,output=map(Path,(model,reservation,output));bundle=load(model)
    record=json.loads(reservation.read_text());key=cohort_key(record['cases'])
    canonical=Path(record['registry'])/'cohorts'/key;consumed=canonical/'consumed.json'
    if (record.get('role')!=RESERVATION_ROLE or record['model_sha256']!=digest(model/'model.json') or
            record['threshold']!=bundle['threshold'] or record['cohort_key']!=key or
            digest(reservation)!=digest(canonical/'reservation.json')):
        raise ValueError('Canonical reservation/model differs')
    if consumed.exists():
        raise ValueError('Grouped cohort consumed; copies and new outputs do not restore freshness')
    if output.exists():
        raise ValueError('Use a new evaluation output')
    if digest(record['collection'])!=record['collection_sha256']:
        raise ValueError('Collection changed')
    for path,sha in {**record['runtime_sha256'],**record['source_sha256']}.items():
        if digest(path)!=sha:
            raise ValueError('Reserved runtime/source changed: '+path)
    for sha in {c['demo_sha256'] for c in record['cases']}:
        usage=json.loads((Path(record['registry'])/'matches'/f'{sha}.json').read_text())
        if usage['cohort_key']!=key or usage['reservation_sha256']!=digest(reservation):
            raise ValueError('Replay usage registry differs')
    validate(record['cases'],record['groups'],set(record['excluded_accounts']))
    receipt=dict(started_at_utc=now(),reservation_sha256=digest(reservation),model_sha256=record['model_sha256'],
        cohort_key=key,output=str(output.resolve()),note='Consumed before any trajectory features or scores, including errors and interrupted runs.')
    write_json(consumed,receipt);output.mkdir(parents=True,exist_ok=False);write_json(output/'start.json',receipt)
    rows=[]
    for i,case in enumerate(record['cases'],1):
        try:
            prediction=predict(model,case['demo'],case['steamid'],output/f'case_{i:03d}')
        except Exception as error:
            prediction=dict(status='error',score=None,flagged=None,error_type=type(error).__name__,error=str(error))
        row=dict(prediction,case_id=case['case_id'],group_id=case['group_id'],label=case['label'])
        rows.append(row);write_json(output/f'prediction_{i:03d}.json',row)
        print(case['case_id'],row['status'],flush=True)
    result=dict(summary=summary(rows),predictions=rows,model_sha256=record['model_sha256'],
        collection_sha256=record['collection_sha256'],reservation_sha256=digest(reservation),consumption_sha256=digest(consumed))
    write_json(output/'evaluation.json',result)
    lines=['# Frozen mixed-label grouped evaluation','',json.dumps(result['summary'],indent=2),'',
           '| Case | Match group | Source label | Score | Decision |','| --- | --- | --- | ---: | --- |']
    lines.extend(f'| {r["case_id"]} | {r["group_id"]} | {r["label"]} | {r.get("score")} | {r["status"]} |' for r in rows)
    (output/'report.md').write_text('\n'.join(lines)+'\n');load(model)
    print(json.dumps(result['summary']),flush=True);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('reserve');r.add_argument('model',type=Path);r.add_argument('collection',type=Path);r.add_argument('--output',type=Path,required=True);r.add_argument('--registry',type=Path,required=True)
    e=sub.add_parser('evaluate');e.add_argument('model',type=Path);e.add_argument('reservation',type=Path);e.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.command=='reserve':reserve(a.model,a.collection,a.output,a.registry)
    else:evaluate(a.model,a.reservation,a.output)

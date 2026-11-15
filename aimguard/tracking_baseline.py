"""Freeze, reserve fresh cases, and evaluate the four-feature tracking candidate."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from aimguard.baseline import EXPECTED_CONFIGURATION, digest, evaluation_metrics, report_features, write_json
from aimguard.batch import validate_windows
from aimguard.gameplay import FEATURE_VERSION, analyze_demo, identity_strings
from aimguard.target_tracking import extract_case
from aimguard.tracking_models import MIN_INTERVALS, MIN_WINDOWS, PRE_SECONDS, TRACKING_RECIPES, case_features

FEATURES=TRACKING_RECIPES['speed_and_tracking']['features']
DEPENDENCIES=('numpy','pandas','scipy','scikit-learn','demoparser2')
SOURCE_FILES=('tracking_baseline.py','tracking_models.py','development_models.py','baseline.py',
              'target_tracking.py','target_geometry.py','gameplay.py','combat.py','core.py','cs2.py','batch.py')
HYPERPARAMETERS=dict(C=1.,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0)


def now():return datetime.now(timezone.utc).isoformat()


def participant_ids(demo):
    """Read identity metadata, never view angles or movement features."""
    from demoparser2 import DemoParser
    parser=DemoParser(str(demo))
    participants=set()
    # Player-info snapshots can be empty or omit disconnected/replaced players.
    # Request no gameplay properties: the full identity stream supplies coverage.
    for frame in (parser.parse_player_info(),parser.parse_ticks([])):
        values=identity_strings(frame['steamid'])
        participants.update(value for value in values if value.isdigit() and int(value)>0)
    participants=sorted(participants)
    if not participants:raise ValueError('Replay has no exact participant identities')
    return participants


def score(bundle,features):
    values=np.asarray(features,dtype=float)
    if values.shape!=(4,) or not np.isfinite(values).all() or (values<0).any():
        raise ValueError('Four finite nonnegative tracking features required')
    mean=np.asarray(bundle['scaler_mean'],dtype=float);scale=np.asarray(bundle['scaler_scale'],dtype=float)
    coefficients=np.asarray(bundle['coefficients'],dtype=float)
    if (mean.shape!=(4,) or scale.shape!=(4,) or coefficients.shape!=(4,)
        or not np.isfinite(np.r_[mean,scale,coefficients,bundle['intercept']]).all() or (scale<=0).any()):
        raise ValueError('Invalid frozen model parameters')
    return float(expit(bundle['intercept']+np.dot(coefficients,(np.log1p(values)-mean)/scale)))


def load_model(directory):
    directory=Path(directory);path=directory/'model.json'
    if digest(path)!=(directory/'model.sha256').read_text().strip():
        raise ValueError('Model checksum mismatch')
    bundle=json.loads(path.read_text())
    expected=dict(python_version=platform.python_version(),schema_version=1,model_kind='speed_and_pre_shot_tracking',feature_names=FEATURES,
        feature_version=FEATURE_VERSION,threshold=.5,configuration=EXPECTED_CONFIGURATION,
        assumed_tickrate_hz=64.,pre_seconds=PRE_SECONDS,minimum_intervals=MIN_INTERVALS,
        minimum_windows=MIN_WINDOWS,hyperparameters=HYPERPARAMETERS)
    if any(bundle.get(key)!=value for key,value in expected.items()):
        raise ValueError('Frozen tracking protocol differs from supported recipe')
    if set(bundle['code_sha256'])!=set(SOURCE_FILES) or set(bundle['dependencies'])!=set(DEPENDENCIES):
        raise ValueError('Incomplete frozen runtime receipt')
    for name,expected_hash in bundle['code_sha256'].items():
        if digest(Path(__file__).with_name(name))!=expected_hash:
            raise ValueError(f'Frozen code changed: {name}')
    for name,expected_version in bundle['dependencies'].items():
        if importlib.metadata.version(name)!=expected_version:
            raise ValueError(f'Frozen dependency changed: {name}')
    score(bundle,[0.,0.,0.,0.]) # Validate shapes and finite parameters before feature access.
    return bundle


def freeze(manifest_path,analysis_root,tracking_root,comparison_root,output,exclude_demos=()):
    if Path(output).exists():raise ValueError('Choose a new frozen output directory')
    manifest_path,analysis_root,tracking_root,comparison_root=map(Path,(manifest_path,analysis_root,tracking_root,comparison_root))
    manifest=json.loads(manifest_path.read_text())
    protocol=json.loads((comparison_root/'protocol.json').read_text())
    inputs=json.loads((comparison_root/'inputs.json').read_text())
    comparison=json.loads((comparison_root/'comparison.json').read_text())
    if manifest.get('role')!='development' or not manifest.get('cases'):
        raise ValueError('Freeze requires nonempty development data')
    if (protocol['manifest_sha256']!=digest(manifest_path) or comparison['protocol_sha256']!=digest(comparison_root/'protocol.json')
        or comparison['inputs_sha256']!=digest(comparison_root/'inputs.json')):
        raise ValueError('Development comparison receipt mismatch')
    if (protocol['recipes']['speed_and_tracking']!=TRACKING_RECIPES['speed_and_tracking']
        or protocol['threshold']!=.5 or protocol['pre_seconds']!=PRE_SECONDS
        or protocol['minimum_contiguous_intervals']!=MIN_INTERVALS or protocol['minimum_eligible_windows']!=MIN_WINDOWS
        or protocol['hyperparameters']!=HYPERPARAMETERS):
        raise ValueError('Comparison recipe differs from candidate to freeze')
    if protocol['dependencies']!={name:importlib.metadata.version(name) for name in DEPENDENCIES}:
        raise ValueError('Development comparison dependencies changed')
    for name,expected_hash in protocol['source_code_sha256'].items():
        if name!='target_tracking.py' and digest(Path(__file__).with_name(name))!=expected_hash:
            raise ValueError(f'Development feature code changed: {name}')
    cases=manifest['cases']
    if (len(inputs['tracking'])!=len(cases) or len(inputs['cases'])!=len(cases)
        or len({case['steamid'] for case in cases})!=len(cases)
        or len({case['match_id'] for case in cases})!=len(cases)
        or len({case['demo_sha256'] for case in cases})!=len(cases)):
        raise ValueError('Development identities must be unique and complete')
    rows=[];labels=[];development=[];participants=set();equivalence=[]
    for index,case in enumerate(cases,1):
        if case['label'] not in ('cheating','legitimate'):raise ValueError('Unknown development label')
        directory=analysis_root/f'job_{index:04d}'
        original_path=tracking_root/f'case_{index:04d}.json'
        prior=inputs['tracking'][index-1]
        if (prior['case_id']!=case['case_id'] or prior['tracking_sha256']!=digest(original_path)
            or inputs['cases'][index-1]['case_id']!=case['case_id']
            or inputs['cases'][index-1]['report_sha256']!=digest(directory/'report.json')):
            raise ValueError('Development inputs changed since comparison')
        # Re-extract with the exact code to be frozen; refactors must reproduce all records.
        current=extract_case(case,directory)
        if current!=json.loads(original_path.read_text()):
            raise ValueError('Canonical tracking re-extraction differs from development record')
        tracking,counts=case_features(current['windows'],current['assumed_tickrate_hz'])
        if tracking is None or tracking!=prior['features'] or counts['eligible_windows']!=prior['eligible_windows']:
            raise ValueError('Tracking feature/coverage mismatch before freeze')
        report=json.loads((directory/'report.json').read_text());speed,_=report_features(report)
        if report['assumed_tickrate_hz']!=64.:raise ValueError('Candidate requires frozen 64 Hz assumption')
        members=participant_ids(case['demo'])
        if case['steamid'] not in members:raise ValueError('Development target absent from participants')
        participants.update(members);values=[*speed,*tracking]
        rows.append(values);labels.append(int(case['label']=='cheating'))
        development.append(dict(case_id=case['case_id'],steamid=case['steamid'],match_id=case['match_id'],
            demo_sha256=case['demo_sha256'],label=case['label'],participants=members,features=values,
            eligible_windows=counts['eligible_windows'],report_sha256=digest(directory/'report.json'),tracking_sha256=digest(original_path)))
        equivalence.append(dict(case_id=case['case_id'],full_record_equal=True,feature_equal=True))
        print(f"Verified development case {index}/{len(cases)}",flush=True)
    if len(set(labels))!=2:raise ValueError('Development requires both classes')
    exclusions=[]
    for demo in exclude_demos:
        members=participant_ids(demo);participants.update(members)
        exclusions.append(dict(demo_name=Path(demo).name,demo_sha256=digest(demo),participants=members))
    scaler=StandardScaler().fit(np.log1p(rows))
    model=LogisticRegression(**HYPERPARAMETERS).fit(scaler.transform(np.log1p(rows)),labels)
    bundle=dict(python_version=platform.python_version(),schema_version=1,model_kind='speed_and_pre_shot_tracking',frozen_at_utc=now(),
        feature_names=FEATURES,feature_version=FEATURE_VERSION,threshold=.5,configuration=EXPECTED_CONFIGURATION,
        assumed_tickrate_hz=64.,pre_seconds=PRE_SECONDS,minimum_intervals=MIN_INTERVALS,minimum_windows=MIN_WINDOWS,
        hyperparameters=HYPERPARAMETERS,transformation='log1p then development-fitted StandardScaler',
        scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),coefficients=model.coef_[0].tolist(),
        intercept=float(model.intercept_[0]),development=development,excluded_participants=sorted(participants),
        additional_inspected_demos=exclusions,participant_metadata_method='Union of player-info and all-tick identity-only streams; no aim properties',development_manifest_sha256=digest(manifest_path),
        comparison_sha256=digest(comparison_root/'comparison.json'),
        code_sha256={name:digest(Path(__file__).with_name(name)) for name in SOURCE_FILES},
        dependencies={name:importlib.metadata.version(name) for name in DEPENDENCIES},
        note='Frozen research candidate, not a deployed or independently validated detector. Scores are uncalibrated.')
    for values,expected_score in zip(rows,model.predict_proba(scaler.transform(np.log1p(rows)))[:,1]):
        if not np.isclose(score(bundle,values),expected_score,rtol=0,atol=1e-12):
            raise ValueError('Exported candidate scores do not reproduce fitted model')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    write_json(output/'model.json',bundle)
    (output/'model.sha256').write_text(digest(output/'model.json')+'\n')
    write_json(output/'extraction-equivalence.json',dict(cases=equivalence,
        original_tracking_code_sha256=protocol['source_code_sha256']['target_tracking.py'],
        frozen_tracking_code_sha256=digest(Path(__file__).with_name('target_tracking.py')),
        note='Current canonical extraction reproduces complete saved records and candidate features before fitting.'))
    return bundle


def validate_candidates(bundle,cases,registered=()):
    """Only checksums and participant metadata, no trajectory features."""
    if not cases:raise ValueError('Fresh reservation requires at least one case')
    blocked=set(bundle['excluded_participants'])
    matches={case['match_id'] for case in bundle['development']}
    hashes={case['demo_sha256'] for case in bundle['development']}|{case['demo_sha256'] for case in bundle['additional_inspected_demos']}
    for previous in registered:
        blocked.update(previous['participants']);matches.add(previous['match_id']);hashes.add(previous['demo_sha256'])
    targets=set();seen_participants=set();result=[]
    for index,case in enumerate(cases,1):
        if (case.get('features_inspected') is not False or case.get('label') not in ('cheating','legitimate')
            or not isinstance(case.get('steamid'),str) or not case['steamid'].isdigit() or int(case['steamid'])<=0
            or not isinstance(case.get('match_id'),str) or not case['match_id']):
            raise ValueError('Candidates require uninspected status, labels, match IDs, and exact string SteamIDs')
        if case['steamid'] in blocked|targets or case['match_id'] in matches or case['demo_sha256'] in hashes:
            raise ValueError('Duplicate or previously inspected evaluation target/match/demo')
        if digest(case['demo'])!=case['demo_sha256'] or digest(case['source_label_file'])!=case['source_label_sha256']:
            raise ValueError('Candidate demo/label source checksum mismatch')
        members=participant_ids(case['demo'])
        if case['steamid'] not in members:raise ValueError('Evaluation target absent from participants')
        if set(members)&blocked:raise ValueError('Evaluation participant overlaps inspected/development data')
        if set(members)&seen_participants:raise ValueError('Evaluation cases share participants')
        targets.add(case['steamid']);matches.add(case['match_id']);hashes.add(case['demo_sha256']);seen_participants.update(members)
        result.append(dict(case,case_id=f'R-{index:03d}',participants=members))
    return result


def reserve(model_directory,candidate_manifest,output):
    bundle=load_model(model_directory);candidate_manifest=Path(candidate_manifest)
    manifest=json.loads(candidate_manifest.read_text())
    if manifest.get('role')!='evaluation_candidates' or manifest.get('features_inspected') is not False:
        raise ValueError('Reservation requires explicitly uninspected evaluation candidates')
    cases=[dict(case,demo=str((candidate_manifest.parent/Path(case['demo'])).resolve()),
                source_label_file=str((candidate_manifest.parent/Path(case['source_label_file'])).resolve()))
           for case in manifest['cases']]
    output=Path(output)
    if output.exists() or output.with_suffix('.sha256').exists():raise ValueError('Choose a new reservation path')
    registry=Path(model_directory)/'reservations';registry.mkdir(exist_ok=True)
    lock=registry/'.lock'
    with lock.open('x') as handle:handle.write('Reservation registry update in progress\n')
    try:
        previous=[]
        for path in registry.glob('*.reservation.json'):
            receipt=json.loads(path.read_text())
            if receipt['model_sha256']!=digest(Path(model_directory)/'model.json'):
                raise ValueError('Reservation registry model mismatch')
            previous.extend(receipt['cases'])
        cases=validate_candidates(bundle,cases,previous)
        output.parent.mkdir(parents=True,exist_ok=True)
        write_json(output,dict(schema_version=1,role='reserved_tracking_evaluation',features_inspected=False,
            reserved_at_utc=now(),model_sha256=digest(Path(model_directory)/'model.json'),cases=cases,
            candidate_manifest_sha256=digest(candidate_manifest),caveats=manifest.get('caveats',[]),
            selection=manifest.get('selection','Caller-supplied cases; no representativeness claim'),
            note='Metadata-only reservation. Uninspected status is an explicit declaration, not proof of prior non-use.'))
        manifest_hash=digest(output)
        output.with_suffix('.sha256').write_text(manifest_hash+'\n')
        write_json(registry/f'{manifest_hash}.reservation.json',dict(model_sha256=digest(Path(model_directory)/'model.json'),
            reserved_manifest_sha256=manifest_hash,manifest=str(output.resolve()),cases=cases))
    finally:
        lock.unlink()

    return cases


def evaluate(model_directory,reserved_manifest,output):
    bundle=load_model(model_directory);reserved_manifest=Path(reserved_manifest);output=Path(output)
    model_hash=digest(Path(model_directory)/'model.json');manifest_hash=digest(reserved_manifest)
    if manifest_hash!=reserved_manifest.with_suffix('.sha256').read_text().strip():raise ValueError('Reservation checksum mismatch')
    manifest=json.loads(reserved_manifest.read_text())
    if manifest.get('role')!='reserved_tracking_evaluation' or manifest.get('features_inspected') is not False or manifest.get('model_sha256')!=model_hash:
        raise ValueError('Reservation belongs to a different frozen model/protocol')
    registry=Path(model_directory)/'reservations'
    registration=json.loads((registry/f'{manifest_hash}.reservation.json').read_text())
    if registration['model_sha256']!=model_hash or registration['cases']!=manifest['cases']:
        raise ValueError('Reservation registry receipt mismatch')
    started=registry/f'{manifest_hash}.started.json'
    if started.exists() or reserved_manifest.with_suffix('.started.json').exists():raise ValueError('Reservation already started/consumed; do not reuse as fresh evaluation')
    cases=validate_candidates(bundle,manifest['cases'])
    for saved,actual in zip(manifest['cases'],cases):
        if saved['participants']!=actual['participants']:raise ValueError('Reserved participant metadata changed')
    output.mkdir(parents=True,exist_ok=False)
    receipt=dict(started_at_utc=now(),model_sha256=model_hash,reserved_manifest_sha256=manifest_hash,
        threshold=bundle['threshold'],feature_names=FEATURES,output=str(output.resolve()),
        note='Single-use reservation consumed before feature extraction, including runs with analysis errors.')
    write_json(started,receipt) # Central exclusive receipt also catches relocated/copied manifests.
    write_json(reserved_manifest.with_suffix('.started.json'),receipt)
    write_json(output/'start-receipt.json',receipt)
    rows=[]
    for index,case in enumerate(cases,1):
        row=dict(case_id=case['case_id'],steamid=case['steamid'],match_id=case['match_id'],label=case['label'])
        try:
            if digest(case['demo'])!=case['demo_sha256'] or digest(case['source_label_file'])!=case['source_label_sha256']:
                raise ValueError('Evaluation source changed after preflight')
            directory=output/f'case_{index:03d}'
            report=analyze_demo(case['demo'],case['steamid'],directory,tickrate=bundle['assumed_tickrate_hz'],
                pre_s=bundle['configuration']['pre_seconds'],post_s=bundle['configuration']['post_seconds'],
                shot_gap_s=bundle['configuration']['shot_gap_seconds'],max_plots=0,
                weapon_mode=bundle['configuration']['weapon_mode'],near_shot_s=bundle['configuration']['near_shot_seconds'])
            player=pd.read_csv(directory/'telemetry.csv',dtype={'steamid':str})
            events=pd.DataFrame(json.loads((directory/'events.json').read_text()))
            if events.empty:events=pd.DataFrame(columns=['tick','event_type','player_role','segment_id'])
            violations=validate_windows(player,events,report)
            if violations:raise ValueError(f'Structural violations: {violations}')
            tracking=extract_case(case,directory)
            write_json(directory/'tracking.json',tracking)
            track_values,counts=case_features(tracking['windows'],bundle['assumed_tickrate_hz'])
            if track_values is None:raise ValueError('Insufficient eligible pre-shot tracking windows')
            speed,_=report_features(report);values=[*speed,*track_values];value=score(bundle,values)
            row.update(status='scored',baseline_score=value,flagged=value>=bundle['threshold'],features=dict(zip(FEATURES,values)),
                tracking_coverage=counts,windows=report['engagement_count'],round_warnings=report['data_quality']['round_event_anomalies'],
                report_sha256=digest(directory/'report.json'),tracking_sha256=digest(directory/'tracking.json'))
        except Exception as exc:
            row.update(status='abstained',error_type=type(exc).__name__,error=str(exc))
        rows.append(row);write_json(output/f'prediction_{index:03d}.json',row)
        print(f"{index}/{len(cases)}: {row['status']}",flush=True)
    result=dict(model_sha256=model_hash,reserved_manifest_sha256=manifest_hash,completed_at_utc=now(),threshold=bundle['threshold'],
        metrics=evaluation_metrics(rows),predictions=rows,caveats=manifest.get('caveats',[])+[
            'Generic player/match cheating labels do not identify aimbot activation.',
            'Scores are uncalibrated; visibility, vertical/hitbox geometry, recoil and lag/subtick corrections are unresolved.',
            'All replay participants are disjoint across evaluation cases and from recorded inspected cases; source sampling may still induce dependence.',
            'Exact binomial intervals assume independent outcomes; report coverage and abstentions separately.',
            'This reservation is consumed. Tuning using these outcomes requires a new fresh evaluation set.'])
    write_json(output/'evaluation.json',result)
    write_json(registry/f'{manifest_hash}.completed.json',dict(evaluation_sha256=digest(output/'evaluation.json'),output=str(output.resolve())))
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);actions=parser.add_subparsers(dest='action',required=True)
    action=actions.add_parser('freeze')
    for name in ('development_manifest','analysis_root','tracking_root','comparison_root'):action.add_argument(name,type=Path)
    action.add_argument('--exclude-demo',action='append',type=Path,default=[]);action.add_argument('--output',type=Path,required=True)
    action=actions.add_parser('reserve');action.add_argument('model_directory',type=Path);action.add_argument('candidate_manifest',type=Path);action.add_argument('--output',type=Path,required=True)
    action=actions.add_parser('evaluate');action.add_argument('model_directory',type=Path);action.add_argument('reserved_manifest',type=Path);action.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.action=='freeze':freeze(args.development_manifest,args.analysis_root,args.tracking_root,args.comparison_root,args.output,args.exclude_demo)
        elif args.action=='reserve':reserve(args.model_directory,args.candidate_manifest,args.output)
        else:print(json.dumps(evaluate(args.model_directory,args.reserved_manifest,args.output)['metrics'],indent=2))
    except (OSError,ValueError,KeyError) as exc:parser.error(str(exc))


if __name__=='__main__':main()

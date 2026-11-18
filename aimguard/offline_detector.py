"""Freeze and run the v0.6 offline review candidate; single-use holdout evaluation."""
import argparse
from datetime import datetime,timezone
import html
import importlib.metadata
import json
from pathlib import Path
import platform

import numpy as np
from scipy.stats import beta
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from aimguard.baseline import digest,write_json,EXPECTED_CONFIGURATION
from aimguard.development_models import participant_groups
from aimguard.phase_gameplay import analyze_demo,FEATURE_VERSION,PHASE_POLICY
from aimguard.phase_development import speed_features,verify_live
from aimguard.target_tracking import extract_case
from aimguard.tracking_models import case_features,TRACKING_RECIPES
from aimguard.tracking_baseline import participant_ids,score as parameter_score,load_model as legacy_model,SOURCE_FILES

CODE_FILES=tuple(sorted(set(SOURCE_FILES)|{'offline_detector.py','phase_gameplay.py','phase_audit.py','phase_development.py','review.py'}))
DEPENDENCIES=('numpy','pandas','scipy','scikit-learn','demoparser2','matplotlib')
PARAMETERS=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0)
THRESHOLD=.75


def now():return datetime.now(timezone.utc).isoformat()


def load(directory):
    directory=Path(directory);path=directory/'model.json'
    if digest(path)!=(directory/'model.sha256').read_text().strip():raise ValueError('Frozen model checksum differs')
    bundle=json.loads(path.read_text())
    expected=dict(model_kind='phase_clean_offline_review',schema_version=1,feature_version=FEATURE_VERSION,phase_policy=PHASE_POLICY,threshold=THRESHOLD,
        feature_names=TRACKING_RECIPES['speed_and_tracking']['features'],configuration=EXPECTED_CONFIGURATION,
        hyperparameters=PARAMETERS,tickrate=64,python_version=platform.python_version())
    if any(bundle.get(k)!=v for k,v in expected.items()):raise ValueError('Frozen offline recipe differs')
    if set(bundle['code_sha256'])!=set(CODE_FILES) or set(bundle['dependencies'])!=set(DEPENDENCIES):raise ValueError('Incomplete runtime receipt')
    for name,h in bundle['code_sha256'].items():
        if digest(Path(__file__).with_name(name))!=h:raise ValueError('Frozen source changed: '+name)
    for name,version in bundle['dependencies'].items():
        if importlib.metadata.version(name)!=version:raise ValueError('Frozen dependency changed: '+name)
    parameter_score(bundle,[0,0,0,0]);return bundle


def freeze(pool,reference,legacy_directory,output):
    pool,reference,legacy_directory,output=map(Path,(pool,reference,legacy_directory,output))
    if output.exists():raise ValueError('Use a new frozen directory')
    result=json.loads((pool/'comparison.json').read_text());inputs=json.loads((pool/'inputs.json').read_text());protocol=json.loads((pool/'protocol.json').read_text());ref=json.loads((reference/'comparison.json').read_text());rp=json.loads((reference/'protocol.json').read_text())
    if result['inputs_sha256']!=digest(pool/'inputs.json') or result['protocol_sha256']!=digest(pool/'protocol.json') or ref['protocol_sha256']!=digest(reference/'protocol.json') or any(rp['source_sha256'][n]!=digest(pool/n) for n in ('inputs.json','protocol.json','comparison.json')) or ref['models']['cost_ratio_threshold']['threshold']!=THRESHOLD:raise ValueError('Freeze source/reference receipts differ')
    if protocol['role']!='inspected_v06_development' or protocol['hyperparameters']!=PARAMETERS:raise ValueError('Unexpected training recipe')
    rows=inputs['cases'];ids=[r['case_id'] for r in rows];members=[cid for cs in inputs['groups'].values() for cid in cs]
    if len(set(ids))!=len(ids) or len(set(members))!=len(members) or set(ids)!=set(members) or inputs['groups']!=protocol['groups']:raise ValueError('Training group partition differs')
    training=[];vectors=[];excluded=set(legacy_model(legacy_directory)['excluded_participants'])
    for i,row in enumerate(rows,1):
        directory=pool/'analysis'/f'job_{i:04d}';report=json.loads((directory/'report.json').read_text());trackpath=pool/'tracking'/f'case_{i:04d}.json';tracking=json.loads(trackpath.read_text())
        if digest(directory/'report.json')!=row['report_sha256'] or digest(trackpath)!=row['tracking_sha256'] or tracking['summary']['case_id']!=row['case_id'] or tracking['summary']['label']!=row['label'] or row['label'] not in ('cheating','legitimate'):raise ValueError('Training case receipt differs')
        for name,h in tracking['input_sha256'].items():
            if digest(directory/name)!=h:raise ValueError('Training input changed')
        if report['assumed_tickrate_hz']!=64:raise ValueError('Unsupported training tickrate')
        verify_live(directory,report);speed=speed_features(report);target,coverage=case_features(tracking['windows'],report['assumed_tickrate_hz']);vector=[*speed,*target] if speed is not None and target is not None else None
        if vector is None or not np.allclose(vector,row['features'],rtol=0,atol=1e-10):raise ValueError('Training vector differs')
        demo=Path(report['source'])
        if digest(demo)!=report['source_sha256']:raise ValueError('Training demo changed')
        participants=participant_ids(demo);excluded.update(participants);vectors.append(vector)
        training.append(dict(case_id=row['case_id'],label=row['label'],steamid=report['steamid'],demo_sha256=report['source_sha256'],report_sha256=row['report_sha256'],tracking_sha256=row['tracking_sha256'],participants=participants,features=vector))
        print(f'Verified training case {i}/{len(rows)}',flush=True)
    actual_groups=participant_groups([set(c['participants']) for c in training])
    actual_partition={frozenset(c['case_id'] for c,g in zip(training,actual_groups) if g==group) for group in set(actual_groups)}
    if actual_partition!={frozenset(cs) for cs in inputs['groups'].values()}:raise ValueError('Participant-derived training groups differ')
    x=np.log1p(vectors);y=np.array([int(r['label']=='cheating') for r in rows]);scaler=StandardScaler().fit(x);model=LogisticRegression(**PARAMETERS).fit(scaler.transform(x),y)
    bundle=dict(schema_version=1,model_kind='phase_clean_offline_review',created_at_utc=now(),feature_version=FEATURE_VERSION,phase_policy=PHASE_POLICY,
        threshold=THRESHOLD,feature_names=TRACKING_RECIPES['speed_and_tracking']['features'],configuration=EXPECTED_CONFIGURATION,hyperparameters=PARAMETERS,tickrate=64,
        scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),coefficients=model.coef_[0].tolist(),intercept=float(model.intercept_[0]),
        training=training,groups=inputs['groups'],excluded_participants=sorted(excluded),
        reserved_holdout_sha256=protocol['holdout_manifest_sha256'],
        source_sha256={str(p):digest(p) for p in (pool/'inputs.json',pool/'comparison.json',pool/'protocol.json',reference/'comparison.json',reference/'protocol.json')},
        code_sha256={name:digest(Path(__file__).with_name(name)) for name in CODE_FILES},dependencies={n:importlib.metadata.version(n) for n in DEPENDENCIES},python_version=platform.python_version(),
        note='Uncalibrated generic-cheating review score. Not confirmed active-aimbot probability. Threshold fixed before holdout extraction; no ban recommendation.')
    if not np.allclose([parameter_score(bundle,v) for v in vectors],model.predict_proba(scaler.transform(x))[:,1],atol=1e-12):raise ValueError('Full-fit score export differs')
    output.mkdir(parents=True,exist_ok=False);write_json(output/'model.json',bundle);(output/'model.sha256').write_text(digest(output/'model.json')+'\n');load(output);return bundle


def predict(model_directory,demo,steamid,output):
    bundle=load(model_directory);demo,output=map(Path,(demo,output))
    if output.exists():raise ValueError('Use a new output directory')
    if not isinstance(steamid,str) or not steamid.isdigit() or int(steamid)<=0:raise ValueError('Use an exact positive SteamID string')
    output.mkdir(parents=True,exist_ok=False);write_json(output/'start.json',dict(model_sha256=digest(Path(model_directory)/'model.json'),demo_sha256=digest(demo),steamid=steamid,started_at_utc=now()))
    directory=output/'analysis';report=analyze_demo(demo,steamid,directory,tickrate=bundle['tickrate'],max_plots=0);verify_live(directory,report);speed=speed_features(report)
    case=dict(case_id='offline-input',label='unlabeled',steamid=steamid,demo=str(demo.resolve()),demo_sha256=report['source_sha256'])
    tracking=extract_case(case,directory);write_json(output/'tracking.json',tracking);target,coverage=case_features(tracking['windows'],bundle['tickrate'])
    result=dict(model_sha256=digest(Path(model_directory)/'model.json'),demo_sha256=report['source_sha256'],steamid=steamid,threshold=THRESHOLD,
        feature_version=FEATURE_VERSION,coverage=coverage,windows=report['engagement_count'],round_event_warnings=report['data_quality']['round_event_anomalies'],
        report_sha256=digest(directory/'report.json'),tracking_sha256=digest(output/'tracking.json'),
        note='Score is uncalibrated review priority, not cheating probability. Not flagged does not certify legitimate play; insufficient evidence is unresolved.')
    if speed is None or target is None:result.update(status='insufficient_evidence',flagged=None,score=None,features=None)
    else:
        vector=[*speed,*target];score=parameter_score(bundle,vector);contributions=((np.log1p(vector)-bundle['scaler_mean'])/bundle['scaler_scale'])*bundle['coefficients']
        result.update(status='flag_for_review' if score>=THRESHOLD else 'not_flagged',flagged=bool(score>=THRESHOLD),score=score,features=vector,contributions=dict(zip(bundle['feature_names'],contributions.tolist())),intercept=bundle['intercept'])
    write_json(output/'prediction.json',result)
    score_text=f"{100*result['score']:.2f} / 100" if result['score'] is not None else 'Unavailable'
    warnings='Round-event warnings are present; inspect the evidence report.' if result['round_event_warnings'] else 'No round-event warnings recorded.'
    page='<!doctype html><html lang="en"><meta charset="utf-8"><title>AimGuard offline review</title><style>body{font:17px system-ui;max-width:900px;margin:30px auto;padding:20px;line-height:1.5}</style><h1>AimGuard offline result</h1><h2>'+html.escape(result['status'].replace('_',' '))+'</h2><p>Review-priority score: <b>'+score_text+'</b> · flag threshold:75/100.</p><p>This is an uncalibrated score, not a cheating probability. A flag requests review; a non-flag does not prove legitimate play.</p><p>Published live windows: '+str(result['windows'])+' · eligible tracking windows: '+str(coverage['eligible_windows'])+'.</p><p>'+warnings+'</p><p><a href="analysis/review.html">Inspect replay trajectory evidence</a> · <a href="prediction.json">Measurement and provenance details</a></p></html>'
    (output/'result.html').write_text(page)
    print(json.dumps({k:result[k] for k in ('status','score','threshold','windows')}),flush=True);return result


def validate_holdout(bundle,manifest):
    if manifest.get('role')!='future_phase_evaluation_holdout' or manifest.get('features_inspected') is not False or manifest.get('fresh_holdout') is not True or not manifest['cases']:raise ValueError('Need explicitly untouched reserved metadata')
    blocked=set(bundle['excluded_participants']);used=set();hashes={c['demo_sha256'] for c in bundle['training']};targets=set()
    for case in manifest['cases']:
        if case.get('features_inspected') is not False or case['label'] not in ('cheating','legitimate') or not isinstance(case['steamid'],str) or not case['steamid'].isdigit():raise ValueError('Holdout metadata differs')
        if case['steamid'] in targets or case['demo_sha256'] in hashes or digest(case['demo'])!=case['demo_sha256'] or digest(case['source_label_file'])!=case['source_label_sha256']:raise ValueError('Holdout source/identity conflict')
        participants=participant_ids(case['demo'])
        if participants!=case['participants'] or case['steamid'] not in participants or set(participants)&(blocked|used):raise ValueError('Holdout participant overlap/identity conflict')
        targets.add(case['steamid']);hashes.add(case['demo_sha256']);used.update(participants)


def summarize(rows):
    scored=[r for r in rows if r['status'] in ('flag_for_review','not_flagged')];neg=[r for r in scored if r['label']=='legitimate'];pos=[r for r in scored if r['label']=='cheating'];fp=sum(r['flagged'] for r in neg)
    upper=float(beta.ppf(.95,fp+1,len(neg)-fp)) if neg and fp<len(neg) else (1. if neg else None)
    return dict(cases=len(rows),scored=len(scored),unresolved=len(rows)-len(scored),legitimate_scored=len(neg),false_flags=fp,
        cheating_scored=len(pos),cheating_flagged=sum(r['flagged'] for r in pos),false_positive_fraction=fp/len(neg) if neg else None,
        conditional_one_sided_95_upper_fpr=upper,
        caveat='Negative-only cohort cannot estimate detection. Bound assumes independent representative correctly labeled cases; archive convenience sampling restricts population inference. Unresolved cases are not correct negatives.')


def evaluate_once(model_directory,holdout,output):
    model_directory,holdout,output=map(Path,(model_directory,holdout,output));bundle=load(model_directory)
    if output.exists():raise ValueError('Use a new evaluation directory')
    if digest(holdout)!=bundle['reserved_holdout_sha256']:raise ValueError('Holdout differs from frozen reservation')
    consumed=holdout.with_suffix('.consumed.json')
    if consumed.exists():raise ValueError('This holdout is consumed; do not reuse it as fresh evaluation')
    manifest=json.loads(holdout.read_text());validate_holdout(bundle,manifest)
    receipt=dict(started_at_utc=now(),model_sha256=digest(model_directory/'model.json'),holdout_sha256=digest(holdout),output=str(output.resolve()),
        case_ids=[c['case_id'] for c in manifest['cases']],note='Single-use holdout consumed before feature extraction, including errors/partial runs. Metadata declaration remains immutable and is superseded by this usage receipt.')
    write_json(consumed,receipt);output.mkdir(parents=True,exist_ok=False);write_json(output/'start.json',receipt);rows=[]
    for i,c in enumerate(manifest['cases'],1):
        try:r=predict(model_directory,c['demo'],c['steamid'],output/f'case_{i:03d}')
        except Exception as error:r=dict(status='error',flagged=None,score=None,error_type=type(error).__name__,error=str(error))
        row=dict(r,case_id=c['case_id'],label=c['label']);rows.append(row);write_json(output/f'prediction_{i:03d}.json',row);print(c['case_id'],row['status'],flush=True)
    result=dict(predictions=rows,summary=summarize(rows),consumption_sha256=digest(consumed),model_sha256=receipt['model_sha256'],holdout_sha256=receipt['holdout_sha256'])
    write_json(output/'evaluation.json',result);lines=['# Frozen offline holdout evaluation','',json.dumps(result['summary'],indent=2),'','| Case | Label | Score | Decision |','| --- | --- | ---: | --- |']
    for row in rows:lines.append(f"| {row['case_id']} | {row['label']} | {row.get('score')} | {row['status']} |")
    (output/'report.md').write_text('\n'.join(lines)+'\n');print(json.dumps(result['summary']),flush=True);return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    f=sub.add_parser('freeze')
    for n in ('pool','reference','legacy_directory'):f.add_argument(n,type=Path)
    f.add_argument('--output',required=True,type=Path)
    s=sub.add_parser('score');s.add_argument('model',type=Path);s.add_argument('demo',type=Path);s.add_argument('--steamid',required=True);s.add_argument('--output',required=True,type=Path)
    e=sub.add_parser('evaluate');e.add_argument('model',type=Path);e.add_argument('holdout',type=Path);e.add_argument('--output',required=True,type=Path)
    a=p.parse_args(argv)
    if a.command=='freeze':freeze(a.pool,a.reference,a.legacy_directory,a.output)
    elif a.command=='score':predict(a.model,a.demo,a.steamid,a.output)
    else:evaluate_once(a.model,a.holdout,a.output)


if __name__=='__main__':main()

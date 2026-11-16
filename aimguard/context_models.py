"""Offline development benchmark with training-only weapon/shot-count centering."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.preprocessing import StandardScaler

from aimguard.baseline import digest,evaluation_metrics,write_json
from aimguard.combat import FIREARMS
from aimguard.tracking_models import window_features

FAMILIES={
    'pistol':set('glock hkp2000 usp_silencer p250 cz75a tec9 fiveseven elite deagle revolver'.split()),
    'rifle':set('ak47 m4a1 m4a1_silencer galilar famas aug sg556'.split()),
    'smg':set('mac10 mp9 mp7 mp5sd ump45 p90 bizon'.split()),
    'sniper':set('awp ssg08 g3sg1 scar20'.split()),
    'shotgun':set('nova xm1014 mag7 sawedoff'.split()),
    'machinegun':set('m249 negev'.split()),
}
FEATURES=['p95_speed','mean_accel','pre_shot_horizontal_error','pre_shot_relative_velocity']
MIN_CASE_WINDOWS=5
MIN_CONTEXT_WINDOWS=5
MIN_REFERENCE_CASES=2
HYPERPARAMETERS=dict(C=1.,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0)


def family(weapon):
    matches=[name for name,weapons in FAMILIES.items() if weapon in weapons]
    if len(matches)!=1:raise ValueError(f'Unknown or multiply classified firearm: {weapon}')
    return matches[0]


def window_rows(report,tracking):
    if len(report['engagements'])!=len(tracking['windows']):raise ValueError('Context window count mismatch')
    rows=[];excluded=Counter()
    for published,track in zip(report['engagements'],tracking['windows']):
        if any(published[key]!=track[key] for key in ('engagement_id','weapon','shot_ticks')):raise ValueError('Context window identity mismatch')
        shots=len(published['shot_ticks'])
        if shots<1 or published['shot_count']!=shots:raise ValueError('Context shot count mismatch')
        group=family(published['weapon']);state='single' if shots==1 else 'multi'
        values,reason=window_features(track,report['assumed_tickrate_hz'])
        near=published['movement_context']['near_shot']
        if values is None:excluded[reason]+=1;continue
        values=[near['p95_speed'],near['mean_accel'],*values]
        if any(value is None or not np.isfinite(value) or value<0 for value in values):
            excluded['missing_joint_measurement']+=1;continue
        rows.append(dict(window_id=published['engagement_id'],weapon=published['weapon'],family=group,state=state,
            context=group+':'+state,log_features=np.log1p(values).tolist()))
    return rows,dict(excluded)


def fit_reference(training_rows,training_labels):
    """Median of per-case medians: long demos do not dominate reference fitting."""
    legitimate=[rows for rows,label in zip(training_rows,training_labels) if label==0]
    if not legitimate:raise ValueError('No legitimate training cases for context reference')
    global_center=np.median([np.median([r['log_features'] for r in rows],axis=0) for rows in legitimate],axis=0).tolist()
    anchors={}
    for key in sorted({row['context'] for rows in legitimate for row in rows}):
        values=[]
        for rows in legitimate:
            selected=[row['log_features'] for row in rows if row['context']==key]
            if len(selected)>=MIN_CONTEXT_WINDOWS:values.append(np.median(selected,axis=0))
        if len(values)>=MIN_REFERENCE_CASES:anchors[key]=dict(center=np.median(values,axis=0).tolist(),cases=len(values))
    families={}
    for key in sorted({row['family'] for rows in legitimate for row in rows}):
        values=[]
        for rows in legitimate:
            selected=[row['log_features'] for row in rows if row['family']==key]
            if len(selected)>=MIN_CONTEXT_WINDOWS:values.append(np.median(selected,axis=0))
        if len(values)>=MIN_REFERENCE_CASES:families[key]=dict(center=np.median(values,axis=0).tolist(),cases=len(values))
    return dict(global_center=global_center,legitimate_cases=len(legitimate),contexts=anchors,families=families)


def case_vector(rows,reference=None):
    if len(rows)<MIN_CASE_WINDOWS:raise ValueError('Insufficient joint context windows')
    values=[];fallback=Counter()
    for row in rows:
        value=np.asarray(row['log_features'],dtype=float)
        if value.shape!=(4,) or not np.isfinite(value).all():raise ValueError('Invalid context feature vector')
        if reference is not None:
            if row['context'] in reference['contexts']:
                anchor=reference['contexts'][row['context']]['center'];fallback['context']+=1
            elif row['family'] in reference['families']:
                anchor=reference['families'][row['family']]['center'];fallback['family']+=1
            else:anchor=reference['global_center'];fallback['global']+=1
            value=value-np.asarray(anchor)
        values.append(value)
    return np.median(values,axis=0),dict(fallback)


def grouped_context(rows,labels,groups,ids,centered):
    labels,groups=np.asarray(labels),np.asarray(groups)
    if not (len(rows)==len(labels)==len(groups)==len(ids)) or len(set(ids))!=len(ids):raise ValueError('Context cases must align uniquely')
    if not np.isin(labels,[0,1]).all():raise ValueError('Context labels must be binary')
    eligible=[i for i,case in enumerate(rows) if len(case)>=MIN_CASE_WINDOWS]
    predictions=[dict(case_id=ids[i],label='cheating' if labels[i] else 'legitimate',status='abstained',error='Insufficient joint context windows') for i in range(len(rows)) if i not in eligible]
    folds=[]
    if len(set(groups[eligible]))<2:raise ValueError('Need independent eligible participant groups')
    for fold,(a,b) in enumerate(LeaveOneGroupOut().split(np.zeros(len(eligible)),labels[eligible],groups[eligible]),1):
        train=np.asarray(eligible)[a];test=np.asarray(eligible)[b]
        record=dict(fold=fold,train_case_ids=[ids[i] for i in train],held_out_case_ids=[ids[i] for i in test])
        if set(groups[train])&set(groups[test]):raise ValueError('Context participant leakage')
        if len(set(labels[train]))<2:
            record['status']='abstained_single_training_class'
            predictions.extend(dict(case_id=ids[i],label='cheating' if labels[i] else 'legitimate',status='abstained',error='Training fold has one class') for i in test)
        else:
            reference=fit_reference([rows[i] for i in train],labels[train]) if centered else None
            train_vectors=[case_vector(rows[i],reference)[0] for i in train]
            test_data=[case_vector(rows[i],reference) for i in test]
            scaler=StandardScaler().fit(train_vectors)
            model=LogisticRegression(**HYPERPARAMETERS).fit(scaler.transform(train_vectors),labels[train])
            scores=model.predict_proba(scaler.transform([value[0] for value in test_data]))[:,1]
            record.update(status='scored',reference=reference,scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),
                coefficients=model.coef_[0].tolist(),intercept=float(model.intercept_[0]))
            for i,value,(_,fallback) in zip(test,scores,test_data):
                predictions.append(dict(case_id=ids[i],label='cheating' if labels[i] else 'legitimate',status='scored',
                    baseline_score=float(value),flagged=bool(value>=.5),fold=fold,context_fallback_windows=fallback))
        folds.append(record)
    predictions.sort(key=lambda row:ids.index(row['case_id']))
    if len(predictions)!=len(ids) or len({row['case_id'] for row in predictions})!=len(ids):raise ValueError('Context predictions incomplete')
    metrics=evaluation_metrics(predictions)
    for key in ('detection_rate','false_positive_rate','precision','accuracy'):metrics[key].pop('exact_95_interval',None)
    metrics['diagnostic_only']=True
    return dict(predictions=predictions,folds=folds,metrics=metrics)


def compare(pool,baseline_directory,output):
    pool,baseline_directory,output=map(Path,(pool,baseline_directory,output))
    manifest=json.loads((pool/'manifest.json').read_text());receipt=json.loads((pool/'pool-receipt.json').read_text())
    protocol=json.loads((baseline_directory/'protocol.json').read_text());inputs=json.loads((baseline_directory/'inputs.json').read_text())
    baseline=json.loads((baseline_directory/'comparison.json').read_text())
    if (manifest.get('role')!='development' or manifest.get('features_inspected') is not True or receipt['manifest_sha256']!=digest(pool/'manifest.json')
        or protocol['manifest_sha256']!=digest(pool/'manifest.json') or baseline['protocol_sha256']!=digest(baseline_directory/'protocol.json')
        or baseline['inputs_sha256']!=digest(baseline_directory/'inputs.json') or inputs['groups']!=receipt['groups']):raise ValueError('Context input receipt mismatch')
    if protocol['threshold']!=.5 or protocol['hyperparameters']!=HYPERPARAMETERS:raise ValueError('Context baseline protocol mismatch')
    if set.union(*FAMILIES.values())!=FIREARMS or sum(map(len,FAMILIES.values()))!=len(FIREARMS):raise ValueError('Firearm grouping incomplete')
    cases=manifest['cases'];ids=[case['case_id'] for case in cases]
    members=[case_id for group in receipt['groups'].values() for case_id in group]
    if len(set(ids))!=len(ids) or len(set(members))!=len(members) or set(ids)!=set(members):raise ValueError('Context group identities mismatch')
    if any(case['label'] not in ('cheating','legitimate') for case in cases):raise ValueError('Unknown context label')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(),role='exploratory_development',
        cases=[dict(case_id=case_id) for case_id in ids],threshold=.5,hyperparameters=HYPERPARAMETERS,
        families={key:sorted(value) for key,value in FAMILIES.items()},feature_names=FEATURES,min_case_windows=MIN_CASE_WINDOWS,
        min_context_windows_per_reference_case=MIN_CONTEXT_WINDOWS,min_legitimate_reference_cases=MIN_REFERENCE_CASES,
        normalization='Training legitimate per-case log-window medians; context median, family fallback, global fallback. No held-out reference fitting.',
        recipes=['copied speed_and_tracking','joint_window_log_baseline','weapon_shot_context'],
        manifest_sha256=digest(pool/'manifest.json'),baseline_comparison_sha256=digest(baseline_directory/'comparison.json'),
        code_sha256={name:digest(Path(__file__).with_name(name)) for name in ('context_models.py','tracking_models.py','development_models.py','baseline.py','core.py')},
        dependencies={name:importlib.metadata.version(name) for name in ('numpy','scipy','scikit-learn')},
        note='Fixed choices before fitting; no parameter/eligibility/threshold search. Cases are inspected development data, not a fresh holdout.'))
    all_rows=[];coverage=[]
    for index,case in enumerate(cases,1):
        report_path=pool/'analysis'/f'job_{index:04d}'/'report.json';track_path=pool/'tracking'/f'case_{index:04d}.json'
        expected=receipt['cases'][index-1]
        if expected['case_id']!=case['case_id'] or digest(report_path)!=expected['report_sha256'] or digest(track_path)!=expected['tracking_sha256']:
            raise ValueError('Context source checksum mismatch')
        prior=inputs['cases'][index-1];prior_tracking=inputs['tracking'][index-1]
        if prior['case_id']!=case['case_id'] or prior['report_sha256']!=expected['report_sha256'] or prior_tracking['case_id']!=case['case_id'] or prior_tracking['tracking_sha256']!=expected['tracking_sha256']:
            raise ValueError('Context pool differs from original baseline inputs')
        report=json.loads(report_path.read_text());tracking=json.loads(track_path.read_text())
        if report['steamid']!=case['steamid'] or report['source_sha256']!=case['demo_sha256'] or tracking['summary']['case_id']!=case['case_id'] or tracking['summary']['label']!=case['label']:
            raise ValueError('Context source identity mismatch')
        rows,excluded=window_rows(report,tracking);all_rows.append(rows)
        coverage.append(dict(case_id=case['case_id'],label=case['label'],eligible_windows=len(rows),excluded=excluded,
            context_windows=dict(Counter(row['context'] for row in rows)),report_sha256=digest(report_path),tracking_sha256=digest(track_path)))
    write_json(output/'inputs.json',dict(cases=coverage,window_rows=all_rows,groups=receipt['groups']))
    by_case={case_id:int(group) for group,members in receipt['groups'].items() for case_id in members}
    groups=[by_case[case_id] for case_id in ids];labels=[int(case['label']=='cheating') for case in cases]
    original=baseline['models']['speed_and_tracking']
    if len(original['predictions'])!=len(ids) or {row['case_id']:row['label'] for row in original['predictions']}!={case['case_id']:case['label'] for case in cases}:
        raise ValueError('Copied baseline predictions mismatch')
    models=dict(speed_and_tracking=original,joint_window_log_baseline=grouped_context(all_rows,labels,groups,ids,False),
        weapon_shot_context=grouped_context(all_rows,labels,groups,ids,True))
    result=dict(cases=len(ids),participant_groups=len(set(groups)),models=models,protocol_sha256=digest(output/'protocol.json'),inputs_sha256=digest(output/'inputs.json'),
        interpretation='Post-feedback development comparison. Context centering is trained inside each fold; no fresh accuracy or classifier replacement claim.')
    write_json(output/'comparison.json',result)
    lines=['# Weapon and grouped-shot context development experiment','',
        'All cases are inspected development data. Whole participant groups are held out; references, scaler and classifier use training cases only.',
        'Weapon families are fixed analysis groupings. Single/multi denotes grouped shot count, not inferred trigger mode or validated recoil state.',
        '', '| Recipe | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,model in models.items():
        c=model['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {model['metrics']['abstentions']} |")
    lines+=['','Joint-window baseline and context recipe use identical eligible window measurements. Their difference is training-only legitimate context centering.',
        'Original speed/acceleration case medians can use a different window subset; the copied four-feature baseline is contextual history, not the exact aggregation control.',
        'Context reference medians weight legitimate training cases equally, requiring five windows per reference case/context and two such cases. Sparse contexts fall back to family, then global legitimate case medians, with counts recorded.',
        'Context residuals are signed log-space deviations. StandardScaler and balanced logistic regression C=1 are fitted on training case vectors, cutoff 0.5.',
        'No damage recipients, source-model predictions, post-feedback threshold search or held-out labels are used to fit references. No new model is frozen. Historical failed fresh evaluation remains unchanged.','']
    (output/'report.md').write_text('\n'.join(lines));print('\n'.join(lines[:11]),flush=True)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('pool',type=Path);parser.add_argument('baseline_directory',type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args(argv)
    compare(args.pool,args.baseline_directory,args.output)


if __name__=='__main__':main()

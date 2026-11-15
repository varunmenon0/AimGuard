"""Post-evaluation diagnostics; never refit, tune, or revise historical outcomes."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
from scipy.special import expit

from aimguard.baseline import digest, write_json, evaluation_metrics
from aimguard.tracking_baseline import load_model
from aimguard.tracking_models import window_features


def contributions(bundle,values):
    values=np.asarray(values,dtype=float)
    names=bundle['feature_names'];mean=np.asarray(bundle['scaler_mean']);scale=np.asarray(bundle['scaler_scale'])
    coefficients=np.asarray(bundle['coefficients'])
    if values.shape!=(len(names),) or not np.isfinite(values).all() or (values<0).any():
        raise ValueError('Invalid diagnostic feature vector')
    if mean.shape!=values.shape or scale.shape!=values.shape or coefficients.shape!=values.shape or (scale<=0).any():
        raise ValueError('Invalid model dimensions/scales')
    transformed=np.log1p(values);standardized=(transformed-mean)/scale
    parts=coefficients*standardized
    margin=float(bundle['intercept']+parts.sum());probability=float(expit(margin))
    if not np.isfinite(np.r_[parts,margin,probability]).all():raise ValueError('Nonfinite diagnostic contribution')
    return dict(raw_features=dict(zip(names,values.tolist())),standardized_features=dict(zip(names,standardized.tolist())),
        contributions=dict(zip(names,parts.tolist())),intercept=bundle['intercept'],margin=margin,
        frozen_score=probability,flagged=probability>=bundle['threshold'])


def summarize(records,names):
    """Descriptive case-level summaries, never window-level significance tests."""
    result=[]
    for cohort in sorted({r['cohort'] for r in records}):
        for label in ('legitimate','cheating'):
            rows=[r for r in records if r['cohort']==cohort and r['label']==label]
            if not rows:continue
            metrics={}
            for name in names:
                values=np.asarray([r['raw_features'][name] for r in rows])
                metrics[name]=dict(median=float(np.median(values)),p25=float(np.percentile(values,25)),
                    p75=float(np.percentile(values,75)),minimum=float(min(values)),maximum=float(max(values)),
                    mean_margin_contribution=float(np.mean([r['contributions'][name] for r in rows])))
            result.append(dict(cohort=cohort,label=label,cases=len(rows),features=metrics,
                mean_margin=float(np.mean([r['margin'] for r in rows]))))
    return result


def context(report,tracking):
    windows=report['engagements']
    counts=Counter(w['weapon'] for w in windows)
    if len(windows)!=len(tracking['windows']):raise ValueError('Tracking/report window counts differ')
    per_weapon={}
    for published,track in zip(windows,tracking['windows']):
        if any(published[key]!=track[key] for key in ('engagement_id','weapon','shot_ticks')):
            raise ValueError('Tracking/report window identity mismatch')
        feature,reason=window_features(track,report['assumed_tickrate_hz'])
        if feature is None:continue
        near=published['movement_context']['near_shot']
        values=[near['p95_speed'],near['mean_accel'],*feature]
        if any(value is None or not np.isfinite(value) or value<0 for value in values):continue
        per_weapon.setdefault(published['weapon'],[]).append(values)
    return dict(windows=len(windows),weapon_windows=dict(counts),
        weapon_fractions={weapon:count/len(windows) for weapon,count in counts.items()} if windows else {},
        per_weapon_features={weapon:dict(eligible_windows=len(values),medians=np.median(values,axis=0).tolist())
            for weapon,values in per_weapon.items()},
        note='Weapon summaries use jointly eligible window measurements; these are not substituted frozen model inputs.')


def analyze(model_directory,development_manifest,development_analysis,development_tracking,evaluation_directory,output):
    model_directory,development_manifest,development_analysis,development_tracking,evaluation_directory=map(Path,
        (model_directory,development_manifest,development_analysis,development_tracking,evaluation_directory))
    bundle=load_model(model_directory);names=bundle['feature_names']
    manifest=json.loads(development_manifest.read_text())
    if manifest.get('role')!='development' or digest(development_manifest)!=bundle['development_manifest_sha256']:
        raise ValueError('Development manifest mismatch')
    if len(manifest['cases'])!=len(bundle['development']):raise ValueError('Development count mismatch')
    evaluation=json.loads((evaluation_directory/'evaluation.json').read_text())
    start=json.loads((evaluation_directory/'start-receipt.json').read_text())
    if evaluation['model_sha256']!=digest(model_directory/'model.json') or any(start[key]!=evaluation[key] for key in ('model_sha256','reserved_manifest_sha256','threshold')):
        raise ValueError('Evaluation frozen receipt mismatch')
    if evaluation_metrics(evaluation['predictions'])!=evaluation['metrics']:
        raise ValueError('Evaluation metrics differ from preserved predictions')
    records=[];provenance={};abstentions=[]
    for index,(case,training) in enumerate(zip(manifest['cases'],bundle['development']),1):
        if any(case[key]!=training[key] for key in ('case_id','steamid','match_id','label','demo_sha256')):
            raise ValueError('Development case identity mismatch')
        directory=development_analysis/f'job_{index:04d}';tracking_path=development_tracking/f'case_{index:04d}.json'
        if digest(directory/'report.json')!=training['report_sha256'] or digest(tracking_path)!=training['tracking_sha256']:
            raise ValueError('Development source checksum mismatch')
        report=json.loads((directory/'report.json').read_text());tracking=json.loads(tracking_path.read_text())
        record=dict(cohort='original_development',case_id=case['case_id'],label=case['label'],
            **contributions(bundle,training['features']),context=context(report,tracking),
            prediction_scope='Full-pool fitted-model explanation; not an out-of-fold performance estimate',
            source=dict(directory=str(directory.resolve()),tracking=str(tracking_path.resolve())))
        records.append(record);provenance['original_development/'+case['case_id']]=dict(report=digest(directory/'report.json'),tracking=digest(tracking_path))
    for index,row in enumerate(evaluation['predictions'],1):
        if row['status']!='scored':
            abstentions.append(row);continue
        directory=evaluation_directory/f'case_{index:03d}'
        if digest(directory/'report.json')!=row['report_sha256'] or digest(directory/'tracking.json')!=row['tracking_sha256']:
            raise ValueError('Evaluation source checksum mismatch')
        report=json.loads((directory/'report.json').read_text());tracking=json.loads((directory/'tracking.json').read_text())
        if report['steamid']!=row['steamid']:raise ValueError('Evaluation player identity mismatch')
        values=[row['features'][name] for name in names];explanation=contributions(bundle,values)
        if not np.isclose(explanation['frozen_score'],row['baseline_score'],rtol=0,atol=1e-12) or explanation['flagged']!=row['flagged']:
            raise ValueError('Diagnostic explanation does not reproduce frozen decision')
        records.append(dict(cohort='consumed_evaluation',case_id=row['case_id'],label=row['label'],
            **explanation,context=context(report,tracking),prediction_scope='Preserved frozen evaluation prediction',
            source=dict(directory=str(directory.resolve()),tracking=str((directory/'tracking.json').resolve()))))
        provenance['consumed_evaluation/'+row['case_id']]=dict(report=row['report_sha256'],tracking=row['tracking_sha256'])
    summaries=summarize(records,names)
    legitimate_training=[r for r in records if r['cohort']=='original_development' and r['label']=='legitimate']
    false_flags=[r for r in records if r['cohort']=='consumed_evaluation' and r['label']=='legitimate' and r['flagged']]
    bounds={name:(min(r['raw_features'][name] for r in legitimate_training),max(r['raw_features'][name] for r in legitimate_training)) for name in names}
    for record in false_flags:
        record['outside_original_legitimate_range']=[name for name in names if not bounds[name][0]<=record['raw_features'][name]<=bounds[name][1]]
        record['largest_positive_term']=max((name for name in names if record['contributions'][name]>0),key=lambda name:record['contributions'][name],default=None)
    weapon_summary=[]
    weapons=sorted({w for r in records if r['label']=='legitimate' for w in r['context']['weapon_windows']})
    for weapon in weapons:
        groups={cohort:[r for r in records if r['cohort']==cohort and r['label']=='legitimate'] for cohort in ('original_development','consumed_evaluation')}
        eligible={cohort:[r['context']['per_weapon_features'][weapon] for r in rows
            if r['context']['per_weapon_features'].get(weapon,{}).get('eligible_windows',0)>=5] for cohort,rows in groups.items()}
        weapon_summary.append(dict(weapon=weapon,
            mean_case_window_share={cohort:float(np.mean([r['context']['weapon_fractions'].get(weapon,0) for r in rows])) for cohort,rows in groups.items()},
            eligible_cases={cohort:len(values) for cohort,values in eligible.items()},
            matched_case_medians={cohort:np.median([v['medians'] for v in values],axis=0).tolist() if len(values)>=2 else None for cohort,values in eligible.items()},
            reporting_rule='At least five jointly eligible windows per case/weapon and two cases per cohort for matched summaries; no model refit'))
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    result=dict(role='post_evaluation_development_diagnostic',feature_names=names,cases=records,summaries=summaries,
        false_flag_case_ids=[r['case_id'] for r in false_flags],false_flag_largest_positive_terms=dict(Counter(r['largest_positive_term'] for r in false_flags)),
        false_flags_within_all_original_legitimate_ranges=sum(not r['outside_original_legitimate_range'] for r in false_flags),
        weapon_context=weapon_summary,abstentions=abstentions,
        model_sha256=digest(model_directory/'model.json'),evaluation_sha256=digest(evaluation_directory/'evaluation.json'),
        code_sha256=digest(__file__),input_sha256=provenance,
        limitations=['Margin contributions explain arithmetic, not causal cheating behavior',
            'Feature distributions are observed sample differences, not proof of a single cause',
            'This evaluated cohort is now inspected development feedback; no new held-out performance claim',
            'Full-model development scores are explanatory training scores, not CV results',
            'Weapon matching is descriptive and leaves visibility, skill, range and recoil uncontrolled',
            'No refitting, threshold sweep, feature selection or historical prediction changes'])
    write_json(output/'diagnostics.json',result)
    print(f'{len(false_flags)} false flags explained; {result["false_flags_within_all_original_legitimate_ranges"]} within all original legitimate feature ranges',flush=True)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('model_directory','development_manifest','development_analysis','development_tracking','evaluation_directory'):parser.add_argument(name,type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args(argv)
    analyze(args.model_directory,args.development_manifest,args.development_analysis,args.development_tracking,args.evaluation_directory,args.output)


if __name__=='__main__':main()

"""Combine inspected cases into development data without copying or relabeling demos."""
import argparse
import json
from pathlib import Path

from aimguard.baseline import digest,write_json
from aimguard.development_models import participant_groups
from aimguard.tracking_baseline import load_model


def prepare(model_directory,manifest_path,analysis_root,tracking_root,reserved_path,evaluation_root,output):
    model_directory,manifest_path,analysis_root,tracking_root,reserved_path,evaluation_root=map(Path,
        (model_directory,manifest_path,analysis_root,tracking_root,reserved_path,evaluation_root))
    bundle=load_model(model_directory);manifest=json.loads(manifest_path.read_text())
    reserved=json.loads(reserved_path.read_text());evaluation=json.loads((evaluation_root/'evaluation.json').read_text())
    if (manifest.get('role')!='development' or digest(manifest_path)!=bundle['development_manifest_sha256']
        or evaluation['model_sha256']!=digest(model_directory/'model.json')
        or evaluation['reserved_manifest_sha256']!=digest(reserved_path)):
        raise ValueError('Expanded development source receipts mismatch')
    if len(manifest['cases'])!=len(bundle['development']) or len(reserved['cases'])!=len(evaluation['predictions']):
        raise ValueError('Expanded source case counts mismatch')
    cases=[];sources=[];participants=[];summaries=[]
    for index,(case,training) in enumerate(zip(manifest['cases'],bundle['development']),1):
        if any(case[key]!=training[key] for key in ('case_id','steamid','match_id','label','demo_sha256')):
            raise ValueError('Original development identity mismatch')
        directory=analysis_root/f'job_{index:04d}';tracking=tracking_root/f'case_{index:04d}.json'
        if digest(directory/'report.json')!=training['report_sha256'] or digest(tracking)!=training['tracking_sha256']:
            raise ValueError('Original development checksum mismatch')
        cases.append(dict(case,role='development',features_inspected=True,origin='original development pool'))
        sources.append((directory,tracking));participants.append(set(training['participants']))
    for index,(case,row) in enumerate(zip(reserved['cases'],evaluation['predictions']),1):
        if any(case[key]!=row[key] for key in ('case_id','steamid','match_id','label')):
            raise ValueError('Consumed evaluation identity mismatch')
        if row['status']!='scored':raise ValueError('Pool preparation requires scored extraction; do not silently drop abstentions')
        directory=evaluation_root/f'case_{index:03d}';tracking=directory/'tracking.json'
        if digest(directory/'report.json')!=row['report_sha256'] or digest(tracking)!=row['tracking_sha256']:
            raise ValueError('Consumed evaluation checksum mismatch')
        cases.append(dict(case,role='development',features_inspected=True,origin='consumed frozen tracking evaluation'))
        sources.append((directory,tracking));participants.append(set(case['participants']))
    for key in ('case_id','steamid','match_id','demo_sha256'):
        if len({case[key] for case in cases})!=len(cases):raise ValueError(f'Duplicate development {key}')
    for case,(directory,tracking) in zip(cases,sources):
        report=json.loads((directory/'report.json').read_text());record=json.loads(tracking.read_text())
        if (report['steamid']!=case['steamid'] or report['source_sha256']!=case['demo_sha256']
            or record['summary']['case_id']!=case['case_id'] or record['summary']['label']!=case['label']):
            raise ValueError('Staged report/tracking identity mismatch')
        summaries.append(record['summary'])
    groups=participant_groups(participants);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    (output/'analysis').mkdir();(output/'tracking').mkdir()
    write_json(output/'manifest.json',dict(role='development',features_inspected=True,fresh_holdout=False,cases=cases,
        source_evaluation_sha256=digest(evaluation_root/'evaluation.json'),
        note='All cases already inspected. Consumed evaluation is development feedback, never a reusable fresh holdout.'))
    receipts=[]
    for index,(case,(directory,tracking)) in enumerate(zip(cases,sources),1):
        (output/'analysis'/f'job_{index:04d}').symlink_to(directory.resolve(),target_is_directory=True)
        (output/'tracking'/f'case_{index:04d}.json').symlink_to(tracking.resolve())
        receipts.append(dict(case_id=case['case_id'],report_sha256=digest(directory/'report.json'),tracking_sha256=digest(tracking)))
    write_json(output/'tracking'/'summary.json',dict(role='development_tracking_diagnostic',cases=summaries,
        manifest_sha256=digest(output/'manifest.json'),note='Existing canonical extraction reused by verified local links; no labels or source artifacts changed.'))
    write_json(output/'pool-receipt.json',dict(cases=receipts,groups={str(group):[case['case_id'] for case,g in zip(cases,groups) if g==group] for group in sorted(set(groups))},
        code_sha256=digest(__file__),manifest_sha256=digest(output/'manifest.json'),features_inspected=True,fresh_holdout=False))
    print(f'{len(cases)} inspected cases in {len(set(groups))} participant components; development only',flush=True)
    return len(cases),len(set(groups))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('model_directory','manifest_path','analysis_root','tracking_root','reserved_path','evaluation_root'):parser.add_argument(name,type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args(argv)
    prepare(args.model_directory,args.manifest_path,args.analysis_root,args.tracking_root,args.reserved_path,args.evaluation_root,args.output)


if __name__=='__main__':main()

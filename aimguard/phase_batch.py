"""Isolated v0.6 batch analysis; legacy v0.5 reproduction remains separate."""
import argparse
import json
from pathlib import Path

from aimguard.batch import load_manifest
from aimguard.phase_gameplay import analyze_demo,FEATURE_VERSION


def run_batch(manifest,output,max_plots=0):
    if type(max_plots) is not int or max_plots<0:raise ValueError('max-plots must be nonnegative')
    jobs=load_manifest(manifest);output=Path(output);output.mkdir(parents=True,exist_ok=False);rows=[]
    for index,job in enumerate(jobs,1):
        row=dict(job,artifacts=f'job_{index:04d}')
        try:
            report=analyze_demo(job['demo'],job['steamid'],output/row['artifacts'],tickrate=job['tickrate'],max_plots=max_plots)
            quality=report['data_quality'];warnings=[]
            if report['analysis_status']!='complete':warnings.append('insufficient_live_evidence')
            if quality['round_event_anomalies']:warnings.append('round_event_anomalies')
            row.update(status='warning' if warnings else 'passed',warnings=warnings,source_sha256=report['source_sha256'],
                feature_version=report['feature_version'],active_samples=quality['active_samples'],windows=report['engagement_count'],
                phase_exclusions=quality['phase_excluded_previously_active'],violations=report['structural_violations'])
        except Exception as error:row.update(status='error',error_type=type(error).__name__,error=str(error))
        rows.append(row);print(f"{index}/{len(jobs)}: {row['status']}",flush=True)
    result=dict(feature_version=FEATURE_VERSION,jobs=rows,counts={status:sum(r['status']==status for r in rows) for status in ('passed','warning','error')},
                note='Phase-checked structural analysis only; warnings/errors and absent windows are not legitimate classifications.')
    (output/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('manifest',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--max-plots',type=int,default=0)
    args=parser.parse_args(argv);summary=run_batch(args.manifest,args.output,args.max_plots);return 1 if summary['counts']['error'] else 0


if __name__=='__main__':raise SystemExit(main())

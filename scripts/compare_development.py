"""Summarize temporal development features by case and weapon."""
import argparse
import html
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

METRICS = {
    'near_shot_stop_fraction': 'Near-shot stop fraction',
    'near_shot_mean_turn': 'Near-shot mean turn (radians)',
    'near_shot_yaw_reversals_per_second': 'Near-shot yaw reversals/s',
    'near_shot_pitch_reversals_per_second': 'Near-shot pitch reversals/s',
    'pre_post_speed_log_ratio': 'Before/after speed log ratio',
    'near_shot_peak_offset_seconds': 'Near-shot speed peak offset (s)',
}


def compare(manifest_path, analysis_root, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    manifest = json.loads(Path(manifest_path).read_text())
    if manifest.get('role') != 'development':
        raise ValueError('This comparison expects an explicitly designated development pool')
    records, summaries, report_hashes = [], [], {}
    reference_signature = None
    for index, case in enumerate(manifest['cases'], 1):
        report = json.loads((Path(analysis_root) / f'job_{index:04d}' / 'report.json').read_text())
        if report['steamid'] != case['steamid'] or report['source_sha256'] != case['demo_sha256']:
            raise ValueError(f"Report identity mismatch for {case['case_id']}")
        if case['label'] not in ('cheating', 'legitimate'):
            raise ValueError('Unknown development label')
        signature = dict(feature_version=report['feature_version'],
                         configuration={key:report['configuration'][key] for key in
                             ('weapon_mode','near_shot_seconds','pre_seconds','post_seconds','shot_gap_seconds')},
                         assumed_tickrate_hz=report['assumed_tickrate_hz'])
        if signature['configuration']['weapon_mode'] != 'firearms':
            raise ValueError('Development comparison requires firearm-filtered reports')
        if reference_signature is None:
            reference_signature = signature
        elif signature != reference_signature:
            raise ValueError('Development reports use different extraction configurations')
        report_path = Path(analysis_root) / f'job_{index:04d}' / 'report.json'
        report_hashes[case['case_id']] = hashlib.sha256(report_path.read_bytes()).hexdigest()
        for window in report['engagements']:
            near_count = window['movement_context']['near_shot']['speed_intervals']
            profile = window['shot_time_profile']
            if sum(profile[k] for k in ('pre_shot_intervals', 'on_shot_intervals', 'post_shot_intervals')) != near_count:
                raise ValueError('Shot timing categories do not partition near-shot observations')
            records.append(dict(case_id=case['case_id'], label=case['label'], weapon=window['weapon'],
                                window_id=window['engagement_id'], **{k:profile[k] for k in METRICS}))
        summaries.append(dict(case_id=case['case_id'],label=case['label'],windows=report['engagement_count'],
                              non_alive_positive_health_samples=report['data_quality']['non_alive_positive_health_samples']))
    if not records:
        raise ValueError('No published firearm windows to compare')
    frame = pd.DataFrame(records)
    case_order = [c['case_id'] for c in manifest['cases']]
    for summary in summaries:
        part = frame.loc[frame.case_id.eq(summary['case_id'])]
        summary['metrics'] = {}
        for metric in METRICS:
            values = part[metric].dropna()
            summary['metrics'][metric] = dict(eligible_windows=len(values),
                median=float(values.median()) if len(values) else None,
                p25=float(values.quantile(.25)) if len(values) else None,
                p75=float(values.quantile(.75)) if len(values) else None)
    weapon_cases = []
    for (case_id, label, weapon), part in frame.groupby(['case_id','label','weapon']):
        for metric in METRICS:
            values = part[metric].dropna()
            weapon_cases.append(dict(case_id=case_id,label=label,weapon=weapon,metric=metric,
                                     windows=len(part),eligible_windows=len(values),
                                     median=float(values.median()) if len(values) else None))
    matched = []
    for weapon in sorted(frame.weapon.unique()):
        for metric in METRICS:
            eligible = [r for r in weapon_cases if r['weapon']==weapon and r['metric']==metric
                        and r['eligible_windows']>=5]
            positive = [r['median'] for r in eligible if r['label']=='cheating']
            negative = [r['median'] for r in eligible if r['label']=='legitimate']
            if len(positive)>=2 and len(negative)>=2:
                matched.append(dict(weapon=weapon,metric=metric,cheating_cases=len(positive),
                                    legitimate_cases=len(negative),cheating_median=float(np.median(positive)),
                                    legitimate_median=float(np.median(negative))))
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    fig, axes = plt.subplots(2,3,figsize=(18,10),layout='constrained')
    for axis, (metric,title) in zip(axes.flat,METRICS.items()):
        for index, case in enumerate(manifest['cases']):
            values = frame.loc[frame.case_id.eq(case['case_id']),metric].dropna().to_numpy()
            if not len(values):
                continue
            color = '#b64841' if case['label']=='cheating' else '#147756'
            jitter = np.random.default_rng(index).uniform(-.16,.16,len(values))
            axis.scatter(index+jitter,values,s=5,alpha=.08,color=color,rasterized=True)
            q25,median,q75 = np.quantile(values,[.25,.5,.75])
            axis.errorbar(index,median,yerr=[[median-q25],[q75-median]],fmt='o',color=color,capsize=3)
        axis.set_title(title)
        axis.set_xticks(range(len(case_order)),case_order,rotation=65,fontsize=8)
        axis.grid(axis='y',alpha=.2)
    fig.suptitle(f'Expanded development pool · {len(summaries)} selected player/match cases\nDots = case medians; bars = middle 50%; faint points = windows')
    fig.legend(handles=[Line2D([],[],marker='o',linestyle='',color='#b64841',label='Cheating label'),
                        Line2D([],[],marker='o',linestyle='',color='#147756',label='Legitimate label')],
               loc='outside lower center',ncol=2)
    fig.savefig(output/'temporal-distributions.png',dpi=160)
    plt.close(fig)
    lines=['# Expanded temporal development comparison','',
           f"{len(summaries)} player/match cases; {len(frame)} firearm windows. {sum(c['label']=='cheating' for c in manifest['cases'])} cheating labels and {sum(c['label']=='legitimate' for c in manifest['cases'])} legitimate labels.",
           'D cases are the original six study cases. E cases were previously evaluated by the first frozen baseline and now form development evidence.',
           'No fresh detection accuracy estimate is computed here. The original evaluation is preserved.',
           '', '| Case | Label | Windows | Retained-health non-alive samples excluded |',
           '| --- | --- | ---: | ---: |']
    for row in summaries:
        lines.append(f"| {row['case_id']} | {row['label']} | {row['windows']} | {row['non_alive_positive_health_samples']} |")
    lines += ['', '## Shared-weapon comparisons','',
              'Each entry compares medians of case medians within a weapon. Cases are weighted equally.',
              'Display requires five eligible windows per case/metric and two cases per label. Those are reporting cutoffs and do not establish sufficient evidence for detection.',
              '', '| Weapon | Feature | Cheating cases | Legitimate cases | Cheating case median | Legitimate case median |',
              '| --- | --- | ---: | ---: | ---: | ---: |']
    for row in matched:
        lines.append(f"| {row['weapon']} | {METRICS[row['metric']]} | {row['cheating_cases']} | {row['legitimate_cases']} | {row['cheating_median']:.4g} | {row['legitimate_median']:.4g} |")
    lines += ['', '## Interpretation limits','',
              'These features describe movement timing and direction. They do not measure target error, visibility, or recoil compensation.',
              'Direction reversals require adjacent near-shot intervals and axis steps of at least 0.05 degrees. Turn angles require nonzero adjacent two-dimensional steps. Missing observations remain null.',
              'Before, at, and after categories reference the nearest grouped shot. A tie references the earlier shot. Speed intervals use their ending tick.',
              'The before/after log ratio uses log1p(speed in degrees/s) differences. Positive values indicate higher pre-shot p95 speed.',
              'Stop fraction uses the existing 2-degrees/s cutoff. Peak offsets use the first maximum in time; stationary motion has no peak timing.',
              'Windows within a match are correlated and may overlap. Weapon comparisons reduce one source of variation; skill, targets, recoil, and recording artifacts remain uncontrolled.',
              'Labels indicate cheating per player/match with unspecified subtype. Source identity precision caveats remain in the acquisition records.',
              'All 17 cases are development data. A later revised model needs a fresh cohort for a held-out performance claim.', '']
    lines += ['', '## Extraction provenance', '',
              'Feature version: '+reference_signature['feature_version'],
              'Configuration: '+json.dumps(reference_signature['configuration'], sort_keys=True),
              'Assumed tick rate: '+str(reference_signature['assumed_tickrate_hz'])+' Hz',
              'Manifest and report SHA-256 hashes are recorded in comparison-provenance.json.', '']
    (output/'comparison-provenance.json').write_text(json.dumps(dict(
        manifest_sha256=hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest(),
        report_sha256=report_hashes,extraction=reference_signature),indent=2)+'\n')
    text='\n'.join(lines)
    (output/'report.md').write_text(text)
    (output/'case-summaries.json').write_text(json.dumps(summaries,indent=2)+'\n')
    (output/'weapon-case-summaries.json').write_text(json.dumps(weapon_cases,indent=2)+'\n')
    (output/'matched-weapon-summary.json').write_text(json.dumps(matched,indent=2)+'\n')
    (output/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>AimGuard temporal development</title><style>body{font:16px system-ui;max-width:1200px;margin:30px auto;padding:20px;color:#17392b}img{width:100%}pre{white-space:pre-wrap;font:inherit;line-height:1.5}</style><h1>Temporal movement development</h1><img src="temporal-distributions.png" alt="Six temporal measurements across seventeen cases"><pre>'+html.escape(text)+'</pre></html>')
    print(f'{len(summaries)} cases; {len(frame)} firearm windows; {len(matched)} shared-weapon comparisons')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('analysis_root',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        compare(args.manifest,args.analysis_root,args.output)
    except (OSError,ValueError,KeyError) as exc:
        parser.error(str(exc))


if __name__=='__main__':
    main()

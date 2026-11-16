"""Render model arithmetic and distribution diagnostics without model tuning."""
import argparse
import html
import json
from pathlib import Path

import numpy as np
from aimguard.baseline import digest
from scripts.render_target_tracking import PAGE

LABELS={'p95_speed':'Near-shot speed','mean_accel':'Near-shot acceleration',
    'median_pre_shot_absolute_error_degrees':'Pre-shot horizontal error',
    'median_pre_shot_absolute_relative_rate_dps':'Pre-shot relative velocity'}


def render(directory):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    directory=Path(directory);result=json.loads((directory/'diagnostics.json').read_text());names=result['feature_names']
    summaries=result['summaries']
    old=next(row for row in summaries if row['cohort']=='original_development' and row['label']=='legitimate')
    new=next(row for row in summaries if row['cohort']=='consumed_evaluation' and row['label']=='legitimate')
    changes=[new['features'][name]['mean_margin_contribution']-old['features'][name]['mean_margin_contribution'] for name in names]
    fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    for axis,name in zip(axes.flat,names):
        for index,group in enumerate(summaries):
            rows=[r for r in result['cases'] if r['cohort']==group['cohort'] and r['label']==group['label']]
            values=[r['raw_features'][name] for r in rows]
            jitter=np.random.default_rng(index).uniform(-.08,.08,len(values))
            axis.scatter(index+jitter,values,c='#b64841' if group['label']=='cheating' else '#147756',alpha=.7,s=35)
            axis.plot([index-.2,index+.2],[np.median(values)]*2,c='black',lw=2)
        axis.set_xticks(range(len(summaries)),[('New inspected' if g['cohort']=='consumed_evaluation' else 'Original')+'\n'+g['label'] for g in summaries])
        axis.set_title(LABELS.get(name,name));axis.grid(alpha=.15)
    fig.suptitle('Observed case-level feature distributions · post-evaluation development feedback\nDots = player/match summaries; black bars = medians; no significance or causal claim')
    fig.savefig(directory/'feature-distributions.png',dpi=160);plt.close(fig)
    fig,axis=plt.subplots(figsize=(11,5),layout='constrained')
    axis.barh([LABELS.get(name,name) for name in names],changes,color=['#b64841' if v>0 else '#147756' for v in changes])
    axis.axvline(0,color='black',lw=1);axis.set_xlabel('Change in mean logistic margin contribution: new legitimate minus original legitimate')
    axis.set_title('Why the model shifts toward flags on the new legitimate sample\nArithmetic decomposition; not causal behavior attribution')
    fig.savefig(directory/'margin-shift.png',dpi=160);plt.close(fig)
    rows=[]
    for index,row in enumerate(result['cases'],1):
        if row['cohort']!='consumed_evaluation':continue
        path=Path(row['source']['tracking']);key=row['cohort']+'/'+row['case_id']
        if digest(path)!=result['input_sha256'][key]['tracking']:raise ValueError('Tracking viewer input changed')
        record=json.loads(path.read_text());filename=f'tracking_{index:04d}.html'
        (directory/filename).write_text(PAGE.replace('__DATA__',json.dumps(record,allow_nan=False).replace('<',r'\u003c')))
        false=row['label']=='legitimate' and row['flagged']
        terms='; '.join(f'{LABELS.get(name,name)}: {value:+.4f}' for name,value in row['contributions'].items())
        rows.append('<tr>'+f'<td><a href="{filename}">{html.escape(row["case_id"])}</a></td>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in
            (row['label'],f"{row['frozen_score']:.8f}",'False flag' if false else ('Flagged' if row['flagged'] else 'Unflagged'),
             f"{row['margin']:+.8f}",terms,row['context']['weapon_windows']))+'</tr>')
    lines=['# Frozen-model false-flag diagnosis','',
        'This is post-evaluation development feedback. No model, threshold, historical outcome or eligibility rule changed.',
        'Contributions exactly reconstruct the frozen logistic margin: intercept plus coefficient × standardized log1p feature.',
        'They explain the model arithmetic, not whether a player cheated or a causal explanation of behavior.',
        '', f"| Feature | Original legitimate median ({old['cases']} cases) | New legitimate median ({new['cases']} cases) | Mean margin shift |",
        '| --- | ---: | ---: | ---: |']
    for name,change in zip(names,changes):
        lines.append(f"| {LABELS.get(name,name)} | {old['features'][name]['median']:.4f} | {new['features'][name]['median']:.4f} | {change:+.4f} |")
    lines+=['',f"{result['false_flags_within_all_original_legitimate_ranges']}/{len(result['false_flag_case_ids'])} false flags fall within the original legitimate range for every feature. Simple marginal range checks would not reject them.",
        'Largest positive term per false flag: '+str(result['false_flag_largest_positive_terms']),
        'Full-model development scores are explanatory training scores, never out-of-fold performance estimates.',
        '', '## Shared-weapon summaries','',
        'Each case needs five jointly eligible windows for the weapon; each cohort needs two cases. Case medians receive equal weight. Values are descriptive and are not substituted into the classifier.',
        '', '| Weapon | Original/new eligible cases | Original medians: speed, acceleration, error, relative velocity | New medians |',
        '| --- | --- | --- | --- |']
    for row in result['weapon_context']:
        a=row['matched_case_medians']['original_development'];b=row['matched_case_medians']['consumed_evaluation']
        if a is None or b is None:continue
        lines.append(f"| {row['weapon']} | {row['eligible_cases']['original_development']}/{row['eligible_cases']['consumed_evaluation']} | {', '.join(f'{v:.3f}' for v in a)} | {', '.join(f'{v:.3f}' for v in b)} |")
    lines+=['','## Limits','',*['- '+s for s in result['limitations']],
        '', 'Review links retain exact frozen scores to eight decimals. Rounded display values near 0.5 must not be mistaken for changed cutoff decisions.','']
    text='\n'.join(lines);(directory/'report.md').write_text(text)
    (directory/'index.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AimGuard false-flag diagnosis</title><style>body{font:16px system-ui;max-width:1150px;margin:30px auto;padding:20px;color:#17392b}img{width:100%}pre{white-space:pre-wrap}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}.scroll{overflow-x:auto}</style><h1>False-flag diagnosis</h1><p>Post-evaluation development feedback. Model arithmetic and observed sample differences; no new accuracy or causal claim.</p><img src="margin-shift.png" alt="Feature contributions to the legitimate sample margin shift"><img src="feature-distributions.png" alt="Case-level features by cohort and source label"><pre>'+html.escape(text)+'</pre><h2>All preserved evaluation decisions</h2><p>Click a case to inspect its fixed-opponent trajectories. Scores are uncalibrated. Margin is the sum of the feature terms and model intercept.</p><div class="scroll"><table><thead><tr><th>Case</th><th>Source label</th><th>Score</th><th>Decision</th><th>Margin</th><th>Feature contributions</th><th>Weapon windows</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>')
    print(directory/'index.html')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path);args=parser.parse_args(argv);render(args.directory)


if __name__=='__main__':main()

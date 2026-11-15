"""Render saved grouped development diagnostics without refitting models."""
import argparse
import html
import json
from pathlib import Path


def render(directory):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    directory=Path(directory)
    result=json.loads((directory/'comparison.json').read_text())
    protocol=json.loads((directory/'protocol.json').read_text())
    models=result['models']
    case_order=[case['case_id'] for case in protocol['cases']]
    fig,axes=plt.subplots(1,len(models),figsize=(13,9),layout='constrained',squeeze=False)
    for axis,(name,model) in zip(axes.flat,models.items()):
        predictions={row['case_id']:row for row in model['predictions']}
        for index,case_id in enumerate(case_order):
            row=predictions[case_id]
            if row['status']!='scored':
                axis.text(.02,index,'Abstained',va='center')
                continue
            color='#b64841' if row['label']=='cheating' else '#147756'
            wrong=row['flagged']!=(row['label']=='cheating')
            axis.scatter(row['baseline_score'],index,c=color,s=75,
                         edgecolors='black' if wrong else color,linewidths=2 if wrong else 1)
        axis.axvline(protocol['threshold'],linestyle='--',color='#777')
        axis.set_yticks(range(len(case_order)),case_order)
        axis.invert_yaxis();axis.set_xlim(-.025,1.025)
        axis.set_xticks([0,.25,.5,.75,1])
        axis.set_xlabel('Uncalibrated diagnostic score')
        axis.set_title(name.replace('_',' '))
        axis.grid(alpha=.15)
    fig.suptitle(f"Development diagnostics · {result['cases']} cases in {result['participant_groups']} participant groups\nRed = cheating label; green = legitimate label; black outline = error")
    fig.savefig(directory/'model-scores.png',dpi=160)
    plt.close(fig)
    text=(directory/'report.md').read_text()
    text+='\n## Individual development predictions\n\n| Case | Label | Speed score | Speed flag | Timing score | Timing flag |\n| --- | --- | ---: | --- | ---: | --- |\n'
    lookups={name:{row['case_id']:row for row in model['predictions']} for name,model in models.items()}
    for case_id in case_order:
        speed=lookups['speed_acceleration'][case_id]
        timing=lookups['timing_direction'][case_id]
        def score(row):
            return f"{row['baseline_score']:.4f}" if row['status']=='scored' else '—'
        def flag(row):
            return str(row['flagged']) if row['status']=='scored' else 'Abstained'
        text+=f"| {case_id} | {speed['label']} | {score(speed)} | {flag(speed)} | {score(timing)} | {flag(timing)} |\n"
    text+='\nThese results describe development behavior after feature choices informed by this pool. Fresh cases are required for an independent performance claim.\n'
    (directory/'readable-report.md').write_text(text)
    (directory/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>AimGuard grouped development diagnostics</title><style>body{font:17px system-ui;max-width:1150px;margin:30px auto;padding:20px;color:#17392b}img{width:100%}pre{white-space:pre-wrap;font:inherit;line-height:1.5}</style><h1>Grouped development model diagnostics</h1><p>Exploratory comparison on previously inspected cases. No new held-out accuracy claim.</p><img src="model-scores.png" alt="Diagnostic scores for two recipes with errors outlined"><pre>'+html.escape(text)+'</pre></html>')
    print(directory/'index.html')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args(argv)
    render(args.directory)


if __name__=='__main__':
    main()

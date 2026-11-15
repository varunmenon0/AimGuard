"""Render saved horizontal geometry diagnostics without training a model."""
import argparse
import html
import json
from pathlib import Path


def render(directory):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    directory=Path(directory)
    data=json.loads((directory/'summary.json').read_text())
    cases=data['cases']
    fig,axes=plt.subplots(1,2,figsize=(13,8),layout='constrained')
    for index,case in enumerate(cases):
        color='#b64841' if case['label']=='cheating' else '#147756'
        for axis,key in zip(axes,('median_nearest_horizontal_error_degrees','median_same_candidate_error_reduction_degrees')):
            if case[key] is not None:
                axis.scatter(case[key],index,c=color,s=45)
    for axis in axes:
        axis.set_yticks(range(len(cases)),[c['case_id'] for c in cases]);axis.invert_yaxis();axis.grid(alpha=.2)
    axes[0].set_xlabel('Median nearest horizontal bearing error at shot (degrees)')
    axes[1].set_xlabel('Median same-candidate error reduction before shot (degrees)')
    axes[1].axvline(0,color='gray',ls='--')
    fig.suptitle('Horizontal geometry feasibility · development data\nRed = cheating label; green = legitimate label; visibility unknown')
    fig.savefig(directory/'alignment.png',dpi=160);plt.close(fig)
    total=sum(c['shots'] for c in cases)
    available=sum(c['geometry_available'] for c in cases)
    pairs=sum(c['paired_before_shot'] for c in cases)
    lines=['# Horizontal opponent alignment feasibility','',
           f'{len(cases)} development cases; {available}/{total} shots have a valid alive opposing-player candidate; {pairs} have an exact pre-shot pair.',
           'The opponent nearest the recorded yaw at the shot is held fixed for the pre-shot comparison. It is not necessarily the intended target.',
           'The pre-shot endpoint is approximately 100 ms earlier, rounded to replay ticks. No interpolation is used.',
           '', '| Case | Label | Shots | Available | Paired | Median shot yaw error | Median error reduction |',
           '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    def value(v):
        return 'Unavailable' if v is None else f'{v:.3f}'
    for c in cases:
        lines.append(f"| {c['case_id']} | {c['label']} | {c['shots']} | {c['geometry_available']} | {c['paired_before_shot']} | {value(c['median_nearest_horizontal_error_degrees'])} | {value(c['median_same_candidate_error_reduction_degrees'])} |")
    lines+=['','## Measurement limits','']+['- '+s for s in data['limitations']]
    lines+=['','This is geometry feasibility, not detection evaluation. Existing model predictions remain unchanged. Missing opponents and lethal-tick state changes can bias coverage. Tight horizontal alignment alone cannot distinguish legitimate aiming from cheating.','']
    text='\n'.join(lines)
    (directory/'report.md').write_text(text)
    (directory/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>AimGuard horizontal geometry</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:20px}img{width:100%}pre{white-space:pre-wrap}</style><h1>Horizontal opponent alignment</h1><p>Development feasibility only. Visibility and intended target unknown.</p><img src="alignment.png" alt="Per-case horizontal alignment and pre-shot error reduction"><pre>'+html.escape(text)+'</pre>')
    print(text)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args(argv)
    render(args.directory)


if __name__=='__main__':
    main()

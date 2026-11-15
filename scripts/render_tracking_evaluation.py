"""Render a completed frozen evaluation with coverage and uncertainty intact."""
import argparse
import html
import json
import math
from pathlib import Path

from aimguard.baseline import digest, evaluation_metrics


def render(directory,output=None):
    directory=Path(directory);result=json.loads((directory/'evaluation.json').read_text())
    start=json.loads((directory/'start-receipt.json').read_text())
    if any(start[key]!=result[key] for key in ('model_sha256','reserved_manifest_sha256','threshold')):
        raise ValueError('Evaluation and start receipts disagree')
    rows=result['predictions'];ids=[str(row['case_id']) for row in rows]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate evaluation case IDs')
    for row in rows:
        if row['status'] not in ('scored','abstained') or row['label'] not in ('cheating','legitimate'):
            raise ValueError('Unknown evaluation status or label')
        if row['status']=='scored':
            score=row['baseline_score']
            if not isinstance(score,(int,float)) or not math.isfinite(score) or not 0<=score<=1:
                raise ValueError('Invalid evaluation score')
            if row['flagged']!=(score>=result['threshold']):raise ValueError('Flag differs from frozen cutoff')
    metrics=evaluation_metrics(rows)
    if metrics!=result['metrics']:raise ValueError('Saved evaluation metrics differ from predictions')
    def escape(value):return html.escape(str(value))
    def rate(name):
        value=metrics[name];k,n=value['numerator'],value['denominator']
        if not n:return 'Unavailable (no scored cases in this denominator)'
        low,high=value['exact_95_interval']
        return f'{k}/{n} ({100*value["value"]:.1f}%); exact 95% interval {100*low:.1f}–{100*high:.1f}%'
    confusion=metrics['confusion']
    cards=''.join(f'<div><strong>{confusion[key]}</strong><span>{label}</span></div>' for key,label in
        [('true_positive','Cheating labels flagged'),('false_negative','Cheating labels missed'),
         ('false_positive','Legitimate cases falsely flagged'),('true_negative','Legitimate cases unflagged')])
    body=[]
    for row in rows:
        if row['status']=='scored':
            outcome=('Flagged' if row['flagged'] else 'Unflagged')
            correct=row['flagged']==(row['label']=='cheating')
            outcome+=(' · agrees with source label' if correct else ' · differs from source label')
            score=f'{row["baseline_score"]:.4f}';note=''
        else:outcome='Abstained';score='—';note=row.get('error','No usable analysis')
        body.append('<tr>'+''.join('<td>'+escape(value)+'</td>' for value in
            (row['case_id'],row['label'],score,outcome,note))+'</tr>')
    caveats=''.join('<li>'+escape(text)+'</li>' for text in result.get('caveats',[]))
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AimGuard frozen evaluation</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:20px;color:#17392b;background:#f7f8f5}p,li{line-height:1.5}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}.cards div{background:white;border:1px solid #ced8d0;border-radius:8px;padding:18px}.cards strong{font-size:2rem;display:block}.cards span{display:block}table{border-collapse:collapse;width:100%;background:white}td,th{text-align:left;padding:10px;border-bottom:1px solid #ddd;vertical-align:top}code{overflow-wrap:anywhere}.scroll{overflow-x:auto}</style>
<h1>Frozen-model evaluation</h1><p>All cases are shown, including failed analyses. Scores are uncalibrated and source labels describe cheating per player/match, not confirmed aimbot activation.</p>'''
    page+=f'<p><strong>{metrics["scored"]}/{metrics["cases"]} cases scored; {metrics["abstentions"]} abstained.</strong> Abstentions by label: {escape(metrics["abstentions_by_label"])}.</p><div class="cards">'+cards+'</div>'
    page+='<h2>Rates among successfully analyzed cases</h2><p>Cheating labels flagged: '+rate('detection_rate')+'</p><p>False flags among legitimate cases: '+rate('false_positive_rate')+'</p><p>Intervals assume independent outcomes. Archive-order sampling, source-label precision, and small denominators limit generalization. Zero observed false flags does not establish zero false-positive risk.</p>'
    page+='<h2>Every evaluation case</h2><p>Fixed score cutoff: '+escape(result['threshold'])+'</p><div class="scroll"><table><thead><tr><th>Case</th><th>Source label</th><th>Score</th><th>Outcome</th><th>Analysis note</th></tr></thead><tbody>'+''.join(body)+'</tbody></table></div>'
    page+='<h2>Recorded limitations</h2><ul>'+caveats+'</ul><h2>Provenance</h2><p>Model SHA-256: <code>'+escape(result['model_sha256'])+'</code></p><p>Reservation SHA-256: <code>'+escape(result['reserved_manifest_sha256'])+'</code></p><p>Evaluation SHA-256: <code>'+digest(directory/'evaluation.json')+'</code></p><p>This reservation has been consumed. Further tuning using these outcomes requires new fresh cases for another performance claim.</p></html>'
    output=Path(output) if output else directory/'evaluation.html'
    with output.open('x',encoding='utf-8') as handle:handle.write(page)
    print(output)
    return output


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv);render(args.directory,args.output)


if __name__=='__main__':main()

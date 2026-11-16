"""Render candidate ambiguity receipts without modifying extraction or predictions."""
import argparse
import html
import json
from pathlib import Path

from aimguard.baseline import digest


def render(directory):
    directory=Path(directory); summary=json.loads((directory/'summary.json').read_text())
    if summary['protocol_sha256']!=digest(directory/'protocol.json'): raise ValueError('Protocol receipt mismatch')
    records=[]
    for case in summary['cases']:
        case_id=case['case_id']
        if Path(case_id).name!=case_id or case_id in ('.','..'): raise ValueError('Unsafe case filename')
        path=directory/f'{case_id}.json'
        if digest(path)!=summary['case_sha256'][case_id]: raise ValueError('Case receipt mismatch')
        record=json.loads(path.read_text())
        if record['case_id']!=case_id or record['summary']!=case['summary']: raise ValueError('Case identity mismatch')
        records.append(record)
    def number(value): return 'unavailable' if value is None else f'{value:.3f}'
    def page(title,body):
        return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>body{font:17px system-ui;max-width:1150px;margin:30px auto;padding:20px;color:#17392b}pre{white-space:pre-wrap;font:inherit;line-height:1.5}table{border-collapse:collapse;width:100%}th,td{padding:8px;border-bottom:1px solid #ddd;text-align:left}a{color:#07645d}</style><h1>'+html.escape(title)+'</h1><p>Descriptive selected-case audit. Nearest geometry is not intended target or visibility. No detection decisions changed.</p>'+body+'</html>'
    links=[]
    for record in records:
        rows=[]
        for w in record['windows']:
            endpoint=w['snapshots'][0]; comparison=w['comparisons'][1]
            cells=[str(w['engagement_id']),str(w['first_shot_tick']),html.escape(w['weapon']),
                   number(endpoint.get('nearest_error')),number(endpoint.get('runner_up_gap')),
                   str(comparison['same_nearest']) if comparison['status']=='available' else 'unavailable']
            rows.append('<tr>'+''.join('<td>'+c+'</td>' for c in cells)+'</tr>')
        body='<p><a href="index.html">All cases</a> · <a href="'+html.escape(Path(record['review']).as_uri(),quote=True)+'">Open local trajectories</a></p>'
        body+='<table><tr><th>Window</th><th>First shot tick</th><th>Weapon</th><th>Endpoint error °</th><th>Runner-up gap °</th><th>Same nearest 200 ms earlier</th></tr>'+''.join(rows)+'</table>'
        (directory/f"{record['case_id']}.html").write_text(page(record['case_id']+' · '+record['cohort'],body))
        links.append('<li><a href="'+html.escape(record['case_id'],quote=True)+'.html">'+html.escape(record['case_id']+' · '+record['cohort'])+'</a></li>')
    (directory/'index.html').write_text(page('Candidate ambiguity audit','<ul>'+''.join(links)+'</ul><pre>'+html.escape((directory/'report.md').read_text())+'</pre>'))
    print(directory/'index.html');return directory/'index.html'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    render(parser.parse_args(argv).directory)


if __name__=='__main__':main()

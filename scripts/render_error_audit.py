"""Render saved shared-error diagnostics without changing decisions or fitting."""
import argparse
import html
import json
from pathlib import Path

from aimguard.baseline import digest


def render(directory):
    directory = Path(directory)
    result = json.loads((directory/'audit.json').read_text())
    if result['protocol_sha256'] != digest(directory/'protocol.json') or result['inputs_sha256'] != digest(directory/'inputs.json'):
        raise ValueError('Audit receipt mismatch')
    inputs = json.loads((directory/'inputs.json').read_text())
    sources = {row['case_id']: row for row in inputs['sources']}
    rows = []
    for case in result['explanations']:
        if not case['error']: continue
        source = sources[case['case_id']]
        link = html.escape(Path(source['review']).as_uri(), quote=True)
        cells = [html.escape(case['case_id']), html.escape(case['label']), f"{case['score']:.4f}",
                 f'<a href="{link}">Open local trajectories</a>']
        rows.append('<tr>'+''.join('<td>'+cell+'</td>' for cell in cells)+'</tr>')
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AimGuard error audit</title><style>body{font:17px system-ui;max-width:1100px;margin:30px auto;padding:20px;color:#17392b}pre{white-space:pre-wrap;font:inherit;line-height:1.6}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #ccc}a{color:#07645d}</style>
<h1>Shared error audit</h1><p>Inspected development diagnostics. No detector or policy is promoted. Scores are not calibrated cheating probabilities.</p>
<table><tr><th>Case</th><th>Source label</th><th>Score</th><th>Review</th></tr>'''+''.join(rows)+'</table><pre>'+html.escape((directory/'report.md').read_text())+'</pre></html>'
    (directory/'index.html').write_text(document)
    print(directory/'index.html')
    return directory/'index.html'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('directory', type=Path)
    render(parser.parse_args(argv).directory)


if __name__ == '__main__': main()

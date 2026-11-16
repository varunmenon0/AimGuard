"""Render observed measurement evidence and pending game-review bookmarks."""
import argparse
import csv
import html
import json
from pathlib import Path

from aimguard.baseline import digest


def render(directory):
    directory=Path(directory);summary=json.loads((directory/'summary.json').read_text())
    if summary.get('eye_head_geometry_validated') is not False or summary.get('visibility_validated') is not False:
        raise ValueError('Renderer supports unvalidated proxy audits only')
    if digest(directory/'plan.json')!=summary['plan_sha256']:raise ValueError('Audit plan checksum mismatch')
    records=[]
    for case in summary['cases']:
        path=directory/(case['case_id']+'.json')
        if digest(path)!=summary['case_sha256'][case['case_id']]:raise ValueError('Audit case checksum mismatch')
        record=json.loads(path.read_text())
        if record['summary']!=case:raise ValueError('Audit case summary mismatch')
        records.append(record)
    def esc(value):return html.escape(str(value))
    missing=[(record['summary']['case_id'],window['engagement_id']) for record in records for window in record['windows'] for sample in window['samples'] if sample['kind']=='pre_first_shot' and sample.get('reason')=='missing_exact_shooter_sample']
    view_states=[[value['status'] for prop,value in record['property_availability'].items() if 'ViewOffset' in prop] for record in records]
    omitted=sum(bool(states) and all(status=='requested_column_omitted' for status in states) for states in view_states)
    lines=['# Combat measurement audit','',
        'Small selected post-evaluation sample. Telemetry/event audit only; rendered gameplay annotation remains pending.',
        'Body-origin geometry is a proxy. Measured eye-to-head/hitbox error and validated visibility remain unavailable. No classifier or threshold changed.',
        '', '| Case | Label | Frozen score | Windows | Comparable pre-shot ranks | Origin-proxy rank changes | Horizontal/event agreement | Proxy/event agreement |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for case in summary['cases']:
        n=case.get('damage_at_or_after_first_shot',0)
        lines.append(f"| {case['case_id']} | {case['label']} | {case['frozen_score']:.8f} | {case['windows']} | {case.get('comparable_initial_ranks',0)} | {case.get('initial_rank_differs_under_origin_proxy',0)} | {case.get('initial_horizontal_in_damage_recipient_set',0)}/{n} | {case.get('initial_origin_proxy_in_damage_recipient_set',0)}/{n} |")
    lines+=['','Agreement means the candidate is one of the window damage recipients. It is not intended-target accuracy or a per-shot association.',
        f"{len(missing)} exact pre-shot samples are absent from saved telemetry/sparse extraction in cases {sorted({case for case,_ in missing})}. Missing samples remain unavailable, without interpolation.",
        f'Requested view-offset columns were omitted in {omitted}/{len(records)} audited demos. Returned head-constraint vectors and hitbox-set indices are not validated world eye/head coordinates.',
        'Recoil and crouch fields are recorded without guessed correction. Spotted/mask fields are not treated as line-of-sight ground truth.',
        '', '## Limits','',*['- '+value for value in summary['limitations']],
        '', 'Open review-bookmarks.csv on the machine used to play the demos. Its rendered-review fields are deliberately pending; confirm target, visibility, hitbox geometry and recoil against actual gameplay before promoting measurements.','']
    (directory/'report.md').write_text('\n'.join(lines))
    bookmarks=[];details=[]
    for record in records:
        case=record['summary'];windows=[]
        for window in record['windows']:
            pre=next(s for s in window['samples'] if s['kind']=='pre_first_shot')
            # Observed event timestamps are bookmarks, never a guessed target verdict.
            shot_ticks=window['shot_ticks'];damage_ticks=sorted({e['tick'] for e in window['damage_at_or_after_first_shot']})
            sample_ticks=[s['tick'] for s in window['samples']]
            bookmarks.append(dict(case_id=case['case_id'],source_label=case['label'],demo_path=record['demo_path'],
                window_number=window['engagement_id']+1,weapon=window['weapon'],first_shot_tick=shot_ticks[0],
                shot_ticks=' '.join(map(str,shot_ticks)),damage_ticks=' '.join(map(str,damage_ticks)),
                first_audit_tick=min(sample_ticks),last_audit_tick=max(sample_ticks),
                rendered_review_status='pending',intended_target_review='pending',visibility_review='pending',
                eye_head_geometry_review='pending',reviewer_notes=''))
            proxies=[]
            for i,candidate in enumerate(pre['candidates'],1):
                label=[]
                if candidate['opponent_id']==window['frozen_horizontal_candidate']:label.append('frozen horizontal candidate')
                if candidate['opponent_id']==pre.get('nearest_origin_proxy_candidate'):label.append('nearest body-origin proxy')
                if candidate['opponent_id'] in {e['opponent_id'] for e in window['damage_at_or_after_first_shot']}:label.append('window damage recipient')
                proxies.append('<tr>'+''.join('<td>'+esc(value)+'</td>' for value in
                    (f'Opponent {i}',', '.join(label),candidate['horizontal_error_degrees'],
                     round(candidate['origin_proxy_angular_error_degrees'],4),round(candidate['height_delta_units'],3),
                     round(candidate['origin_distance_units'],3)))+'</tr>')
            windows.append('<details><summary>Window '+str(window['engagement_id']+1)+' · '+esc(window['weapon'])+' · '+esc(window['category'])+'</summary><p>First shot: '+str(shot_ticks[0])+'; damage ticks: '+esc(damage_ticks)+'; pre-shot sample: '+esc(pre.get('reason',pre['status']))+'</p><p>Opponent labels are local to this window. Positions are origins, not hitboxes; visibility is unverified.</p><div class="scroll"><table><tr><th>Opponent</th><th>Observed associations</th><th>Horizontal error (degrees)</th><th>Origin proxy angle (degrees)</th><th>Height delta (units)</th><th>Origin distance (units)</th></tr>'+''.join(proxies)+'</table></div><p>Damage event details: <code>'+esc(json.dumps(window['damage_event_details'],ensure_ascii=False))+'</code></p></details>')
        availability=[]
        for prop,value in record['property_availability'].items():
            text=value['status']
            if text=='returned':text+=f" · {value['nonnull']}/{value['rows']} non-null"
            if 'nonzero_numeric_values' in value:text+=f" · {value['nonzero_numeric_values']} nonzero numeric components"
            availability.append('<tr><td>'+esc(prop)+'</td><td>'+esc(text)+'</td></tr>')
        details.append('<section><h2>'+esc(case['case_id'])+' · '+esc(case['label'])+'</h2><p>Frozen score '+f"{case['frozen_score']:.8f}"+'; rendered gameplay review: <strong>pending</strong>.</p><details><summary>Observed field availability</summary><div class="scroll"><table>'+''.join(availability)+'</table></div></details>'+''.join(windows)+'</section>')
    with (directory/'review-bookmarks.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(bookmarks[0]) if bookmarks else ['case_id','rendered_review_status']);writer.writeheader();writer.writerows(bookmarks)
    (directory/'review-template.json').write_text(json.dumps(dict(status='pending_rendered_gameplay',plan_sha256=summary['plan_sha256'],bookmarks=bookmarks),indent=2)+'\n')
    (directory/'index.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AimGuard measurement audit</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:20px;color:#17392b}pre{white-space:pre-wrap}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}section{margin:24px 0}details{margin:12px 0;padding:10px;background:#f5f7f3}summary{cursor:pointer}.scroll{overflow-x:auto}code{overflow-wrap:anywhere}</style><h1>Combat measurement audit</h1><p><strong>Telemetry checked; rendered gameplay review is pending.</strong> This report does not validate eye/head positions or visibility and does not change model predictions.</p><p><a href="review-bookmarks.csv">Tick bookmarks</a> · <a href="review-template.json">Pending review template</a></p><pre>'+esc('\n'.join(lines))+'</pre>'+''.join(details))
    print(directory/'index.html')
    return bookmarks


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path);args=parser.parse_args(argv);render(args.directory)


if __name__=='__main__':main()

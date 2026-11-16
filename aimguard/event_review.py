"""Local event bookmarks and provenance-checked human observations, never auto-labels."""
import argparse
import csv
import html
import json
from pathlib import Path

from aimguard.baseline import digest, write_json

EDITABLE = {'review_status','review_source','observed_behavior','assistance_assessment','evidence_reference','evidence_note','reviewer'}
SOURCES = {'unreviewed','telemetry_only','rendered_gameplay'}
BEHAVIORS = {'unreviewed','ordinary_preaim','aim_correction','tracking','unclear'}
ASSESSMENTS = {'unreviewed','not_assessable','no_clear_evidence','suspicious'}


def load_queue(directory):
    directory=Path(directory);comparison=json.loads((directory/'comparison.json').read_text())
    if comparison['review_queue_sha256']!=digest(directory/'review-queue.json'):raise ValueError('Review queue receipt mismatch')
    queue=json.loads((directory/'review-queue.json').read_text())
    if queue['role']!='pending_behavior_review' or queue['template_sha256']!=digest(directory/'event-review-template.csv'):
        raise ValueError('Original review template receipt mismatch')
    ids=[e['review_id'] for e in queue['events']]
    if len(set(ids))!=len(ids) or not ids:raise ValueError('Unique nonempty event identities required')
    return queue


def validate(directory,annotations,output):
    directory,annotations,output=map(Path,(directory,annotations,output));queue=load_queue(directory)
    expected={e['review_id']:e for e in queue['events']}
    with annotations.open(newline='') as handle:
        reader=csv.DictReader(handle);fields=reader.fieldnames;rows=list(reader)
    wanted=set(queue['events'][0])
    if fields is None or len(fields)!=len(set(fields)) or set(fields)!=wanted:raise ValueError('Annotation columns mismatch')
    if len(rows)!=len(expected) or {r['review_id'] for r in rows}!=set(expected):raise ValueError('Annotation event coverage/identity mismatch')
    if len({r['review_id'] for r in rows})!=len(rows):raise ValueError('Duplicate annotation event')
    reviewed=[];pending=0
    for row in rows:
        if set(row)!=wanted or any(not isinstance(value,str) for value in row.values()):raise ValueError('Malformed annotation row')
        original=expected[row['review_id']]
        if any(row[key]!=str(original[key]) for key in wanted-EDITABLE):raise ValueError('Immutable event metadata changed')
        if (row['review_status'] not in {'pending','reviewed'} or row['review_source'] not in SOURCES
            or row['observed_behavior'] not in BEHAVIORS or row['assistance_assessment'] not in ASSESSMENTS):
            raise ValueError('Unknown review state or observation')
        if row['review_status']=='pending':
            if any(row[k]!='unreviewed' for k in ('review_source','observed_behavior','assistance_assessment')):
                raise ValueError('Pending events cannot carry completed observations')
            pending+=1;continue
        if (row['review_source']=='unreviewed' or row['observed_behavior']=='unreviewed' or row['assistance_assessment']=='unreviewed'
            or any(not row[k].strip() for k in ('reviewer','evidence_reference','evidence_note'))):
            raise ValueError('Reviewed observations require source, behavior, assessment, reviewer and evidence')
        reviewed.append(row)
    result=dict(role='human_behavior_observations',reviewed=len(reviewed),pending=pending,observations=reviewed,
        queue_sha256=digest(directory/'review-queue.json'),annotations_sha256=digest(annotations),
        training_labels_created=False,cheat_activation_ground_truth=None,
        note='Review source and evidence are reviewer attestations, not independently verified ground truth. Suspicious observations are not confirmed cheat activation labels.')
    write_json(output,result);print(f"{len(reviewed)} reviewed observations; {pending} pending; no training labels created",flush=True);return result


def render(directory,pool):
    from scripts.render_target_tracking import PAGE
    directory,pool=map(Path,(directory,pool));queue=load_queue(directory)
    if queue['manifest_sha256']!=digest(pool/'manifest.json'):raise ValueError('Review manifest mismatch')
    result=json.loads((directory/'comparison.json').read_text())
    if result['inputs_sha256']!=digest(directory/'inputs.json'):raise ValueError('Review inputs receipt mismatch')
    inputs=json.loads((directory/'inputs.json').read_text());cases=json.loads((pool/'manifest.json').read_text())['cases']
    by_case={c['case_id']:(i,c) for i,c in enumerate(cases,1)};receipts={c['case_id']:c for c in inputs['cases']}
    events={}
    for event in queue['events']:events.setdefault(event['case_id'],[]).append(event)
    from aimguard.candidate_audit import SAMPLE
    first_pass=[]
    priority=set(SAMPLE)
    folder=directory/'event-pages';folder.mkdir(exist_ok=True);links=[]
    for case_id,rows in events.items():
        index,case=by_case[case_id]
        if Path(case_id).name!=case_id or case_id in ('.','..'):raise ValueError('Unsafe case ID')
        path=pool/'tracking'/f'case_{index:04d}.json'
        if digest(path)!=receipts[case_id]['tracking_sha256']:raise ValueError('Review tracking receipt mismatch')
        tracking=json.loads(path.read_text());tracking['summary'].pop('label',None)
        payload=json.dumps(tracking,allow_nan=False).replace('<',r'\u003c')
        (folder/f'{case_id}-tracks.html').write_text(PAGE.replace('__DATA__',payload))
        positions={w['engagement_id']:(i,w) for i,w in enumerate(tracking['windows'])};table=[];priority_rounds=set()
        for row in rows:
            position,window=positions[row['engagement_id']];candidate=window['nearest_before_first_shot']
            opponent=next((i for i,t in enumerate(window['tracks']) if t['opponent_id']==candidate),0)
            href=html.escape(f'{case_id}-tracks.html#w={position}&t={opponent}',quote=True)
            if case_id in priority and len(priority_rounds)<3 and row['round_id'] not in priority_rounds:
                priority_rounds.add(row['round_id'])
                first_pass.append('<li><a href="event-pages/'+href+'">'+html.escape(row['review_id'])+'</a> · round '+str(row['round_id'])+' · tick '+str(row['first_shot_tick'])+'</li>')
            table.append('<tr><td>'+html.escape(row['review_id'])+'</td><td>'+str(row['round_id'])+'</td><td>'+str(row['first_shot_tick'])+'</td><td><a href="'+href+'">Open trajectory</a></td><td>Pending</td></tr>')
        body='<p><a href="../event-review.html">All cases</a></p><table><tr><th>Event</th><th>Round</th><th>First shot tick</th><th>Telemetry</th><th>Status</th></tr>'+''.join(table)+'</table>'
        (folder/f'{case_id}.html').write_text(page(case_id+' event review',body))
        links.append('<li><a href="event-pages/'+html.escape(case_id,quote=True)+'.html">'+html.escape(case_id)+f'</a> · {len(rows)} pending events</li>')
    body='<p>Source match labels and model scores are omitted. Trajectory charts are not rendered CS2 gameplay. All events are pending; no aim-assist activation labels have been established.</p><p><a href="event-review-template.csv" download>Download editable review CSV</a></p><p>Record observed behavior, review source, evidence reference, notes and reviewer. Preserve event identities. Use unclear/not_assessable when the evidence is insufficient. A suspicious observation is not confirmation of cheating.</p><h2>First pass: '+str(len(first_pass))+' events</h2><p>First chronological encounter in each of three distinct rounds for the fixed error/control sample. This selected review sample is not an accuracy estimate.</p><ul>'+''.join(first_pass)+'</ul><h2>All cases</h2><ul>'+''.join(links)+'</ul>'
    output=directory/'event-review.html';output.write_text(page('Event-level behavior review',body));print(output);return output


def page(title,body):
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>body{font:17px system-ui;max-width:1100px;margin:30px auto;padding:20px;color:#17392b}p{line-height:1.5}table{border-collapse:collapse;width:100%}th,td{padding:10px;border-bottom:1px solid #ccc;text-align:left}li{margin:8px}a{color:#07645d}</style><h1>'+html.escape(title)+'</h1>'+body+'</html>'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    renderer=sub.add_parser('render');renderer.add_argument('directory',type=Path);renderer.add_argument('pool',type=Path)
    validator=sub.add_parser('validate');validator.add_argument('directory',type=Path);validator.add_argument('annotations',type=Path);validator.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    if args.command=='render':render(args.directory,args.pool)
    else:validate(args.directory,args.annotations,args.output)


if __name__=='__main__':main()

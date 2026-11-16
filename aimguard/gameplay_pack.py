"""Prepare a bounded rendered-gameplay comparison; do not simulate completed review."""
import argparse
import csv
import html
import json
from pathlib import Path
import random
import shutil
import math

import pandas as pd

from aimguard.baseline import digest,write_json
from aimguard.context_models import family
from aimguard.event_review import load_queue,validate as validate_observations,BEHAVIORS,ASSESSMENTS
from aimguard.tracking_models import window_features

PAIRS=[('D-1A',0,'L-013'),('D-1B',0,'D-3A'),('D-1B',1,'R-009'),('D-1B',2,'L-002'),('D-2B',0,'R-002')]
EDITABLE={'playback_status','pov_confirmed','xray_disabled','game_build','visibility','observed_behavior',
          'assistance_assessment','evidence_reference','evidence_note','reviewer'}


def clip_bounds(tick,rate,last_tick):
    if type(tick) is not int or tick<96 or not math.isfinite(rate) or rate<=0 or last_tick<tick:raise ValueError('Invalid playback tick bounds')
    return max(96,tick-round(8*rate)),min(last_tick,tick+round(4*rate))


def choose_control(report,tracking,events,steamid,weapon):
    if len(report['engagements'])!=len(tracking['windows']):raise ValueError('Control window count mismatch')
    choices=[]
    for index,(window,track) in enumerate(zip(report['engagements'],tracking['windows'])):
        if any(window[k]!=track[k] for k in ('engagement_id','weapon','shot_ticks','round_id')):raise ValueError('Control window identity mismatch')
        if window_features(track,report['assumed_tickrate_hz'])[0] is None:continue
        kills=[e['tick'] for e in events if e['event_type']=='player_death' and e.get('attacker_steamid')==steamid
            and e.get('segment_id')==window['segment_id'] and window['shot_ticks'][0]<=e['tick']<=window['end_tick']
            and str(e.get('weapon','')).removeprefix('weapon_')==window['weapon']]
        if kills:
            match=0 if window['weapon']==weapon else (1 if family(window['weapon'])==family(weapon) else 2)
            choices.append((match,min(kills),index))
    if not choices:raise ValueError('No eligible matching control elimination')
    match,tick,index=min(choices)
    return dict(window_index=index,kill_tick=int(tick),weapon_match=('exact','family','unmatched')[match])


def build(pool,anchors_directory,queue_directory,output,include_demos=False):
    pool,anchors_directory,queue_directory,output=map(Path,(pool,anchors_directory,queue_directory,output))
    manifest=json.loads((pool/'manifest.json').read_text());receipt=json.loads((pool/'pool-receipt.json').read_text())
    anchors=json.loads((anchors_directory/'anchors.json').read_text());anchor_protocol=json.loads((anchors_directory/'protocol.json').read_text())
    queue=load_queue(queue_directory);comparison=json.loads((queue_directory/'comparison.json').read_text())
    if (manifest.get('role')!='development' or receipt['manifest_sha256']!=digest(pool/'manifest.json')
        or anchors['protocol_sha256']!=digest(anchors_directory/'protocol.json') or anchor_protocol['manifest_sha256']!=digest(pool/'manifest.json')
        or queue['manifest_sha256']!=digest(pool/'manifest.json')):raise ValueError('Review source receipts mismatch')
    cases={c['case_id']:(i,c) for i,c in enumerate(manifest['cases'],1)}
    predictions={r['case_id']:r for r in comparison['models']['original_speed_and_tracking']['predictions']}
    queued={r['review_id']:r for r in queue['events']};cache={}
    def source(case_id):
        if case_id in cache:return cache[case_id]
        index,case=cases[case_id];directory=pool/'analysis'/f'job_{index:04d}';path=pool/'tracking'/f'case_{index:04d}.json'
        report=json.loads((directory/'report.json').read_text());tracking=json.loads(path.read_text());expected=receipt['cases'][index-1]
        if (expected['case_id']!=case_id or digest(directory/'report.json')!=expected['report_sha256'] or digest(path)!=expected['tracking_sha256']
            or report['steamid']!=case['steamid'] or report['source_sha256']!=case['demo_sha256'] or digest(case['demo'])!=case['demo_sha256']):raise ValueError('Review source identity/hash mismatch')
        for name in ('report.json','telemetry.csv','events.json'):
            if digest(directory/name)!=tracking['input_sha256'][name]:raise ValueError('Review canonical input checksum mismatch')
        events=json.loads((directory/'events.json').read_text());names=pd.read_csv(directory/'telemetry.csv',usecols=['tick','name'])
        cache[case_id]=(case,report,tracking,events,names);return cache[case_id]
    selected=[]
    for case_id,ordinal,control_id in PAIRS:
        case,report,tracking,events,names=source(case_id)
        refs=[a for a in anchors['anchors'] if a['case_id']==case_id]
        anchor=refs[ordinal]
        if len(anchor['overlapping_analysis_windows'])!=1:raise ValueError('Source bookmark needs a unique canonical window')
        wi=anchor['overlapping_analysis_windows'][0]['window_index'];window=report['engagements'][wi]
        selected.append(dict(case_id=case_id,window_index=wi,kill_tick=anchor['replay_kill_tick'],role='author_reference',pair=len(selected)//2+1,weapon_match='reference'))
        control_case,control_report,control_tracking,control_events,_=source(control_id)
        prediction=predictions[control_id]
        if control_case['label']!='legitimate' or prediction['label']!='legitimate' or prediction['status']!='scored' or not prediction['flagged']:
            raise ValueError('Fixed comparison case is no longer a legitimate false flag')
        control=choose_control(control_report,control_tracking,control_events,control_case['steamid'],window['weapon'])
        selected.append(dict(case_id=control_id,role='legitimate_false_flag_comparison',pair=len(selected)//2+1,**control))
    if len({(r['case_id'],r['window_index']) for r in selected})!=10:raise ValueError('Review encounters must be unique')
    random.Random(730).shuffle(selected)
    output.mkdir(parents=True,exist_ok=False);(output/'commands').mkdir()
    if include_demos:(output/'demos').mkdir()
    rows=[];private=[];demos={}
    for number,item in enumerate(selected,1):
        case,report,tracking,events,names=source(item['case_id']);window=report['engagements'][item['window_index']]
        review_id=f"{item['case_id']}:{window['engagement_id']}"
        if review_id not in queued or queued[review_id]['demo_sha256']!=case['demo_sha256']:raise ValueError('Event queue identity mismatch')
        tick=item['kill_tick']
        if not any(e['event_type']=='player_death' and e.get('attacker_steamid')==case['steamid'] and e['tick']==tick for e in events):raise ValueError('Bookmark kill event not found')
        begin,end=clip_bounds(tick,report['assumed_tickrate_hz'],int(names.tick.max()))
        player=names.loc[names.tick.eq(tick),'name']
        if len(player)!=1 or pd.isna(player.iloc[0]):raise ValueError('Exact-event player name unavailable')
        if case['demo_sha256'] not in demos:
            filename=f'D{len(demos)+1:02d}.dem';demos[case['demo_sha256']]=dict(filename=filename,source=case['demo'],sha256=case['demo_sha256'],bytes=Path(case['demo']).stat().st_size)
            if include_demos:
                shutil.copyfile(case['demo'],output/'demos'/filename)
                if digest(output/'demos'/filename)!=case['demo_sha256']:raise ValueError('Copied review demo checksum mismatch')
        demo=demos[case['demo_sha256']]['filename'];alias=f'R{number:02d}'
        row=dict(review_alias=alias,demo_file=demo,steamid=case['steamid'],player_name=str(player.iloc[0]),
            start_tick=begin,event_tick=tick,end_tick=end,weapon=window['weapon'],playback_status='pending',
            pov_confirmed='',xray_disabled='',game_build='',visibility='unreviewed',observed_behavior='unreviewed',
            assistance_assessment='unreviewed',evidence_reference='',evidence_note='',reviewer='')
        rows.append(row);private.append(dict(review_alias=alias,event_review_id=review_id,**item))
        (output/'commands'/f'{alias}.txt').write_text(f'After copying demos to game/csgo/replays/aimguard/, load this demo:\nplaydemo "replays/aimguard/{demo}"\n\nWait for the demo to load. Then seek:\ndemo_gototick {begin}\ndemoui\n\nSelect the named player in first-person using demo controls. Turn X-Ray off and confirm both settings. Watch through tick {end}; event tick {tick}. These instructions have not been runtime-tested here.\n')
    with (output/'review-template.csv').open('x',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write_json(output/'selection-private.json',dict(selection=private,note='Selected development diagnostic controls; not a performance cohort. Source labels/roles omitted from reviewer presentation, not cryptographically blinded.'))
    write_json(output/'pack.json',dict(role='pending_rendered_gameplay_review_pack',events=rows,demos=list(demos.values()),demos_included=include_demos,
        manifest_sha256=digest(pool/'manifest.json'),anchors_sha256=digest(anchors_directory/'anchors.json'),
        source_queue_sha256=digest(queue_directory/'review-queue.json'),template_sha256=digest(output/'review-template.csv'),
        private_selection_sha256=digest(output/'selection-private.json'),code_sha256=digest(__file__),rendered_reviews_completed=0,
        note='No gameplay has been rendered by this builder. Build/version, POV, X-Ray and evidence remain pending reviewer attestations.'))
    cells=[]
    for r in rows:
        fields=[r['review_alias'],r['player_name'],r['steamid'],r['weapon'],str(r['start_tick']),str(r['event_tick']),str(r['end_tick'])]
        cells.append('<tr>'+''.join('<td>'+html.escape(v)+'</td>' for v in fields)+f'<td><a href="commands/{r["review_alias"]}.txt">Playback steps</a></td><td>Pending</td></tr>')
    (output/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ten-event gameplay review</title><style>body{font:17px system-ui;max-width:1200px;margin:30px auto;padding:20px}p{line-height:1.5}table{border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left}</style><h1>Ten-event gameplay review</h1><p>Actual CS2 playback is required. These are bookmarks and commands, not rendered video. Source labels, model scores and selection roles are omitted here. All reviews remain pending.</p><p>Watch each interval at normal speed first, in the named player’s first-person view with X-Ray off. Then replay slowly if useful. Record visibility and what the player does, including ordinary explanations such as recoil, sound, teammate information and common angles. One unusual correction is not confirmation of cheating.</p><p><a href="review-template.csv" download>Download review CSV</a> · <a href="SETUP.md">Setup and recording observations</a></p><table><tr><th>Review</th><th>Player</th><th>SteamID64</th><th>Weapon</th><th>Start tick</th><th>Event tick</th><th>End tick</th><th>Playback</th><th>Status</th></tr>'+''.join(cells)+'</table></html>')
    total=sum(d['bytes'] for d in demos.values())
    (output/'SETUP.md').write_text(f'''# Ten-event rendered gameplay review

Ten planned intervals of about 12 seconds each, across eight unique demos. No gameplay review is completed by this package. Demo bytes needed: {total:,}. Demos included: {include_demos}.

Use a computer with CS2 installed. Copy the eight files listed in pack.json to the CS2 game/csgo/replays/aimguard folder under their D01.dem-style aliases. If demos are included, their local copies are in demos/. Otherwise pack.json records the original local source paths and SHA-256 checksums. Copying this metadata-only folder alone does not transfer demos.

Enable the developer console via CS2 settings. Open each commands/Rxx.txt file. Load the demo first; wait for loading to finish before issuing the seek command. Use demo controls to select the player, confirm first-person POV and disable X-Ray. Check that the indicated kill occurs at event_tick. Watch start_tick through end_tick at normal speed, then repeat if needed. Playback commands are prepared instructions, not runtime-tested on this computer.

Edit a copy of review-template.csv. Keep all ten rows and identity/tick fields unchanged. For playback_status use pending, reviewed, or unavailable. A reviewed row requires pov_confirmed=yes, xray_disabled=yes, a recorded game_build, reviewer, evidence_reference and evidence_note. visibility accepts visible, occluded, mixed, or unclear. observed_behavior accepts ordinary_preaim, aim_correction, tracking, or unclear. assistance_assessment accepts not_assessable, no_clear_evidence, or suspicious. Suspicious is an observation, not confirmed activation. If playback fails or the view cannot be verified, use unavailable with a reviewer and explanation; it remains unreviewed rather than a negative label.

The review aliases are shuffled deterministically. No labels or model scores appear in this sheet or index. selection-private.json preserves selection/provenance for the investigator; this is not a statistically representative or fully blinded study. Compare observations before reading that key.

Reference for console setup: https://help.steampowered.com/en/faqs/view/4700-D10E-26BE-DDDD
Reference implementation for seeking: https://github.com/akiver/cs-demo-manager/blob/main/src/node/counter-strike/json-actions-file/json-actions-file-generator.ts
''')
    print(f'{len(rows)} pending intervals, {len(demos)} demos, {total:,} bytes to transfer; 0 rendered reviews completed',flush=True)
    return rows


def import_reviews(pack_directory,queue_directory,annotations,output):
    pack_directory,queue_directory,annotations,output=map(Path,(pack_directory,queue_directory,annotations,output))
    pack=json.loads((pack_directory/'pack.json').read_text());queue=load_queue(queue_directory)
    if (pack['template_sha256']!=digest(pack_directory/'review-template.csv')
        or pack['private_selection_sha256']!=digest(pack_directory/'selection-private.json')
        or pack['source_queue_sha256']!=digest(queue_directory/'review-queue.json')):raise ValueError('Review pack source receipt mismatch')
    expected={r['review_alias']:r for r in pack['events']}
    key={r['review_alias']:r['event_review_id'] for r in json.loads((pack_directory/'selection-private.json').read_text())['selection']}
    with annotations.open(newline='') as handle:reader=csv.DictReader(handle);fields=reader.fieldnames;rows=list(reader)
    if fields is None or len(fields)!=len(set(fields)) or set(fields)!=set(pack['events'][0]) or len(rows)!=len(expected):raise ValueError('Review rows/columns mismatch')
    if len({r['review_alias'] for r in rows})!=len(expected) or set(r['review_alias'] for r in rows)!=set(expected):raise ValueError('Review alias coverage mismatch')
    events={r['review_id']:dict(r) for r in queue['events']};unavailable=0
    for row in rows:
        if set(row)!=set(fields) or any(not isinstance(v,str) for v in row.values()):raise ValueError('Malformed review row')
        original=expected[row['review_alias']]
        if any(row[k]!=str(original[k]) for k in set(fields)-EDITABLE):raise ValueError('Immutable playback identity changed')
        if row['playback_status'] not in ('pending','reviewed','unavailable'):raise ValueError('Unknown playback status')
        if row['playback_status']!='reviewed':
            if any(row[k]!='unreviewed' for k in ('visibility','observed_behavior','assistance_assessment')):raise ValueError('Unreviewed clips cannot carry completed observations')
            if row['playback_status']=='unavailable':
                if not row['reviewer'].strip() or not row['evidence_note'].strip():raise ValueError('Unavailable playback needs reviewer and reason')
                unavailable+=1
            continue
        if (row['pov_confirmed']!='yes' or row['xray_disabled']!='yes' or not row['game_build'].strip()
            or row['visibility'] not in ('visible','occluded','mixed','unclear') or row['observed_behavior'] not in BEHAVIORS-{'unreviewed'}
            or row['assistance_assessment'] not in ASSESSMENTS-{'unreviewed'}):raise ValueError('Rendered observations require verified POV/X-Ray, build and accepted categories')
        event=events[key[row['review_alias']]]
        event.update(review_status='reviewed',review_source='rendered_gameplay',observed_behavior=row['observed_behavior'],
            assistance_assessment=row['assistance_assessment'],reviewer=row['reviewer'],evidence_reference=row['evidence_reference'],
            evidence_note=f"Reported build: {row['game_build']}; first-person confirmed; X-Ray disabled; visibility: {row['visibility']}. {row['evidence_note']}")
        if any(not row[k].strip() for k in ('evidence_note','evidence_reference','reviewer')):raise ValueError('Reviewed event requires reviewer, evidence reference and observation notes')
    output.mkdir(parents=True,exist_ok=False)
    merged=output/'merged-event-observations.csv'
    with merged.open('x',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(queue['events'][0]));writer.writeheader();writer.writerows(events.values())
    result=validate_observations(queue_directory,merged,output/'observations.json')
    write_json(output/'import-receipt.json',dict(pack_sha256=digest(pack_directory/'pack.json'),annotations_sha256=digest(annotations),unavailable_playback=unavailable,
        reviewed=result['reviewed'],pending=result['pending'],training_labels_created=False))
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    builder=sub.add_parser('build')
    for name in ('pool','anchors_directory','queue_directory'):builder.add_argument(name,type=Path)
    builder.add_argument('--output',type=Path,required=True);builder.add_argument('--include-demos',action='store_true')
    importer=sub.add_parser('import')
    for name in ('pack_directory','queue_directory','annotations'):importer.add_argument(name,type=Path)
    importer.add_argument('--output',type=Path,required=True);args=parser.parse_args(argv)
    if args.command=='build':build(args.pool,args.anchors_directory,args.queue_directory,args.output,args.include_demos)
    else:import_reviews(args.pack_directory,args.queue_directory,args.annotations,args.output)


if __name__=='__main__':main()

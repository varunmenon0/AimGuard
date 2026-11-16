"""Link published case illustrations to replay events without inventing activation labels."""
import argparse
import html
import io
import struct
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import zlib

import numpy as np
import pandas as pd

from aimguard.baseline import digest, write_json
from aimguard.tracking_baseline import load_model

PAPER_URL='https://arxiv.org/html/2601.18068v1'
SITE_URL='https://xguardian-anti-cheat.github.io/'
CASE_MAP={'1A':('Case C','author_described_aimbot'),
          '1B':('Case E','author_described_aimbot_and_wallhack'),
          '2B':('Case D','author_described_wallhack_only')}


class Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,data):self.parts.append(data)


def source_text(document):
    parser=Text();parser.feed(document);return ' '.join(' '.join(parser.parts).split())


def parse_frame_ranges(document):
    match=re.search(r'const\s+frameRanges\s*=\s*(\{.*?\})\s*;',document,re.S)
    if not match:raise ValueError('Missing published frame-range object')
    value=json.loads(re.sub(r',\s*([}\]])',r'\1',match[1]))
    for case,events in value.items():
        if not isinstance(events,dict):raise ValueError('Invalid published event ranges')
        for bounds in events.values():
            if (not isinstance(bounds,list) or len(bounds)!=2 or any(type(v) is not int for v in bounds)
                or bounds[0]<0 or bounds[1]<bounds[0]):raise ValueError('Invalid published frame bounds')
    return value


def unique_rounded_identity(token,participants):
    number=float(token)
    if not np.isfinite(number) or number<=0:raise ValueError('Invalid source identity token')
    matches=[str(p) for p in participants if float(p)==number]
    if len(matches)!=1:raise ValueError('Rounded source identity is not uniquely linked within replay')
    return matches[0]


def map_frame_window(frame,bounds,steamid,participants,kill_ticks):
    """Frame indices remain separate from tick values; row-order assumption stays explicit."""
    lo,hi=bounds
    if lo<0 or hi<lo or hi>=len(frame):raise ValueError('Published frame range outside selected source rows')
    part=frame.iloc[lo:hi+1]
    if any(unique_rounded_identity(token,participants)!=steamid for token in part.steamid.unique()):
        raise ValueError('Selected source identity mismatch')
    ticks=pd.to_numeric(part.tick).to_numpy(dtype=float)
    if (not np.isfinite(ticks).all() or (ticks%1!=0).any() or (np.diff(ticks)!=1).any()
        or part.kill_num.nunique()!=1 or part.match_id.nunique()!=1):raise ValueError('Source window must be contiguous and belong to one match/elimination')
    flags=part.isKilling.astype(str).str.lower()
    if not flags.isin(['true','false']).all():raise ValueError('Invalid source elimination flag')
    kills=part.loc[flags.eq('true'),'tick'].tolist()
    if len(kills)!=1 or int(kills[0]) not in kill_ticks:raise ValueError('Source elimination does not match replay death event')
    return dict(published_frame_start=lo,published_frame_end=hi,source_elimination_number=int(part.kill_num.iloc[0]),
                replay_start_tick=int(ticks[0]),replay_end_tick=int(ticks[-1]),replay_kill_tick=int(kills[0]),
                mapping_status='original_split_row_link_with_matching_replay_death_not_activation_ground_truth',
                activation_ground_truth=None,rendered_gameplay_review='pending')


def cached_member(cache,entry):
    with Path(cache).open('rb') as handle:
        handle.seek(entry['offset']);header=handle.read(30)
        if len(header)!=30:raise ValueError('Cached member header missing')
        signature,version,flags,method,mtime,mdate,crc,compressed,size,namesize,extra=struct.unpack('<4s5H3L2H',header)
        if signature!=b'PK\x03\x04' or handle.read(namesize).decode()!=entry['name']:raise ValueError('Cached archive member identity mismatch')
        handle.read(extra);body=handle.read(entry['compressed'])
    if len(body)!=entry['compressed']:raise ValueError('Incomplete cached archive member')
    if method==8:body=zlib.decompress(body,-15)
    elif method!=0:raise ValueError('Unsupported cached member compression')
    if len(body)!=entry['size'] or zlib.crc32(body)!=entry['crc']:raise ValueError('Cached member CRC/size mismatch')
    return body


def image_elimination_identity(index,paper_case,display,bounds,study):
    case_name=paper_case.replace(' ','');folder='tra_'+display if case_name=='CaseE' else 'tra'
    probe=bounds[0]+min(56,bounds[1]-bounds[0])
    suffix=f'5.7_Case_Study/elimination_scope/{case_name}/{folder}/velocity_x_shap_value_{probe}.png'
    targets=[e for e in index if e['name'].endswith(suffix)]
    if len(targets)!=1:raise ValueError('Published image member missing/duplicated')
    target=targets[0];identities=set()
    for entry in index:
        if entry['name']==target['name'] or entry['size']!=target['size'] or entry['crc']!=target['crc']:continue
        match=re.search(r'/([^/]+)_(\d+)_(g[^/]+)/velocity_x_shap_value_\d+\.png$',entry['name'])
        if match and match[3]==study['match_id'] and float(match[1])==float(study['steamid']):identities.add(int(match[2]))
    if len(identities)>1:raise ValueError('Conflicting duplicate-image elimination identities')
    return next(iter(identities)) if identities else None


def choose_candidate(candidates,expected_elimination=None):
    filtered=[c for c in candidates if expected_elimination is None or c['elimination']==expected_elimination]
    if len(filtered)!=1:raise ValueError('Published source rows ambiguous or missing; do not guess a replay event')
    return filtered[0]


def build(pool,frozen,artifact_root,output):
    pool,frozen,artifact_root,output=map(Path,(pool,frozen,artifact_root,output))
    evidence=artifact_root/'source-evidence';site=(evidence/'site.html').read_text();paper=(evidence/'paper.html').read_text()
    text=source_text(paper)
    if '1A and 1B are Case C and Case E' not in text or '2B is Case D' not in text or 'only employs wallhack' not in text:
        raise ValueError('Published case mapping/subtype evidence changed; review sources before proceeding')
    ranges=parse_frame_ranges(site)
    source_script=evidence/'2D_vis_batch_concurrent.py'
    code=source_script.read_text()
    if 'for idx, row in sample.iterrows()' not in code or '{shap_column}_{idx}.png' not in code:
        raise ValueError('Published image-index convention changed')
    # Verify local source files against the already downloaded artifact index, not their filenames alone.
    index=json.loads((artifact_root/'archive-index.json').read_text())
    cache=artifact_root/'XGuardian_USENIX_Sec_26_v2.zip.partial'
    split_script=evidence/'split_shap_csv_to_subCSVs.py'
    if "groupby(['steamid', 'kill_num', 'match_id'])" not in split_script.read_text() or 'range(0, len(samples), 20)' not in split_script.read_text():
        raise ValueError('Published split-batch convention changed')
    for path,suffix in [(source_script,'5.7_Case_Study/elimination_scope/src/scripts/2D_vis_batch_concurrent.py'),(split_script,'5.7_Case_Study/elimination_scope/src/scripts/split_shap_csv_to_subCSVs.py')]:
        entries=[e for e in index if e['name'].endswith(suffix)]
        if len(entries)!=1:raise ValueError('Unique archive source member required')
        data=path.read_bytes();entry=entries[0]
        if len(data)!=entry['size'] or zlib.crc32(data)!=entry['crc']:raise ValueError('Artifact member CRC/size mismatch')
    bundle=load_model(frozen);manifest=json.loads((pool/'manifest.json').read_text());receipt=json.loads((pool/'pool-receipt.json').read_text())
    if manifest.get('role')!='development' or not manifest.get('features_inspected') or receipt['manifest_sha256']!=digest(pool/'manifest.json'):
        raise ValueError('Inspected pool receipt mismatch')
    studies=json.loads((artifact_root/'study-cases.json').read_text());lookup={c['case']:c for c in studies}
    if not set(CASE_MAP)<=set(lookup):raise ValueError('Study mapping missing')
    cases=manifest['cases'];by_demo={c['demo_sha256']:(i,c) for i,c in enumerate(cases,1)}
    if len(by_demo)!=len(cases):raise ValueError('Duplicate pool demos')
    source_rows={(name,display):[] for name,(paper_case,kind) in CASE_MAP.items() for display in ranges[paper_case]}
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='source_attributed_review_anchors',paper=PAPER_URL,site=SITE_URL,
        manifest_sha256=digest(pool/'manifest.json'),study_sha256=digest(artifact_root/'study-cases.json'),
        source_sha256={p.name:digest(p) for p in (cache,source_script,split_script,artifact_root/'archive-index.json',evidence/'site.html',evidence/'paper.html')},
        code_sha256=digest(__file__),mapping='Published image frame -> selected-player processed CSV row -> recorded tick -> replay death event; use original split-batch row indices; image-copy CRC/size identities disambiguate where available; no activation labels.',
        training_labels_changed=False,activation_ground_truth=None))
    entries=[e for e in index if '/Design/src/Explainer_vis/test_set_data/cheater_part_' in e['name'] and e['name'].endswith('.csv')]
    for entry in entries:
        body=cached_member(cache,entry)
        frame=pd.read_csv(io.BytesIO(body),usecols=['steamid','match_id','tick','kill_num','isKilling'],dtype={'steamid':str})
        for study,(paper_case,kind) in CASE_MAP.items():
            identity=lookup[study]
            for display,bounds in ranges[paper_case].items():
                part=frame.iloc[bounds[0]:bounds[1]+1]
                if (len(part)==bounds[1]-bounds[0]+1 and part.match_id.eq(identity['match_id']).all()
                    and part.steamid.map(float).eq(float(identity['steamid'])).all() and part.kill_num.nunique()==1):
                    source_rows[(study,display)].append(dict(frame=frame,member=entry['name'],elimination=int(part.kill_num.iloc[0])))
    anchors=[];case_evidence={};records={}
    for study,(paper_case,kind) in CASE_MAP.items():
        source=lookup[study]
        if source['demo_sha256'] not in by_demo:raise ValueError('Study demo not linked to development pool')
        position,case=by_demo[source['demo_sha256']]
        if any(source[key]!=case[key] for key in ('steamid','match_id')) or source['study_label']!=case['label']:
            raise ValueError('Study/development identity or label mismatch')
        training=next(r for r in bundle['development'] if r['case_id']==case['case_id'])
        directory=pool/'analysis'/f'job_{position:04d}';tracking_path=pool/'tracking'/f'case_{position:04d}.json'
        report=json.loads((directory/'report.json').read_text());tracking=json.loads(tracking_path.read_text())
        expected=receipt['cases'][position-1]
        if (digest(case['demo'])!=case['demo_sha256'] or digest(directory/'report.json')!=expected['report_sha256']
            or digest(tracking_path)!=expected['tracking_sha256'] or expected['case_id']!=case['case_id']
            or report['steamid']!=case['steamid'] or report['source_sha256']!=case['demo_sha256']):raise ValueError('Replay/report identity or receipt mismatch')
        for filename in ('report.json','telemetry.csv','events.json'):
            if digest(directory/filename)!=tracking['input_sha256'][filename]:raise ValueError('Canonical source checksum mismatch')
        events=json.loads((directory/'events.json').read_text())
        kills={e['tick'] for e in events if e['event_type']=='player_death' and e.get('attacker_steamid')==case['steamid']}
        case_evidence[case['case_id']]=dict(study_case=study,published_case=paper_case,author_description=kind,source=SITE_URL,
            paper_source=PAPER_URL,scope='published case narrative; not an independent tick-level label')
        records[case['case_id']]=tracking
        for display_elimination,bounds in ranges[paper_case].items():
            expected_elimination=image_elimination_identity(index,paper_case,display_elimination,bounds,source)
            candidate=choose_candidate(source_rows[(study,display_elimination)],expected_elimination)
            anchor=map_frame_window(candidate['frame'],bounds,case['steamid'],training['participants'],kills)
            anchor.update(split_source_member=candidate['member'],duplicate_image_elimination_identity=expected_elimination)
            overlaps=[dict(window_index=i,engagement_id=w['engagement_id'],round_id=w['round_id'],first_shot_tick=w['shot_ticks'][0])
                for i,w in enumerate(report['engagements']) if w['start_tick']<=anchor['replay_kill_tick']<=w['end_tick']]
            anchors.append(dict(case_id=case['case_id'],study_case=study,published_case=paper_case,
                published_display_elimination=display_elimination,author_description=kind,overlapping_analysis_windows=overlaps,**anchor))
            samples=pd.read_csv(directory/'telemetry.csv',usecols=['tick','yaw','pitch','active','segment_id'])
            local=samples.loc[samples.tick.between(anchor['replay_kill_tick']-3,anchor['replay_kill_tick']+3)]
            anchors[-1]['saved_two_axis_context']=local.to_dict('records')
    rows=[dict(case_id=c['case_id'],original_label=c['label'],author_case_evidence=case_evidence.get(c['case_id']),
               aimbot_activation_ground_truth=None) for c in cases]
    result=dict(cases=rows,anchors=anchors,training_labels_changed=False,activation_ground_truth=None,
                protocol_sha256=digest(output/'protocol.json'),note='Author claims and provisional source-row references only. Existing cheating labels and all performance results remain unchanged.')
    write_json(output/'anchors.json',result)
    from scripts.render_target_tracking import PAGE
    for case_id,tracking in records.items():
        payload=json.dumps(tracking,allow_nan=False).replace('<',r'\u003c')
        (output/f'{case_id}-tracks.html').write_text(PAGE.replace('__DATA__',payload))
    body=[]
    for a in anchors:
        links=[]
        for w in a['overlapping_analysis_windows']:
            tracking=records[a['case_id']]['windows'][w['window_index']];candidate=tracking['nearest_before_first_shot']
            opponent=next((i for i,t in enumerate(tracking['tracks']) if t['opponent_id']==candidate),0)
            links.append(f'<a href="{a["case_id"]}-tracks.html#w={w["window_index"]}&amp;t={opponent}">Window {w["engagement_id"]}</a>')
        cells=[a['case_id'],a['published_case'],a['published_display_elimination'],f"{a['published_frame_start']}–{a['published_frame_end']}",
               f"{a['replay_start_tick']}–{a['replay_end_tick']}",str(a['replay_kill_tick'])]
        body.append('<tr>'+''.join('<td>'+html.escape(c)+'</td>' for c in cells)+'<td>'+(' · '.join(links) or 'No canonical window')+'</td></tr>')
    details=[]
    for a in anchors:
        sample_rows=[]
        for row in a['saved_two_axis_context']:
            sample_rows.append('<tr>'+''.join('<td>'+html.escape(str(row[k]))+'</td>' for k in ('tick','yaw','pitch','active'))+'</tr>')
        details.append('<h2>'+html.escape(a['case_id'])+' · kill '+str(a['replay_kill_tick'])+'</h2><table><tr><th>Replay tick</th><th>Yaw °</th><th>Pitch °</th><th>Active</th></tr>'+''.join(sample_rows)+'</table>')
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Published case review anchors</title><style>body{font:17px system-ui;max-width:1150px;margin:30px auto;padding:20px}p{line-height:1.5}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}table{border-collapse:collapse}</style><h1>Published case review anchors</h1><p>Five focused source-attributed review bookmarks. Processed image frame IDs are distinct from replay ticks. The row-order link is provisional; no aimbot activation labels or rendered gameplay reviews have been created.</p><p>D-1A: authors describe aimbot; D-1B: aimbot and wallhack; D-2B: wallhack-only. Original match labels and detection results are unchanged.</p><table><tr><th>Local case</th><th>Published case</th><th>Display event</th><th>Image frames</th><th>Replay ticks</th><th>Kill tick</th><th>Local trajectory</th></tr>'+''.join(body)+'</table>'+''.join(details)+'<p>Sources: <a href="'+PAPER_URL+'">Paper §5.7/5.10 and Appendix E</a> · <a href="'+SITE_URL+'">Author case descriptions</a>. These bookmarks are selected development references, not independent evaluation data.</p></html>'
    (output/'index.html').write_text(page);print(f'{len(anchors)} provisional source-to-replay event anchors; original labels unchanged',flush=True);return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('pool','frozen','artifact_root'):parser.add_argument(name,type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args(argv);build(args.pool,args.frozen,args.artifact_root,args.output)


if __name__=='__main__':main()

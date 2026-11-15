"""Audit geometric/event disagreements without inferring intended targets."""
import argparse
from collections import Counter
import html
import json
import os
from pathlib import Path

from aimguard.baseline import digest, write_json
from aimguard.target_tracking import matching_damage


def observation(track, tick):
    """Exact recorded sample only; no nearest-time fallback or interpolation."""
    if track is None:
        return None
    ticks=track['ticks']
    if len(set(ticks))!=len(ticks) or any(b<=a for a,b in zip(ticks,ticks[1:])):
        raise ValueError('Track ticks must increase strictly')
    if len(ticks)!=len(track['segment_ids']) or len(ticks)!=len(track['signed_error_degrees']):
        raise ValueError('Track sample arrays must align')
    try:
        index=ticks.index(tick)
    except ValueError:
        return None
    value=track['signed_error_degrees'][index]
    segment=track['segment_ids'][index]
    if value is None or segment<0:
        return None
    if not isinstance(value,(int,float)) or not -180<=value<=180:
        raise ValueError('Invalid signed bearing error')
    return dict(absolute_error_degrees=abs(value),segment_id=segment)


def audit_event(window,event,anchor="shot_tick"):
    """Compare only the first candidate and recipient; this is not a global rank."""
    first=window['shot_ticks'][0]
    before=event['tick']-1
    if anchor not in ('shot_tick','pre_shot_tick'):
        raise ValueError('Unknown candidate anchor')
    anchor_tick=first if anchor=='shot_tick' else first-1
    candidate=window.get('nearest_at_first_shot' if anchor=='shot_tick' else 'nearest_before_first_shot')
    recipient=event['opponent_id']
    tracks={track['opponent_id']:track for track in window['tracks']}
    if len(tracks)!=len(window['tracks']):
        raise ValueError('Duplicate opponent tracks')
    record=dict(damage_tick=event['tick'],pre_damage_tick=before,first_shot_tick=first,
        anchor=anchor,anchor_tick=anchor_tick,initial_candidate=candidate,damage_recipient=recipient,
        classification=None,initial=None,pre_damage=None)
    if candidate is None:
        record['classification']='no_initial_candidate';return record
    if candidate==recipient:
        record['classification']='initial_agreement';return record
    if before<=anchor_tick:
        record['classification']='no_later_pre_damage_sample';return record
    initial=[observation(tracks.get(player),anchor_tick) for player in (candidate,recipient)]
    later=[observation(tracks.get(player),before) for player in (candidate,recipient)]
    record['initial']=dict(zip(('candidate','recipient'),initial))
    record['pre_damage']=dict(zip(('candidate','recipient'),later))
    if any(value is None for value in initial):
        record['classification']='initial_pair_unavailable';return record
    if any(value is None for value in later):
        record['classification']='pre_damage_pair_unavailable';return record
    if any(a['segment_id']!=b['segment_id'] for a,b in zip(initial,later)):
        record['classification']='pair_interrupted';return record
    initial_gap=initial[1]['absolute_error_degrees']-initial[0]['absolute_error_degrees']
    later_gap=later[1]['absolute_error_degrees']-later[0]['absolute_error_degrees']
    record.update(initial_recipient_minus_candidate_degrees=initial_gap,
                  pre_damage_recipient_minus_candidate_degrees=later_gap)
    tolerance=1e-6 # Numeric tie handling, not an aim/detection threshold.
    if initial_gap < -tolerance:
        record['classification']='initial_ranking_inconsistent'
    elif later_gap < -tolerance:
        record['classification']='pairwise_rank_reversal'
    elif later_gap > tolerance:
        record['classification']='initial_candidate_still_closer'
    else:
        record['classification']='pairwise_tie'
    return record


def audit(manifest_path,analysis_root,tracking_root,output):
    manifest=json.loads(Path(manifest_path).read_text())
    if manifest.get('role')!='development':
        raise ValueError('Association audit requires development data')
    tracking_root=Path(tracking_root)
    summary=json.loads((tracking_root/'summary.json').read_text())
    if summary['manifest_sha256']!=digest(manifest_path):
        raise ValueError('Tracking manifest checksum mismatch')
    if len(summary['cases'])!=len(manifest['cases']):
        raise ValueError('Tracking case count mismatch')
    rows=[];cases=[];input_hashes={}
    for index,(case,case_summary) in enumerate(zip(manifest['cases'],summary['cases']),1):
        source=tracking_root/f'case_{index:04d}.json'
        record=json.loads(source.read_text())
        if record['summary']!=case_summary or case_summary['case_id']!=case['case_id'] or case_summary['label']!=case['label']:
            raise ValueError('Tracking case identity mismatch')
        directory=Path(analysis_root)/f'job_{index:04d}'
        for name,expected in record['input_sha256'].items():
            if digest(directory/name)!=expected:
                raise ValueError('Tracking source input checksum mismatch')
        report=json.loads((directory/'report.json').read_text())
        if report['steamid']!=case['steamid'] or report['source_sha256']!=case['demo_sha256'] or record['demo_sha256']!=case['demo_sha256']:
            raise ValueError('Replay/report identity mismatch')
        if len(report['engagements'])!=len(record['windows']):
            raise ValueError('Tracking window count mismatch')
        events=json.loads((directory/'events.json').read_text())
        deaths={(event['tick'],event.get('user_steamid')) for event in events
                if event['event_type']=='player_death' and event.get('attacker_steamid')==case['steamid']}
        counts=Counter();pre_counts=Counter();unique=set();window_disagreements=set()
        for window_index,(window,published) in enumerate(zip(record['windows'],report['engagements'])):
            if 'nearest_before_first_shot' not in window:
                raise ValueError('Regenerate tracking with pre-shot candidates before comparing anchors')
            for key in ('engagement_id','weapon','shot_ticks','round_id'):
                if window[key]!=published[key]:
                    raise ValueError('Tracking window identity mismatch')
            damage=matching_damage(events,published,case['steamid'])
            if window['damage_events']!=damage:
                raise ValueError('Tracking damage association mismatch')
            for event in damage:
                row=audit_event(window,event)
                row['pre_shot_audit']=audit_event(window,event,'pre_shot_tick')
                pre_counts[row['pre_shot_audit']['classification']]+=1
                row.update(recipient_killed_at_damage_tick=(event['tick'],event['opponent_id']) in deaths,
                    damage_at_first_shot=event['tick']==window['shot_ticks'][0])
                row.update(case_id=case['case_id'],label=case['label'],window_index=window_index,
                    engagement_id=window['engagement_id'],weapon=window['weapon'],damage=event['damage'])
                unique.add((event['tick'],event['opponent_id'],window['weapon'],event['damage']))
                counts[row['classification']]+=1
                if row['classification']!='initial_agreement':window_disagreements.add(window_index)
                rows.append(row)
        input_hashes[case['case_id']]=digest(source)
        cases.append(dict(case_id=case['case_id'],label=case['label'],damage_occurrences=sum(counts.values()),
            unique_damage_records=len(unique),windows_with_nonagreement=len(window_disagreements),classifications=dict(counts),pre_shot_classifications=dict(pre_counts)))
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    definitions=dict(initial_agreement='Candidate at the selected anchor is the damage recipient; no intended-target assertion.',
        pairwise_rank_reversal='Recipient becomes closer in horizontal bearing than the original candidate, with both tracks uninterrupted. Supports changed geometric ordering, not verified target switching.',
        initial_candidate_still_closer='Original candidate remains horizontally closer at the exact tick before damage. Visibility, vertical aim, recoil and timing remain unresolved.',
        pair_interrupted='At least one track has a gap, invalid sample, death or team change between comparison samples.',
        no_later_pre_damage_sample='No exact pre-damage sample strictly later than the selected anchor is available.',
        initial_pair_unavailable='One compared player lacks valid geometry at the selected anchor.',
        pre_damage_pair_unavailable='One compared player lacks valid geometry at the exact tick before damage.',
        pairwise_tie='Horizontal differences are numerically tied within 1e-6 degrees.',
        no_initial_candidate='No alive geometric candidate at the selected anchor.',
        initial_ranking_inconsistent='Saved initial errors contradict geometric selection; investigate extraction before interpreting.')
    totals=dict(Counter(row['classification'] for row in rows))
    pre_totals=dict(Counter(row['pre_shot_audit']['classification'] for row in rows))
    lethal_first_disagreements=sum(row['classification']!='initial_agreement' and row['recipient_killed_at_damage_tick'] and row['damage_at_first_shot'] for row in rows)
    write_json(output/'audit.json',dict(role='development_association_audit',cases=cases,occurrences=rows,
        totals=totals,pre_shot_totals=pre_totals,lethal_first_shot_disagreement_occurrences=lethal_first_disagreements,definitions=definitions,code_sha256=digest(__file__),
        input_sha256=dict(manifest=digest(manifest_path),tracking_summary=digest(tracking_root/'summary.json'),cases=input_hashes),
        limitations=['Pairwise horizontal ordering is not intended-target or visibility ground truth',
            'Each damage record can occur in overlapping windows; occurrence counts are not independent trials',
            'Exact pre-damage tick only; no lag, subtick, recoil, vertical or hitbox correction',
            'Same-weapon damage links do not assign individual bullets',
            'No model fitting or threshold change; development data only']))
    lines=['# Target-association disagreement audit','',
        f'{len(rows)} window damage occurrences; {sum(c["unique_damage_records"] for c in cases)} distinct source damage records across {len(cases)} cases.',
        'Occurrences can repeat in overlapping windows. Counts below are not independent trials or target-attribution accuracy.',
        'Compare separate candidates chosen at the first shot and its exact preceding tick. Neither selection uses damage recipients. For disagreements, compare each fixed candidate with the recipient at its anchor and exactly one tick before damage.',
        f'{lethal_first_disagreements} shot-tick disagreement occurrences have same-tick first-shot damage and a recorded kill of that recipient. This documents death-state selection bias, not intended-target truth.',
        '', '| Classification | Shot-tick anchor | Pre-shot anchor |', '| --- | ---: | ---: |',
        *[f'| {name} | {totals.get(name,0)} | {pre_totals.get(name,0)} |' for name in sorted(set(totals)|set(pre_totals))],
        '', '## Interpretation','',*[f'- {name}: {text}' for name,text in definitions.items()],
        '', 'No human gameplay annotation, intended-target verdict, or new detection performance is inferred.','']
    (output/'report.md').write_text('\n'.join(lines))
    # Link to exact window/track selections in the existing local viewers.
    case_indexes={case['case_id']:index for index,case in enumerate(manifest['cases'],1)}
    focus={'E-05','E-09','E-01','E-08','D-3A'}
    examples=[]
    for row in rows:
        if row['case_id'] not in focus or row['classification']=='initial_agreement':continue
        key=(row['case_id'],row['classification'])
        if any(item[0]==key for item in examples):continue
        index=case_indexes[row['case_id']]
        case_record=json.loads((tracking_root/f'case_{index:04d}.json').read_text())
        window=case_record['windows'][row['window_index']]
        track_index=next(i for i,t in enumerate(window['tracks']) if t['opponent_id']==row['damage_recipient'])
        relative=os.path.relpath(tracking_root/f'case_{index:04d}.html',output)
        url=f'{relative}#w={row["window_index"]}&t={track_index}'
        examples.append((key,f'<li><a href="{html.escape(url,quote=True)}">{html.escape(row["case_id"])} · window {row["engagement_id"]+1} · damage tick {row["damage_tick"]}</a> — shot: {html.escape(row["classification"])}; pre-shot: {html.escape(row["pre_shot_audit"]["classification"])}</li>'))
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>AimGuard association audit</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:20px}pre{white-space:pre-wrap}li{margin:12px}</style><h1>Association disagreements</h1><p>Selected examples: first occurrence of each classification in missed/false-flag cases. These are programmatic findings, not human gameplay annotations.</p><ul>'+''.join(item[1] for item in examples)+'</ul><pre>'+html.escape('\n'.join(lines))+'</pre>')
    print('\n'.join(lines[:18]))
    return dict(shot_tick=totals,pre_shot_tick=pre_totals)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path);parser.add_argument('analysis_root',type=Path);parser.add_argument('tracking_root',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    audit(args.manifest,args.analysis_root,args.tracking_root,args.output)


if __name__=='__main__':main()

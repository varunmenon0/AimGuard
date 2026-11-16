"""Reversible stable-prealignment exclusion experiment and event review queue."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from aimguard.baseline import digest, report_features, write_json
from aimguard.tracking_models import case_features, window_features, with_abstentions

ALIGNMENT_DEGREES = 3.
SEPARATION_DEGREES = 3.
MIN_WINDOWS = 5
MIN_ROUNDS = 3


def exclusion_reason(snapshots):
    """Only fully observed, stable sampled prealignment qualifies; never a legit label."""
    if len(snapshots)!=3: raise ValueError('Need exact endpoint, 100 ms and 200 ms snapshots')
    if any(s['status']!='available' for s in snapshots): return 'retained_unknown_context'
    nearest=snapshots[0]['nearest']
    if any(s['nearest']!=nearest for s in snapshots): return 'retained_alignment_changes'
    for s in snapshots:
        if not s['candidates'] or s['nearest_error']>ALIGNMENT_DEGREES: return 'retained_alignment_changes'
        gap=s['runner_up_gap']
        if len(s['candidates'])>1 and (gap is None or gap<SEPARATION_DEGREES): return 'retained_ambiguous_geometry'
    return 'excluded_stable_sampled_pre_alignment'


def filtered_features(report, tracking, snapshot_windows):
    if len(report['engagements'])!=len(tracking['windows']) or len(snapshot_windows)!=len(tracking['windows']):
        raise ValueError('Window counts mismatch')
    kept=[]; kept_tracks=[]; counts=Counter(); details=[]; eligible_rounds=set(); eligible_count=0
    for published, track, sampled in zip(report['engagements'],tracking['windows'],snapshot_windows):
        if (any(published[k]!=track[k] for k in ('engagement_id','round_id','shot_ticks','weapon'))
            or published['engagement_id']!=sampled['engagement_id'] or published['shot_ticks'][0]!=sampled['first_shot_tick']
            or published['weapon']!=sampled['weapon']): raise ValueError('Window identities mismatch')
        if sampled['snapshots'][0].get('nearest')!=track['nearest_before_first_shot']:
            raise ValueError('Candidate identity mismatch')
        reason=exclusion_reason(sampled['snapshots']);counts[reason]+=1
        details.append(dict(engagement_id=published['engagement_id'],round_id=published['round_id'],
                            first_shot_tick=published['shot_ticks'][0],start_tick=published['start_tick'],end_tick=published['end_tick'],reason=reason))
        if reason.startswith('excluded'):continue
        kept.append(published);kept_tracks.append(track)
        value,_=window_features(track,report['assumed_tickrate_hz'])
        if value is not None: eligible_rounds.add(published['round_id']);eligible_count+=1
    coverage=dict(total_windows=len(snapshot_windows),retained_windows=len(kept),eligible_tracking_windows=eligible_count,
                  eligible_rounds=sorted(eligible_rounds),selection_counts=dict(counts),windows=details)
    if eligible_count<MIN_WINDOWS or len(eligible_rounds)<MIN_ROUNDS:
        return None,dict(coverage,abstention_reason=f'Need {MIN_WINDOWS} eligible retained windows across {MIN_ROUNDS} distinct rounds')
    tracking_values,_=case_features(kept_tracks,report['assumed_tickrate_hz'])
    speed,_=report_features(dict(report,engagements=kept))
    return [*speed,*tracking_values],dict(coverage,abstention_reason=None)


def compare(pool,baseline_directory,candidate_directory,output):
    pool,baseline_directory,candidate_directory,output=map(Path,(pool,baseline_directory,candidate_directory,output))
    manifest=json.loads((pool/'manifest.json').read_text());receipt=json.loads((pool/'pool-receipt.json').read_text())
    baseline=json.loads((baseline_directory/'comparison.json').read_text());base_protocol=json.loads((baseline_directory/'protocol.json').read_text())
    base_inputs=json.loads((baseline_directory/'inputs.json').read_text());sample=json.loads((candidate_directory/'summary.json').read_text())
    candidate_protocol=json.loads((candidate_directory/'protocol.json').read_text())
    if (manifest.get('role')!='development' or manifest.get('features_inspected') is not True
        or receipt['manifest_sha256']!=digest(pool/'manifest.json') or base_protocol['manifest_sha256']!=digest(pool/'manifest.json')
        or baseline['protocol_sha256']!=digest(baseline_directory/'protocol.json') or baseline['inputs_sha256']!=digest(baseline_directory/'inputs.json')
        or sample['protocol_sha256']!=digest(candidate_directory/'protocol.json') or candidate_protocol['manifest_sha256']!=digest(pool/'manifest.json')
        or candidate_protocol['baseline_sha256']!=digest(baseline_directory/'comparison.json') or base_inputs['groups']!=receipt['groups']
        or base_protocol['threshold']!=.5 or base_protocol['hyperparameters']!=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0)):
        raise ValueError('Development source protocol/receipt mismatch')
    cases=manifest['cases'];ids=[c['case_id'] for c in cases]
    if candidate_protocol['sample']!=ids or [c['case_id'] for c in sample['cases']]!=ids:
        raise ValueError('Require all development cases in manifest order, not selected errors')
    membership=[cid for members in receipt['groups'].values() for cid in members]
    if len(ids)!=len(set(ids)) or len(membership)!=len(set(membership)) or set(membership)!=set(ids):raise ValueError('Duplicate/missing group identities')
    if any(c['label'] not in ('cheating','legitimate') for c in cases):raise ValueError('Unknown label')
    if any(len(rows)!=len(cases) for rows in (receipt['cases'],base_inputs['cases'],base_inputs['tracking'])):raise ValueError('Case source counts mismatch')
    original=baseline['models']['speed_and_tracking']
    if len(original['predictions'])!=len(cases) or {r['case_id']:r['label'] for r in original['predictions']}!={c['case_id']:c['label'] for c in cases}:
        raise ValueError('Baseline labels/coverage mismatch')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='post_feedback_development',recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        alignment_degrees=ALIGNMENT_DEGREES,separation_degrees=SEPARATION_DEGREES,min_windows=MIN_WINDOWS,min_distinct_rounds=MIN_ROUNDS,
        threshold=.5,hyperparameters=base_protocol['hyperparameters'],manifest_sha256=digest(pool/'manifest.json'),
        baseline_sha256=digest(baseline_directory/'comparison.json'),candidate_summary_sha256=digest(candidate_directory/'summary.json'),
        code_sha256=digest(__file__),cases=[dict(case_id=cid) for cid in ids],
        note='One fixed sampled-prealignment exclusion hypothesis, not verified ordinary aim. Refit the original feature recipe within training groups; no cutoff/parameter/eligibility search. Different rounds are support counts, not statistically independent labels.'))
    vectors=[];coverage=[];review=[]
    for index,case in enumerate(cases,1):
        directory=pool/'analysis'/f'job_{index:04d}';path=pool/'tracking'/f'case_{index:04d}.json';candidate_path=candidate_directory/f"{case['case_id']}.json"
        report=json.loads((directory/'report.json').read_text());tracking=json.loads(path.read_text());snapshots=json.loads(candidate_path.read_text())
        expected=receipt['cases'][index-1];prior=base_inputs['tracking'][index-1]
        if (expected['case_id']!=case['case_id'] or prior['case_id']!=case['case_id'] or snapshots['case_id']!=case['case_id']
            or report['steamid']!=case['steamid'] or report['source_sha256']!=case['demo_sha256'] or tracking['demo_sha256']!=case['demo_sha256']
            or digest(directory/'report.json')!=expected['report_sha256'] or digest(path)!=expected['tracking_sha256'] or digest(path)!=prior['tracking_sha256']
            or sample['case_sha256'][case['case_id']]!=digest(candidate_path)
            or snapshots['source_sha256']!=dict(demo=case['demo_sha256'],report=digest(directory/'report.json'),tracking=digest(path))):
            raise ValueError('Source identity/hash mismatch')
        for name in ('report.json','telemetry.csv','events.json'):
            if digest(directory/name)!=tracking['input_sha256'][name]:raise ValueError('Tracking input checksum mismatch')
        for published,sampled in zip(report['engagements'],snapshots['windows']):
            wanted=[published['shot_ticks'][0]-1-round(lag*report['assumed_tickrate_hz']) for lag in (0,.1,.2)]
            if [s['tick'] for s in sampled['snapshots']]!=wanted:raise ValueError('Snapshot time alignment mismatch')
        value,counts=filtered_features(report,tracking,snapshots['windows']);vectors.append(value)
        coverage.append(dict(case_id=case['case_id'],label=case['label'],features=value,report_sha256=digest(directory/'report.json'),tracking_sha256=digest(path),**counts))
        for w in report['engagements']:
            review.append(dict(review_id=f"{case['case_id']}:{w['engagement_id']}",case_id=case['case_id'],engagement_id=w['engagement_id'],
                round_id=w['round_id'],demo=case['demo'],demo_sha256=case['demo_sha256'],steamid=case['steamid'],start_tick=w['start_tick'],first_shot_tick=w['shot_ticks'][0],end_tick=w['end_tick'],
                review_status='pending',review_source='unreviewed',observed_behavior='unreviewed',assistance_assessment='unreviewed',evidence_reference='',evidence_note='',reviewer=''))
    group_by_case={cid:int(g) for g,members in receipt['groups'].items() for cid in members}
    groups=[group_by_case[cid] for cid in ids];labels=[int(c['label']=='cheating') for c in cases]
    write_json(output/'inputs.json',dict(cases=coverage,groups=receipt['groups']))
    with (output/'event-review-template.csv').open('x',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(review[0]));writer.writeheader();writer.writerows(review)
    write_json(output/'review-queue.json',dict(role='pending_behavior_review',manifest_sha256=digest(pool/'manifest.json'),template_sha256=digest(output/'event-review-template.csv'),events=review,
        note='All pending. Source labels and model scores omitted. Human observations are not ground-truth cheat activation labels.'))
    candidate=with_abstentions(vectors,labels,groups,ids,'log1p')
    counts_by_id={c['case_id']:c for c in coverage}
    for row in candidate['predictions']:
        if row['status']=='abstained' and counts_by_id[row['case_id']]['abstention_reason']:row['error']=counts_by_id[row['case_id']]['abstention_reason']
    models=dict(original_speed_and_tracking=original,filtered_repeated_encounters=candidate)
    result=dict(cases=len(cases),participant_groups=len(set(groups)),models=models,protocol_sha256=digest(output/'protocol.json'),inputs_sha256=digest(output/'inputs.json'),review_queue_sha256=digest(output/'review-queue.json'),
        interpretation='Previously inspected development cases; abstentions are missing decisions, never legitimate classifications. Neither recipe is automatically promoted.')
    write_json(output/'comparison.json',result)
    lines=['# Stable-prealignment exclusion and repeated-round support experiment','','All development cases included; model/scaling fit within training groups only. Fixed cutoff 0.5.','',
        '| Recipe | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,model in models.items():
        c=model['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {model['metrics']['abstentions']} |")
    removed=sum(c['selection_counts'].get('excluded_stable_sampled_pre_alignment',0) for c in coverage)
    lines+=['',f'{removed} windows excluded by the fixed geometric proxy. Event review template has {len(review)} pending rows; no event-level ground truth has been created.',
        'Alignment within 3 degrees, same nearest opponent at exact pre-shot/100/200 ms snapshots, and at least 3 degrees runner-up gap (or a sole candidate) are required for exclusion.',
        'Unknown/ambiguous contexts stay in the pool. At least five eligible retained windows across three distinct rounds are required per case; missing support abstains.',
        'Three sparse snapshots do not prove continuous alignment, legitimate behavior, visibility or intended target. An aimbot holding aim could also be excluded. No threshold/parameter search or historical prediction change.','']
    (output/'report.md').write_text('\n'.join(lines));print('\n'.join(lines),flush=True);return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('pool','baseline_directory','candidate_directory'):parser.add_argument(name,type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args(argv)
    compare(args.pool,args.baseline_directory,args.candidate_directory,args.output)


if __name__=='__main__':main()

"""Acquire a bounded metadata-only legitimate cohort with up to two labels/match."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
from zipfile import ZipFile

import zstandard

from aimguard.baseline import digest, write_json
from aimguard.gameplay import identity_strings
from aimguard.offline_detector import load
from aimguard.tracking_baseline import load_model
from scripts.acquire_fresh_cases import PrefixSource, URL, metadata_labels, recorded_exclusions, unique_exact_id
from scripts.audit_replay_identities import CONTROLLER_ID, account_id, identity_evidence


def select_labels(rows, participants, remaining, per_match=2):
    """All selection is source metadata, with a fixed cap and no score input."""
    resolved = []; seen = set()
    for row in sorted(rows, key=lambda r: hashlib.sha256((r['match_id']+r['steamid']).encode()).hexdigest()):
        if row['isCheater'] != '0':
            continue
        exact = unique_exact_id(row['steamid'], participants)
        if exact is None or not account_id(exact) or exact in seen:
            continue
        resolved.append(dict(row, exact_steamid=exact)); seen.add(exact)
    return resolved[:max(0, min(per_match, remaining))]


def acquire(output, cache, prefetch, target=50, limit_gib=20, extraction_gib=24):
    from demoparser2 import DemoParser
    output, cache, prefetch = map(Path, (output, cache, prefetch))
    model = Path('outputs/xguardian/offline-v06/frozen'); bundle = load(model)
    legacy = Path('outputs/xguardian/tracking-baseline-v2/frozen')
    blocked_raw, blocked_matches, receipts = recorded_exclusions(load_model(legacy), legacy)
    blocked_raw.update(bundle['excluded_participants'])
    blocked = {s for s in blocked_raw if account_id(s)}
    inventory = Path('outputs/xguardian/evaluation-inventory-v2/inventory.json')
    blocked_matches.update(r['match_id'] for r in json.loads(inventory.read_text())['replays'])
    previous_plan = Path('data/external/xguardian/expansion-candidates-v3/plan.json')
    label_sources = json.loads(previous_plan.read_text())['label_sources']
    for path, sha in label_sources.items():
        if digest(path) != sha:
            raise ValueError('Label table changed')
    labels = metadata_labels(list(label_sources))
    if target < 1 or limit_gib*1024**3 < cache.stat().st_size or extraction_gib <= 0:
        raise ValueError('Invalid acquisition bounds')
    output.mkdir(parents=True, exist_ok=False)
    plan = dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(), model_sha256=digest(model/'model.json'),
        threshold=bundle['threshold'], source_url=URL, target_legitimate_players=target, max_players_per_match=2,
        minimum_match_groups_for_target=(target+1)//2, compressed_cache_limit_bytes=int(limit_gib*1024**3),
        initial_cache_bytes=cache.stat().st_size, extracted_file_limit_bytes=int(extraction_gib*1024**3),
        source_label_sha256=label_sources, prior_reservations=receipts,
        prior_inventory_sha256=digest(inventory), excluded_account_participants=sorted(blocked),
        excluded_match_ids=sorted(blocked_matches), code_sha256=digest(__file__),
        helper_sha256={p:digest(p) for p in ('scripts/acquire_fresh_cases.py','scripts/audit_replay_identities.py')},
        selection='Archive order, uninspected participant-disjoint matches; up to two uniquely source-labeled legitimate players/match in SHA256(match+source token) order, stop at target. Never infer labels for teammates or inspect features/scores.',
        caveat='Players sharing a demo form a match group, not independent validation observations. Archive convenience sample; no skill-rating annotations or representative population guarantee.')
    write_json(output/'plan.json', plan)
    source = PrefixSource(cache, prefetch, plan['compressed_cache_limit_bytes'])
    cases = []; groups = []; rejected = []; scanned = []; used = set(); seen_matches = set()
    total_extracted = 0; status = 'scanning'; error_text = None
    def checkpoint():
        value = dict(status=status, cases=cases, groups=groups, rejected=rejected, scanned=scanned,
            compressed_cache_bytes=cache.stat().st_size, extracted_file_bytes=total_extracted,
            plan_sha256=digest(output/'plan.json'), features_inspected=False, error=error_text)
        temp = output/'acquisition.tmp'; temp.write_text(json.dumps(value, indent=2)+'\n'); temp.replace(output/'acquisition.json')
    try:
        with zstandard.ZstdDecompressor(max_window_size=1073741824).stream_reader(source, closefd=False) as decoded:
            with tarfile.open(fileobj=decoded, mode='r|') as archive:
                for member in archive:
                    if not member.isfile():
                        continue
                    name = Path(member.name).name; match = name.split('_',1)[0]
                    scanned.append(dict(name=member.name, size=member.size))
                    if not name.endswith('.zip') or match in blocked_matches | seen_matches:
                        continue
                    rows = [r for r in labels.get(match,[]) if r['isCheater']=='0']
                    if not rows:
                        continue
                    seen_matches.add(match)
                    if member.size > 1024**3:
                        raise ValueError('Nested ZIP exceeds bound')
                    if total_extracted+member.size > plan['extracted_file_limit_bytes']:
                        status='extraction_budget_reached'; break
                    zip_path = output/name
                    with archive.extractfile(member) as src, zip_path.open('xb') as dst:
                        shutil.copyfileobj(src,dst)
                    total_extracted += member.size
                    with ZipFile(zip_path) as nested:
                        if nested.testzip():
                            raise ValueError('ZIP CRC failed')
                        demos = [i for i in nested.infolist() if i.filename.endswith('.dem')]
                        if len(demos)!=1 or demos[0].file_size > 2*1024**3:
                            raise ValueError('Expected one bounded replay')
                        if total_extracted+demos[0].file_size > plan['extracted_file_limit_bytes']:
                            status='extraction_budget_reached'; break
                        demo = output/Path(demos[0].filename).name
                        with nested.open(demos[0]) as src, demo.open('xb') as dst:
                            shutil.copyfileobj(src,dst)
                        total_extracted += demos[0].file_size
                    parser=DemoParser(str(demo)); info=parser.parse_player_info(); frame=parser.parse_ticks([CONTROLLER_ID])
                    actual=identity_strings(frame[CONTROLLER_ID])
                    if not actual.equals(identity_strings(frame['steamid'])):
                        raise ValueError('Controller identity mismatch')
                    snapshot=set(identity_strings(info['steamid']))-{''}; streamed=set(actual)-{''}
                    team=parser.parse_event('player_team')
                    bot_events=int((team['isbot']==True).sum()) if hasattr(team,'columns') and 'isbot' in team else 0
                    try:
                        proof=identity_evidence(snapshot,streamed,bot_events)
                    except ValueError as exc:
                        rejected.append(dict(match_id=match,reason='unresolved_identity',error=str(exc))); checkpoint(); continue
                    humans=proof['account_participants']; overlap=set(humans)&(blocked|used)
                    selected=select_labels(rows,humans,target-len(cases))
                    if overlap or not selected:
                        rejected.append(dict(match_id=match,reason='account_overlap' if overlap else 'no_unique_legitimate_label',overlap=sorted(overlap)))
                        print(f'Rejected {match}: {rejected[-1]["reason"]}',flush=True); checkpoint(); continue
                    demo_hash=digest(demo); group_id=f'G-{len(groups)+1:03d}'
                    for row in selected:
                        cases.append(dict(case_id=f'F-{len(cases)+1:03d}',group_id=group_id,match_id=match,
                            steamid=row['exact_steamid'], label='legitimate', features_inspected=False,
                            demo=str(demo.resolve()),demo_sha256=demo_hash,participants=sorted(snapshot|streamed),
                            account_participants=humans,local_non_account_ids=proof['local_non_account_ids'],
                            source_label_file=row['source_label_file'],source_label_sha256=row['source_label_sha256'],
                            source_player_id=row['steamid'],label_scope='Source player-in-match label, not tick-level verification',
                            archive_path=member.name,zip_sha256=digest(zip_path)))
                    groups.append(dict(group_id=group_id,match_id=match,case_ids=[c['case_id'] for c in cases if c['group_id']==group_id],
                        account_participants=humans,bot_team_events=bot_events,snapshot_records=json.loads(info.to_json(orient='records'))))
                    used.update(humans)
                    print(f'Selected {match}: {len(selected)} labeled players; total {len(cases)}/{target}, {len(groups)} match groups',flush=True)
                    checkpoint()
                    if len(cases)>=target:
                        status='target_complete'; break
                else:
                    status='archive_ended_before_target'
    except (OSError,tarfile.ReadError,zstandard.ZstdError,ValueError) as exc:
        status='bounded_prefix_or_transfer_error'; error_text=f'{type(exc).__name__}: {exc}'
        print(error_text,flush=True)
    finally:
        source.close(); checkpoint()
    manifest=dict(role='grouped_legitimate_evaluation_candidates_not_reserved',features_inspected=False,
        model_sha256=plan['model_sha256'],threshold=plan['threshold'],plan_sha256=digest(output/'plan.json'),
        cases=cases,groups=groups,acquisition_status=status,caveats=[plan['caveat'],
        'Partial compressed archive: full published archive checksum not verified; nested ZIP CRC and demo hashes verified.',
        'Not scored or reserved; bind a separate group-aware single-use evaluation protocol before extraction.'])
    write_json(output/'candidates.json',manifest)
    write_json(output/'summary.json',dict(status=status,labeled_legitimate_players=len(cases),match_groups=len(groups),
        selected_account_participants=len(used),players_per_match=dict(Counter(len(g['case_ids']) for g in groups)),
        additional_cached_bytes=cache.stat().st_size-plan['initial_cache_bytes'],rejected_matches=len(rejected),error=error_text))
    load(model)
    print(f'Acquisition finished: {status}; {len(cases)} players in {len(groups)} matches',flush=True)
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cache',type=Path,required=True); p.add_argument('--prefetch',type=Path,required=True)
    p.add_argument('--target',type=int,default=50); p.add_argument('--limit-gib',type=float,default=20)
    p.add_argument('--extraction-gib',type=float,default=24); a=p.parse_args()
    acquire(a.output,a.cache,a.prefetch,a.target,a.limit_gib,a.extraction_gib)

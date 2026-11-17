"""Bounded archive-order acquisition using label and participant metadata only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import threading
from zipfile import ZipFile

import pandas as pd
import zstandard

from aimguard.baseline import digest, write_json
from aimguard.tracking_baseline import load_model, participant_ids

URL='https://zenodo.org/records/17838584/files/XGuardian_raw.tar.zst.part.001'


def metadata_labels(paths):
    """Ignore model predictions and all trajectory-derived columns."""
    rows={}
    for path in paths:
        path=Path(path)
        source_hash=digest(path)
        frame=pd.read_csv(path,usecols=['steamid','match_id','isCheater'],dtype=str)
        for row in frame.to_dict('records'):
            if row['isCheater'] not in ('0','1'):raise ValueError('Unknown source label')
            key=(row['match_id'],row['steamid'])
            if key in rows and rows[key]['isCheater']!=row['isCheater']:
                raise ValueError('Conflicting source labels for the same match/player token')
            rows.setdefault(key,dict(row,source_label_file=str(path.resolve()),source_label_sha256=source_hash))
    by_match={}
    for row in rows.values():by_match.setdefault(row['match_id'],[]).append(row)
    return by_match


def unique_exact_id(source_token,participants):
    """Never round a scientific-notation source token back into an exact ID."""
    try:encoded=float(source_token)
    except (ValueError,TypeError):return None
    matches=[value for value in participants if float(int(value))==encoded]
    return matches[0] if len(matches)==1 else None


def recorded_exclusions(bundle,model_directory):
    """A frozen bundle is immutable; its reservation registry tracks later use."""
    blocked=set(bundle['excluded_participants'])
    matches={case['match_id'] for case in bundle['development']}
    model_hash=digest(Path(model_directory)/'model.json');receipts={}
    for path in sorted((Path(model_directory)/'reservations').glob('*.reservation.json')):
        receipt=json.loads(path.read_text())
        if receipt['model_sha256']!=model_hash:
            raise ValueError('Reservation registry model mismatch during acquisition')
        for case in receipt['cases']:
            blocked.update(case['participants']);matches.add(case['match_id'])
        receipts[path.name]=digest(path)
    return blocked,matches,receipts


def range_header_ok(text,start,end):
    # Validate the final response, not redirect/interim headers.
    blocks=re.split(r'\r?\n\r?\n',text.strip())
    final=next((block for block in reversed(blocks) if block.startswith('HTTP/')), '')
    if not re.match(r'HTTP/\S+ 206(?:[ \t]|\r?\n|$)',final):return False
    match=re.search(r'(?im)^content-range:\s*bytes\s+(\d+)-(\d+)/(?:\d+|\*)\s*$',final)
    return bool(match and int(match[1])==start and int(match[2])==end-1)


class PrefixSource:
    """Replay the cached prefix, appending verified bounded HTTP byte ranges."""
    def __init__(self,cache,prefetch,limit):
        self.cache=Path(cache);self.prefetch=Path(prefetch);self.prefetch.mkdir(parents=True,exist_ok=True)
        self.limit=limit;self.base=self.cache.stat().st_size if self.cache.exists() else 0
        if self.base>limit:raise ValueError('Cache already exceeds requested limit')
        self.previous=self.cache.open('rb') if self.base else None;self.left=self.base
        self.append=self.cache.open('ab');self.total=self.base;self.current=None;self.current_path=None
        self.pool=ThreadPoolExecutor(max_workers=4);self.processes=set();self.lock=threading.Lock();self.stopping=False
        self.chunk_size=64*1024**2;self.index=0;self.futures={};self.next_progress=self.base+256*1024**2
        for index in range(4):self.submit(index)
    def submit(self,index):
        start=self.base+index*self.chunk_size
        if start<self.limit:self.futures[index]=self.pool.submit(self.download,start,min(start+self.chunk_size,self.limit))
    def download(self,start,end):
        path=self.prefetch/f'{start}-{end}.chunk'
        if path.exists() and path.stat().st_size==end-start:return path
        partial=path.with_suffix('.partial');headers=path.with_suffix('.headers')
        command=['curl','--silent','--show-error','--fail','--location','--retry','4','--retry-all-errors','--retry-delay','2',
            '--connect-timeout','30','--max-time','240','--max-filesize',str(end-start),'--range',f'{start}-{end-1}',
            '--dump-header',str(headers),'--output',str(partial),URL]
        process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        with self.lock:
            self.processes.add(process)
            if self.stopping:process.terminate()
        _,error=process.communicate()
        with self.lock:self.processes.discard(process)
        if process.returncode or not partial.exists() or partial.stat().st_size!=end-start:
            raise OSError(f'Range download failed at {start}: {error.decode(errors="replace")[:200]}')
        if not range_header_ok(headers.read_text(),start,end):raise OSError('Unexpected HTTP range response')
        partial.rename(path);return path
    def read(self,size=-1):
        if size<0:size=131072
        if self.left:
            value=self.previous.read(min(size,self.left));self.left-=len(value);return value
        if self.total>=self.limit:return b''
        if self.current is None:
            self.current_path=self.futures.pop(self.index).result();self.current=self.current_path.open('rb')
        value=self.current.read(size)
        if not value:
            self.current.close();self.current=None;self.current_path.unlink();self.current_path=None
            self.submit(self.index+4);self.index+=1;return self.read(size)
        self.append.write(value);self.append.flush();self.total+=len(value)
        if self.total>=self.next_progress:
            print(f'Compressed cache: {self.total/1024**3:.2f} GiB',flush=True);self.next_progress+=256*1024**2
        return value
    def close(self):
        with self.lock:
            self.stopping=True
            for process in self.processes:
                if process.poll() is None:process.terminate()
        self.pool.shutdown(wait=True,cancel_futures=True)
        if self.current:self.current.close()
        self.append.close()
        if self.previous:self.previous.close()


def acquire(model_directory,label_tables,cache,prefetch,output,cheating=8,legitimate=16,limit_gib=16,purpose="evaluation",cached_only=False):
    bundle=load_model(model_directory)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    labels=metadata_labels(label_tables)
    blocked,blocked_matches,registry_receipts=recorded_exclusions(bundle,model_directory)
    encoded_blocked={float(int(value)) for value in blocked}
    quotas={'1':cheating,'0':legitimate};counts={'1':0,'0':0}
    if min(quotas.values())<0 or sum(quotas.values())<1:raise ValueError('At least one positive label quota required')
    if purpose not in ('evaluation','development'):raise ValueError('Unknown acquisition purpose')
    plan=dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(),role='metadata_only_acquisition',
        source_url=URL,model_sha256=digest(Path(model_directory)/'model.json'),quotas=quotas,
        purpose=purpose,cached_only=cached_only,compressed_cache_limit_bytes=Path(cache).stat().st_size if cached_only else int(limit_gib*1024**3),initial_cache_bytes=Path(cache).stat().st_size,
        label_sources={str(Path(p).resolve()):digest(p) for p in label_tables},
        prior_reservation_receipt_sha256=registry_receipts,excluded_participant_count=len(blocked),
        selection='Archive order; one target/match. Cheating label has priority until its quota is filled. Within label, SHA-256(match+source token) order. Reject inspected/shared participants and nonunique rounded-ID mapping. No features/predictions used.',
        code_sha256=digest(__file__),features_inspected=False)
    write_json(output/'plan.json',plan)
    chosen=[];rejected=[];inventory=[];used=set();seen_matches=set()
    source=PrefixSource(cache,prefetch,plan['compressed_cache_limit_bytes']);status='scanning'
    def receipt():
        value=dict(status=status,cases=chosen,counts=counts,rejected=rejected,inventory=inventory,
            plan_sha256=digest(output/'plan.json'),compressed_cache_bytes=Path(cache).stat().st_size,features_inspected=False)
        temporary=output/'acquisition.tmp';temporary.write_text(json.dumps(value,indent=2)+'\n');temporary.replace(output/'acquisition.json')
    try:
        with zstandard.ZstdDecompressor(max_window_size=1073741824).stream_reader(source,closefd=False) as decoded:
            with tarfile.open(fileobj=decoded,mode='r|') as archive:
                for member in archive:
                    if not member.isfile():continue
                    name=Path(member.name).name;match=name.split('_',1)[0]
                    inventory.append(dict(name=member.name,size=member.size))
                    if match in blocked_matches|seen_matches or not name.endswith('.zip'):continue
                    candidates=[row for row in labels.get(match,[]) if counts[row['isCheater']]<quotas[row['isCheater']]
                        and float(row['steamid']) not in encoded_blocked]
                    if not candidates:continue
                    row=sorted(candidates,key=lambda r:(r['isCheater']!='1',hashlib.sha256((match+r['steamid']).encode()).hexdigest()))[0]
                    seen_matches.add(match)
                    if member.size>1024**3:raise ValueError('Nested ZIP exceeds acquisition size limit')
                    path=output/name;partial=path.with_suffix('.partial')
                    with archive.extractfile(member) as src,partial.open('wb') as dst:shutil.copyfileobj(src,dst)
                    partial.rename(path)
                    with ZipFile(path) as nested:
                        failure=nested.testzip()
                        if failure:raise ValueError(f'Nested ZIP CRC failed: {failure}')
                        demos=[item for item in nested.infolist() if item.filename.endswith('.dem')]
                        if len(demos)!=1 or demos[0].file_size>2*1024**3:raise ValueError('Expected one bounded demo')
                        demo=output/Path(demos[0].filename).name
                        with nested.open(demos[0]) as src,demo.open('xb') as dst:shutil.copyfileobj(src,dst)
                    members=participant_ids(demo)
                    exact=unique_exact_id(row['steamid'],members)
                    overlap=set(members)&(blocked|used)
                    if exact is None or overlap:
                        reason='nonunique_rounded_identity' if exact is None else 'participant_overlap'
                        rejected.append(dict(match_id=match,reason=reason,overlap=sorted(overlap)))
                        print(f'Rejected {match}: {reason}',flush=True);receipt();continue
                    chosen.append(dict(steamid=exact,match_id=match,label='cheating' if row['isCheater']=='1' else 'legitimate',
                        features_inspected=False,demo=str(demo.resolve()),demo_sha256=digest(demo),participants=members,
                        source_label_file=row['source_label_file'],source_label_sha256=row['source_label_sha256'],
                        source_player_id=row['steamid'],archive_path=member.name,zip_sha256=digest(path),
                        identity_method='Unique source float64 encoding among exact full replay participant IDs; no conversion of rounded token to integer',
                        identity_precision='Rounded source ID; unique within replay. Original unrounded label ID unavailable',
                        label_scope='Selected player in match; cheat subtype and activation ticks unspecified'))
                    counts[row['isCheater']]+=1;used.update(members)
                    print(f"Selected {match}: {chosen[-1]['label']}; counts {counts}",flush=True);receipt()
                    if counts==quotas:status='quota_complete';break
                else:status='archive_ended_before_quota'
    except (OSError,tarfile.ReadError,zstandard.ZstdError,ValueError) as exc:
        status='bounded_prefix_exhausted_or_transfer_error';print(f'{type(exc).__name__}: {exc}',flush=True)
    finally:
        source.close();receipt()
    write_json(output/'candidates.json',dict(role='development_candidates' if purpose=='development' else 'evaluation_candidates',features_inspected=False,
        selection=plan['selection'],acquisition_status=status,cases=chosen,
        caveats=['Archive-order convenience sample, not representative population sampling',
                 'Source labels are rounded and match-level; no aimbot activation annotation',
                 'Source archive is a partial cached prefix; nested ZIP CRCs and selected demo hashes verified, not the full multi-part archive checksum']))
    print(f'Acquisition status: {status}; counts {counts}',flush=True)
    return counts


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model_directory',type=Path);parser.add_argument('--label-table',action='append',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True);parser.add_argument('--prefetch',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cheating',type=int,default=8)
    parser.add_argument('--legitimate',type=int,default=16);parser.add_argument('--limit-gib',type=float,default=16)
    parser.add_argument('--purpose',choices=['evaluation','development'],default='evaluation');parser.add_argument('--cached-only',action='store_true')
    args=parser.parse_args(argv)
    acquire(args.model_directory,args.label_table,args.cache,args.prefetch,args.output,args.cheating,args.legitimate,args.limit_gib,args.purpose,args.cached_only)


if __name__=='__main__':main()

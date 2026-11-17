from scripts.acquire_fresh_cases import metadata_labels,range_header_ok,unique_exact_id
import pytest


def test_unique_rounded_mapping_never_invents_an_exact_id():
    ids=['76561199000000001','76561199000000002']
    assert unique_exact_id(str(float(int(ids[0]))),ids) is None
    assert unique_exact_id(str(float(int(ids[0]))),ids[:1])==ids[0]
    assert unique_exact_id('invalid',ids) is None


def test_range_response_must_match_requested_bytes_after_redirects():
    text='HTTP/1.1 302 Found\r\nLocation: elsewhere\r\n\r\nHTTP/2 206 \r\nContent-Range: bytes 100-199/1000\r\n\r\n'
    assert range_header_ok(text,100,200)
    assert not range_header_ok(text,0,100)
    assert not range_header_ok('HTTP/2 200 OK\nContent-Range: bytes 100-199/1000',100,200)


def test_source_predictions_are_not_used_and_conflicting_labels_fail(tmp_path):
    path=tmp_path/'labels.csv';path.write_text('steamid,match_id,isCheater,prediction\n1,m1,0,1\n')
    labels=metadata_labels([path]);assert labels['m1'][0]['isCheater']=='0'
    assert 'prediction' not in labels['m1'][0]
    other=tmp_path/'other.csv';other.write_text('steamid,match_id,isCheater\n1,m1,1\n')
    with pytest.raises(ValueError,match='Conflicting'):
        metadata_labels([path,other])


def test_range_validation_accepts_http2_status_without_reason_phrase():
    assert range_header_ok('HTTP/2 206\r\ncontent-range: bytes 0-63/1000\r\n',0,64)


def test_future_acquisition_excludes_all_registered_participants_without_mutating_model(tmp_path):
    import json
    from aimguard.baseline import digest
    from scripts.acquire_fresh_cases import recorded_exclusions
    model=tmp_path/'model.json';model.write_text('fixture model')
    registry=tmp_path/'reservations';registry.mkdir()
    path=registry/'used.reservation.json'
    path.write_text(json.dumps(dict(model_sha256=digest(model),cases=[dict(participants=['20','21'],match_id='used')])) )
    bundle=dict(excluded_participants=['10','11'],development=[dict(match_id='development')])
    blocked,matches,receipts=recorded_exclusions(bundle,tmp_path)
    assert blocked=={'10','11','20','21'} and matches=={'development','used'}
    assert receipts=={path.name:digest(path)}
    assert bundle['excluded_participants']==['10','11']


def test_acquisition_rejects_registry_for_a_different_model(tmp_path):
    import json
    from scripts.acquire_fresh_cases import recorded_exclusions
    (tmp_path/'model.json').write_text('fixture')
    (tmp_path/'reservations').mkdir()
    (tmp_path/'reservations'/'bad.reservation.json').write_text(json.dumps(dict(model_sha256='wrong',cases=[])))
    with pytest.raises(ValueError,match='registry model mismatch'):
        recorded_exclusions(dict(excluded_participants=[],development=[]),tmp_path)


def test_cached_prefix_source_never_downloads_when_limit_equals_existing_bytes(tmp_path,monkeypatch):
    from scripts.acquire_fresh_cases import PrefixSource
    cache=tmp_path/'cache.zst';cache.write_bytes(b'abc')
    monkeypatch.setattr(PrefixSource,'download',lambda *args:pytest.fail('Cached-only source must not download'))
    source=PrefixSource(cache,tmp_path/'prefetch',3)
    try:
        assert source.read(2)==b'ab' and source.read(2)==b'c' and source.read(2)==b''
    finally:source.close()
    assert cache.read_bytes()==b'abc'


def test_cached_development_acquisition_accepts_legitimate_only_quota(tmp_path,monkeypatch):
    import io,json,tarfile
    from zipfile import ZipFile
    import zstandard
    import scripts.acquire_fresh_cases as module
    model=tmp_path/'model';model.mkdir();(model/'model.json').write_text('fixture')
    labels=tmp_path/'labels.csv';labels.write_text('steamid,match_id,isCheater\n2,fresh,0\n')
    nested=io.BytesIO()
    with ZipFile(nested,'w') as archive:archive.writestr('fresh.dem',b'fixture replay')
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w') as archive:
        member=tarfile.TarInfo('root/fresh_de_map.zip');member.size=len(nested.getvalue());archive.addfile(member,io.BytesIO(nested.getvalue()))
    cache=tmp_path/'cache.zst';cache.write_bytes(zstandard.ZstdCompressor().compress(raw.getvalue()));before=cache.read_bytes()
    monkeypatch.setattr(module,'load_model',lambda _:dict(excluded_participants=['99'],development=[]))
    monkeypatch.setattr(module,'participant_ids',lambda _:['2','3'])
    monkeypatch.setattr(module.PrefixSource,'download',lambda *args:pytest.fail('No network allowed'))
    output=tmp_path/'cohort'
    assert module.acquire(model,[labels],cache,tmp_path/'prefetch',output,0,1,16,'development',True)=={'1':0,'0':1}
    manifest=json.loads((output/'candidates.json').read_text())
    assert manifest['role']=='development_candidates' and manifest['features_inspected'] is False
    assert manifest['cases'][0]['label']=='legitimate'
    assert json.loads((output/'plan.json').read_text())['cached_only'] and cache.read_bytes()==before


def test_range_download_retries_interrupted_transfers_and_validates_response(tmp_path,monkeypatch):
    import threading
    import scripts.acquire_fresh_cases as module
    source=object.__new__(module.PrefixSource)
    source.prefetch=tmp_path;source.processes=set();source.lock=threading.Lock();source.stopping=False
    commands=[]
    class Process:
        returncode=0
        def __init__(self,command,**kwargs):
            commands.append(command)
            Path(command[command.index('--output')+1]).write_bytes(b'abc')
            Path(command[command.index('--dump-header')+1]).write_text('HTTP/2 206\nContent-Range: bytes 0-2/10\n\n')
        def communicate(self):return b'',b''
    from pathlib import Path
    monkeypatch.setattr(module.subprocess,'Popen',Process)
    result=source.download(0,3)
    assert result.read_bytes()==b'abc' and '--retry-all-errors' in commands[0]
    assert commands[0][commands[0].index('--range')+1]=='0-2'

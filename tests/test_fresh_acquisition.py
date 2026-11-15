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

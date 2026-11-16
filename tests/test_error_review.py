import pytest
from aimguard.error_review import outcome


@pytest.mark.parametrize('label,flag,expected',[
    ('cheating',True,'true_positive'),('cheating',False,'false_negative'),
    ('legitimate',True,'false_positive'),('legitimate',False,'true_negative')])
def test_error_categories(label,flag,expected):
    assert outcome(dict(status='scored',label=label,flagged=flag))==expected


def test_abstention_has_no_invented_prediction():
    assert outcome(dict(status='abstained'))=='abstained'


def test_unsafe_case_identifiers_fail_before_creating_output(tmp_path):
    import json
    from aimguard.error_review import build
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps(dict(role='development',cases=[dict(case_id='../escape')])))
    output=tmp_path/'output'
    with pytest.raises(ValueError,match='safe filename'):
        build(manifest,tmp_path,tmp_path,output)
    assert not output.exists()


def test_changed_manifest_rejected_before_review_generation(tmp_path):
    import json
    from aimguard.error_review import build
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps(dict(role='development',cases=[])))
    (tmp_path/'comparison.json').write_text('{}')
    (tmp_path/'protocol.json').write_text(json.dumps(dict(manifest_sha256='wrong')))
    with pytest.raises(ValueError,match='manifest mismatch'):
        build(manifest,tmp_path,tmp_path,tmp_path/'output')
    assert not (tmp_path/'output').exists()

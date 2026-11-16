import json
import pytest
from aimguard.baseline import digest
from scripts.render_measurement_audit import render


def fixture(tmp_path):
    (tmp_path/'plan.json').write_text('{}')
    case=dict(case_id='R1',label='legitimate',frozen_score=.5,windows=0)
    record=dict(summary=case,windows=[],property_availability={'<script>bad()</script>':dict(status='requested_column_omitted')})
    (tmp_path/'R1.json').write_text(json.dumps(record))
    summary=dict(cases=[case],plan_sha256=digest(tmp_path/'plan.json'),case_sha256={'R1':digest(tmp_path/'R1.json')},limitations=[],eye_head_geometry_validated=False,visibility_validated=False)
    (tmp_path/'summary.json').write_text(json.dumps(summary))
    return summary


def test_report_preserves_pending_review_and_escapes_probe_names(tmp_path):
    fixture(tmp_path);render(tmp_path)
    text=(tmp_path/'index.html').read_text()
    assert 'rendered gameplay review is pending' in text
    assert '&lt;script&gt;bad()' in text and '<script>bad()' not in text
    assert json.loads((tmp_path/'review-template.json').read_text())['status']=='pending_rendered_gameplay'


def test_report_rejects_changed_case_before_writing(tmp_path):
    fixture(tmp_path);(tmp_path/'R1.json').write_text('{}')
    with pytest.raises(ValueError,match='case checksum'):render(tmp_path)
    assert not (tmp_path/'index.html').exists()


def test_report_cannot_promote_proxy_to_validated_eye_geometry(tmp_path):
    summary=fixture(tmp_path);summary['eye_head_geometry_validated']=True
    (tmp_path/'summary.json').write_text(json.dumps(summary))
    with pytest.raises(ValueError,match='unvalidated proxy'):render(tmp_path)

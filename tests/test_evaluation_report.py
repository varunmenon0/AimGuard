import json
import pytest
from aimguard.baseline import evaluation_metrics
from scripts.render_tracking_evaluation import render


def fixture(tmp_path):
    rows=[dict(case_id='R1',label='cheating',status='scored',baseline_score=.9,flagged=True),
          dict(case_id='R2',label='legitimate',status='scored',baseline_score=.1,flagged=False),
          dict(case_id='R3',label='cheating',status='abstained',error='<script>bad()</script>')]
    start=dict(model_sha256='model',reserved_manifest_sha256='manifest',threshold=.5)
    result=dict(start,predictions=rows,metrics=evaluation_metrics(rows),caveats=['Fixture limitation'])
    (tmp_path/'start-receipt.json').write_text(json.dumps(start));(tmp_path/'evaluation.json').write_text(json.dumps(result))
    return result


def test_report_keeps_abstentions_intervals_and_escapes_error_text(tmp_path):
    fixture(tmp_path);path=render(tmp_path);text=path.read_text()
    assert '2/3 cases scored; 1 abstained' in text
    assert 'exact 95% interval' in text and '0/1 (0.0%)' in text
    assert '&lt;script&gt;bad()' in text and '<script>bad()' not in text
    assert 'R3' in text and 'Abstained' in text


def test_report_rejects_inconsistent_metrics_and_flags(tmp_path):
    result=fixture(tmp_path);result['metrics']['scored']=3
    (tmp_path/'evaluation.json').write_text(json.dumps(result))
    with pytest.raises(ValueError,match='metrics differ'):render(tmp_path)
    result=fixture(tmp_path);result['predictions'][0]['flagged']=False
    (tmp_path/'evaluation.json').write_text(json.dumps(result))
    with pytest.raises(ValueError,match='frozen cutoff'):render(tmp_path)
    assert not (tmp_path/'evaluation.html').exists()


def test_report_rejects_changed_start_receipt(tmp_path):
    fixture(tmp_path)
    (tmp_path/'start-receipt.json').write_text(json.dumps(dict(model_sha256='other',reserved_manifest_sha256='manifest',threshold=.5)))
    with pytest.raises(ValueError,match='receipts disagree'):render(tmp_path)

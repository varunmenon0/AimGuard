import json
import pytest
from scripts.render_target_tracking import render


def test_tracking_viewer_escapes_embedded_metadata_and_uses_fixed_filenames(tmp_path):
    case=dict(case_id='</script><script>bad()</script>',label='legitimate',windows=0)
    (tmp_path/'summary.json').write_text(json.dumps(dict(cases=[case],limitations=[])))
    (tmp_path/'case_0001.json').write_text(json.dumps(dict(summary=case,windows=[],assumed_tickrate_hz=64)))
    render(tmp_path)
    viewer=(tmp_path/'case_0001.html').read_text()
    assert '</script><script>bad()' not in viewer
    assert r'\u003c/script>' in viewer
    index=(tmp_path/'index.html').read_text()
    assert 'href="case_0001.html"' in index
    assert '&lt;script&gt;bad()' in index


def test_tracking_viewer_rejects_mismatched_summary(tmp_path):
    (tmp_path/'summary.json').write_text(json.dumps(dict(cases=[dict(case_id='A')],limitations=[])))
    (tmp_path/'case_0001.json').write_text(json.dumps(dict(summary=dict(case_id='B'))))
    with pytest.raises(ValueError,match='summary mismatch'):
        render(tmp_path)

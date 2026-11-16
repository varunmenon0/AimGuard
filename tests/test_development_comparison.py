import json

import pytest

from scripts.compare_development import compare


def test_mixed_timing_reports_are_rejected_before_comparison(tmp_path):
    cases=[]
    analysis=tmp_path/'analysis'
    for index,radius in enumerate([.1,.2],1):
        case=dict(case_id=str(index),steamid=str(index),demo_sha256=str(index)*64,
                  label='cheating' if index==1 else 'legitimate')
        cases.append(case)
        directory=analysis/f'job_{index:04d}'
        directory.mkdir(parents=True)
        report=dict(steamid=case['steamid'],source_sha256=case['demo_sha256'],
                    feature_version='0.5.0',assumed_tickrate_hz=64,
                    configuration=dict(weapon_mode='firearms',near_shot_seconds=radius,
                                       pre_seconds=.5,post_seconds=.5,shot_gap_seconds=.5),
                    engagements=[],engagement_count=0,
                    data_quality=dict(non_alive_positive_health_samples=0))
        (directory/'report.json').write_text(json.dumps(report))
    manifest=tmp_path/'cases.json'
    manifest.write_text(json.dumps(dict(role='development',cases=cases)))
    with pytest.raises(ValueError,match='different extraction configurations'):
        compare(manifest,analysis,tmp_path/'output')
    assert not (tmp_path/'output').exists()

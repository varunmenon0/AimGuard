import copy
import numpy as np
import pytest
from aimguard.tracking_models import case_features, window_features, with_abstentions


def window():
    return dict(shot_ticks=[20],nearest_before_first_shot='a',damage_events=[],
        tracks=[dict(opponent_id='a',ticks=list(range(26)),segment_ids=[0]*26,
            signed_error_degrees=[2.]*26,yaw_rate_dps=[5.]*26,bearing_rate_dps=[2.]*26)])


def test_pre_shot_features_ignore_damage_recipients_and_all_post_shot_values():
    value=window();expected,reason=window_features(value,64)
    assert reason is None and expected==[2.,3.]
    value['damage_recipients']=['b'];value['damage_events']=[dict(opponent_id='b',tick=20)]
    value['tracks'].append(copy.deepcopy(value['tracks'][0]));value['tracks'][1]['opponent_id']='b'
    for track in value['tracks']:
        for key in ('signed_error_degrees','yaw_rate_dps','bearing_rate_dps'):
            track[key][20:]=[None]*6
        track['segment_ids'][20:]=[-1]*6
    assert window_features(value,64)[0]==expected


def test_endpoint_and_contiguous_support_are_required_without_gap_bridging():
    value=window();value['tracks'][0]['segment_ids'][14:]=[1]*12
    assert window_features(value,64)[1]=='insufficient_contiguous_pre_shot_intervals'
    value=window();value['tracks'][0]['signed_error_degrees'][19]=None
    assert window_features(value,64)[1]=='invalid_pre_shot_endpoint'
    value=window();value['nearest_before_first_shot']=None
    assert window_features(value,64)[1]=='no_pre_shot_candidate'


def test_case_medians_use_windows_and_minimum_coverage_is_explicit():
    assert case_features([window()]*4,64)[0] is None
    values,counts=case_features([window()]*5,64)
    assert values==[2.,3.] and counts['eligible_windows']==5


def test_rate_at_first_included_sample_does_not_reach_outside_pre_period():
    value=window();value['tracks'][0]['yaw_rate_dps'][8]=99999
    assert window_features(value,64)[0]==[2.,3.]


def test_abstentions_keep_denominators_and_ineligible_cases_out_of_training():
    result=with_abstentions([None,[1.],[2.],[3.],[4.],[5.]],[0,1,0,1,0,1],[0,0,1,2,3,4],list('abcdef'),'log1p')
    assert result['metrics']['abstentions']==1
    assert result['metrics']['scored']==5
    assert result['predictions'][0]['status']=='abstained'
    assert all('a' not in fold['train_case_ids'] for fold in result['folds'])
    assert sorted(row['case_id'] for row in result['predictions'])==list('abcdef')


def test_insufficient_groups_abstain_instead_of_fitting_full_pool():
    result=with_abstentions([[1.],[2.],None],[0,1,0],[0,0,1],list('abc'),'log1p')
    assert result['metrics']['abstentions']==3
    assert result['folds']==[]


def test_malformed_candidate_and_supporting_rates_fail_explicitly():
    value=window();value['tracks'].append(copy.deepcopy(value['tracks'][0]))
    with pytest.raises(ValueError,match='exactly one'):
        window_features(value,64)
    value=window();value['tracks'][0]['yaw_rate_dps'][15]=float('nan')
    with pytest.raises(ValueError,match='supporting'):
        window_features(value,64)


def test_comparison_records_fixed_protocol_but_never_fits_mismatched_tracking_inputs(tmp_path,monkeypatch):
    import json
    import aimguard.tracking_models as module
    manifest=tmp_path/'manifest.json';manifest.write_text('{}')
    tracking=tmp_path/'tracking';tracking.mkdir()
    (tracking/'summary.json').write_text(json.dumps(dict(manifest_sha256='wrong',cases=[])))
    monkeypatch.setattr(module,'load_development',lambda *args:([],{},[],[]))
    monkeypatch.setattr(module,'grouped_predictions',lambda *args:pytest.fail('Must not fit mismatched inputs'))
    output=tmp_path/'comparison'
    with pytest.raises(ValueError,match='Tracking manifest mismatch'):
        module.compare(manifest,tmp_path,tracking,output)
    protocol=json.loads((output/'protocol.json').read_text())
    assert protocol['threshold']==.5 and protocol['minimum_contiguous_intervals']==8
    assert protocol['minimum_eligible_windows']==5 and protocol['pre_seconds']==.2
    assert not (output/'comparison.json').exists()

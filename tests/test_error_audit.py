import numpy as np
import pytest
from aimguard.error_audit import (low_false_flag_predictions, precision_at_prevalence,
                                  negative_sample_requirement, explain_case, temporal_context)


def sample():
    return [[i, i+1, i+2, i+3] for i in range(1, 9)], [0, 1]*4, [0, 0, 1, 2, 3, 4, 5, 6], list('abcdefgh')


def test_outer_group_features_and_labels_cannot_enter_inner_calibration_or_refit():
    values, labels, groups, ids = sample()
    before = low_false_flag_predictions(values, labels, groups, ids)
    changed_values = [[1e8]*4, [1e9]*4, *values[2:]]
    changed_labels = [1, 0, *labels[2:]]
    after = low_false_flag_predictions(changed_values, changed_labels, groups, ids)
    first = next(f for f in before['folds'] if f['held_out_case_ids'] == ['a', 'b'])
    second = next(f for f in after['folds'] if f['held_out_case_ids'] == ['a', 'b'])
    assert first == second
    for fold in before['folds']:
        held_out = set(fold['held_out_case_ids']); training = set(fold['train_case_ids'])
        assert not training & held_out
        for inner in fold['inner_calibration']['folds']:
            assert not set(inner['train_case_ids']) & set(inner['held_out_case_ids'])
            assert (set(inner['train_case_ids']) | set(inner['held_out_case_ids'])) <= training
            assert not held_out & (set(inner['train_case_ids']) | set(inner['held_out_case_ids']))


def test_cutoff_is_exact_training_inner_negative_max_and_decisions_reconstruct():
    values, labels, groups, ids = sample(); result = low_false_flag_predictions(values, labels, groups, ids)
    from scipy.special import expit
    for row in result['predictions']:
        fold = next(f for f in result['folds'] if f['fold'] == row['fold'])
        negatives = [r['baseline_score'] for r in fold['inner_calibration']['predictions'] if r['label']=='legitimate']
        assert fold['cutoff'] == max(negatives)
        value = np.log1p(values[ids.index(row['case_id'])])
        score = expit(fold['intercept'] + np.dot((value-fold['scaler_mean'])/fold['scaler_scale'], fold['coefficients']))
        assert score == pytest.approx(row['baseline_score'])
        assert row['flagged'] == (score > max(negatives))
    assert result['metrics']['diagnostic_only']
    assert 'exact_95_interval' not in result['metrics']['false_positive_rate']


def test_incomplete_inner_class_coverage_abstains_instead_of_using_training_scores():
    result = low_false_flag_predictions([[i]*4 for i in range(6)], [0, 0, 0, 0, 1, 1], [0, 1, 2, 3, 4, 4], list('abcdef'))
    assert result['metrics']['abstentions'] == 6
    assert all(r['status']=='abstained' for r in result['predictions'])


def test_zero_margin_ties_do_not_pass_conservative_cutoff():
    result = low_false_flag_predictions([[1]*4]*8, [0, 1]*4, range(8), list('abcdefgh'))
    assert not any(r.get('flagged') for r in result['predictions'])


def test_prevalence_precision_and_independent_zero_error_sample_planning():
    assert precision_at_prevalence(.8125, .1, .01) == pytest.approx(.0758459743)
    assert precision_at_prevalence(.8125, .001, .01) == pytest.approx(.8913878223)
    assert precision_at_prevalence(0, 0, .01) is None
    assert negative_sample_requirement(.01) == 299
    assert negative_sample_requirement(.001) == 2995
    with pytest.raises(ValueError): precision_at_prevalence(1, -1, .01)
    with pytest.raises(ValueError): negative_sample_requirement(0)


def test_explanations_use_fold_scaling_and_training_neighbours_only():
    cases = [dict(case_id=i, label='legitimate') for i in 'abc']
    fold = dict(train_case_ids=['b', 'c'], scaler_mean=[0]*4, scaler_scale=[1]*4,
                coefficients=[1, -1, 2, -2], intercept=.1)
    result = explain_case([[1]*4, [2]*4, [3]*4], 0, cases, fold)
    assert [r['case_id'] for r in result['nearest_training_cases']]==['b', 'c']
    assert result['contributions'] == pytest.approx(np.log(2)*np.array([1, -1, 2, -2]))
    assert result['largest_positive_feature']==2


@pytest.mark.parametrize('bad', ['negative', 'labels', 'groups', 'duplicate'])
def test_invalid_cases_fail_before_any_fit(bad):
    values, labels, groups, ids = sample()
    if bad=='negative': values[0][0]=-1
    elif bad=='labels': labels[0]=2
    elif bad=='groups': groups=[0]*8
    else: ids[0]=ids[1]
    with pytest.raises(ValueError): low_false_flag_predictions(values, labels, groups, ids)


def test_temporal_context_refuses_misaligned_windows_and_marks_short_halves_unavailable():
    window = dict(engagement_id=0, shot_ticks=[20], weapon='ak47', round_id=1)
    track = dict(window, nearest_before_first_shot=None, tracks=[])
    report = dict(engagements=[window], assumed_tickrate_hz=64)
    result = temporal_context(report, dict(windows=[track]), {})
    assert result['windows']==1 and result['rounds']==1
    assert all(h['score'] is None for h in result['chronological_halves'])
    with pytest.raises(ValueError, match='identity'): temporal_context(report, dict(windows=[dict(track, weapon='awp')]), {})


def test_explanation_rejects_fold_that_trained_on_held_out_case():
    cases = [dict(case_id=i, label='legitimate') for i in 'abc']
    fold = dict(train_case_ids=['a', 'c'], scaler_mean=[0]*4, scaler_scale=[1]*4,
                coefficients=[1]*4, intercept=0)
    with pytest.raises(ValueError, match='held-out fold'):
        explain_case([[1]*4, [2]*4, [3]*4], 0, cases, fold)


def test_saved_error_report_escapes_labels_and_rejects_changed_receipts(tmp_path):
    import json
    from aimguard.baseline import digest
    from scripts.render_error_audit import render
    def write(name, value): (tmp_path/name).write_text(json.dumps(value))
    write('protocol.json', {})
    case_id = '<script>bad</script>'
    write('inputs.json', dict(sources=[dict(case_id=case_id, review=str(tmp_path/'review.html'))]))
    write('audit.json', dict(protocol_sha256=digest(tmp_path/'protocol.json'), inputs_sha256=digest(tmp_path/'inputs.json'),
        explanations=[dict(case_id=case_id, label='<img>', score=.75, error=True)]))
    (tmp_path/'report.md').write_text('<script>report</script>')
    path = render(tmp_path); content = path.read_text()
    assert '<script>' not in content and '&lt;script&gt;' in content and '&lt;img&gt;' in content
    write('inputs.json', {})
    with pytest.raises(ValueError, match='receipt mismatch'): render(tmp_path)

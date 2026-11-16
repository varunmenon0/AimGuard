import numpy as np
import pytest
from aimguard.nonlinear_models import grouped_rbf


def test_held_out_group_never_changes_training_scaler_kernel_or_support_vectors():
    values = [[1, 2, 3, 4], [2, 3, 4, 5], [3, 4, 5, 6], [4, 5, 6, 7], [5, 6, 7, 8], [6, 7, 8, 9]]
    labels = [0, 1, 0, 1, 0, 1]; groups = [0, 0, 1, 2, 3, 4]; ids = list('abcdef')
    before = grouped_rbf(values, labels, groups, ids)
    altered = [[1e8]*4, [1e9]*4, *values[2:]]
    after = grouped_rbf(altered, labels, groups, ids)
    first = next(f for f in before['folds'] if f['held_out_case_ids'] == ['a', 'b'])
    second = next(f for f in after['folds'] if f['held_out_case_ids'] == ['a', 'b'])
    assert first == second
    assert first['scaler_mean'] == pytest.approx(np.log1p(values[2:]).mean(axis=0))
    assert first['gamma'] == pytest.approx(.25)
    for fold in before['folds']:
        assert not set(fold['train_case_ids']) & set(fold['held_out_case_ids'])
        assert set(fold['support_case_ids']) <= set(fold['train_case_ids'])


def test_recorded_support_vectors_reproduce_each_decision_margin():
    values = np.array([[1, 4, 7, 2], [3, 1, 2, 8], [4, 8, 2, 1], [2, 3, 9, 7], [7, 6, 1, 3], [8, 1, 6, 2]])
    ids = list('abcdef'); result = grouped_rbf(values, [0, 1, 0, 1, 0, 1], range(6), ids)
    for row in result['predictions']:
        fold = next(f for f in result['folds'] if f['fold'] == row['fold'])
        mean, scale = np.array(fold['scaler_mean']), np.array(fold['scaler_scale'])
        test = (np.log1p(values[ids.index(row['case_id'])]) - mean) / scale
        support = (np.log1p(values[[ids.index(i) for i in fold['support_case_ids']]]) - mean) / scale
        kernels = np.exp(-fold['gamma'] * ((support-test)**2).sum(axis=1))
        margin = float(kernels @ fold['dual_coefficients'] + fold['intercept'])
        assert row['decision_margin'] == pytest.approx(margin)
        assert row['flagged'] == (margin >= 0)
        assert 'baseline_score' not in row
    assert 'exact_95_interval' not in result['metrics']['false_positive_rate']


def test_missing_coverage_abstains_and_is_excluded_from_training():
    result = grouped_rbf([None, [1]*4, [2]*4, [3]*4, [4]*4], [0, 0, 1, 0, 1], range(5), list('abcde'))
    assert result['predictions'][0]['status'] == 'abstained'
    assert result['metrics']['abstentions'] == 1
    assert all('a' not in f['train_case_ids'] for f in result['folds'])


def test_single_training_class_and_insufficient_groups_abstain_explicitly():
    result = grouped_rbf([[1]*4, [2]*4, [3]*4], [0, 0, 1], [0, 0, 1], list('abc'))
    assert result['metrics']['abstentions'] == 3
    result = grouped_rbf([[1]*4, None], [0, 1], [0, 1], ['a', 'b'])
    assert result['metrics']['abstentions'] == 2
    assert result['folds'] == []


def test_constant_training_values_have_finite_margins_and_defined_gamma():
    result = grouped_rbf([[1]*4]*6, [0, 1]*3, range(6), list('abcdef'))
    assert all(f['gamma'] == 1 for f in result['folds'])
    assert all(np.isfinite(row['decision_margin']) for row in result['predictions'])


@pytest.mark.parametrize('values,labels,groups,ids', [
    ([[1]*4]*2, [0, 2], [0, 1], ['a', 'b']),
    ([[1]*4]*2, [0, 1], [0, 1], ['a', 'a']),
    ([[1]*4]*2, [0, 1], [0], ['a', 'b']),
    ([[1, 2, 3], [2, 3, 4]], [0, 1], [0, 1], ['a', 'b']),
    ([[-1]*4, [1]*4], [0, 1], [0, 1], ['a', 'b']),
    ([[float('nan')]*4, [1]*4], [0, 1], [0, 1], ['a', 'b']),
])
def test_invalid_inputs_fail_instead_of_silent_prediction(values, labels, groups, ids):
    with pytest.raises(ValueError): grouped_rbf(values, labels, groups, ids)


@pytest.mark.parametrize('corruption', ['role', 'checksum', 'groups'])
def test_comparison_rejects_uninspected_tampered_or_repeated_group_sources(tmp_path, corruption):
    import json
    from aimguard.baseline import digest
    from aimguard.nonlinear_models import compare
    from aimguard.tracking_models import TRACKING_RECIPES
    pool = tmp_path/'pool'; pool.mkdir(); baseline = tmp_path/'baseline'; baseline.mkdir()
    def write(path, value): path.write_text(json.dumps(value))
    manifest = dict(role='development', features_inspected=True,
                    cases=[dict(case_id='a', label='legitimate'), dict(case_id='b', label='cheating')])
    if corruption == 'role': manifest['features_inspected'] = False
    write(pool/'manifest.json', manifest)
    groups = {'0':['a'], '1':['b']}
    if corruption == 'groups': groups = {'0':['a'], '1':['a', 'b']}
    write(pool/'pool-receipt.json', dict(manifest_sha256=digest(pool/'manifest.json'), groups=groups))
    write(baseline/'protocol.json', dict(manifest_sha256=digest(pool/'manifest.json'), recipes=TRACKING_RECIPES,
        threshold=.5, hyperparameters=dict(C=1, class_weight='balanced', solver='lbfgs', max_iter=1000, random_state=0)))
    write(baseline/'inputs.json', dict(groups=groups))
    write(baseline/'comparison.json', dict(protocol_sha256=digest(baseline/'protocol.json'), inputs_sha256=digest(baseline/'inputs.json')))
    if corruption == 'checksum': write(baseline/'inputs.json', dict(groups={}, changed=True))
    with pytest.raises(ValueError, match='receipt mismatch|group membership mismatch'):
        compare(pool, baseline, tmp_path/'output')
    assert not (tmp_path/'output').exists()

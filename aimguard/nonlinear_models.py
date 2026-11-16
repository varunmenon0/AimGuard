"""Fixed nonlinear development comparison; never a replacement frozen detector."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from aimguard.baseline import digest, evaluation_metrics, report_features, write_json
from aimguard.tracking_models import case_features, TRACKING_RECIPES

PARAMETERS = dict(kernel='rbf', C=1., gamma='scale', class_weight='balanced')


def grouped_rbf(values, labels, groups, case_ids):
    """Case rows only; kernel width, scaler and support vectors use training groups."""
    labels, groups = np.asarray(labels), np.asarray(groups)
    if (len(values) != len(labels) or len(groups) != len(labels) or len(case_ids) != len(labels)
            or len(set(case_ids)) != len(case_ids)):
        raise ValueError('Aligned, unique case identities required')
    if labels.ndim != 1 or groups.ndim != 1 or not set(labels).issubset({0, 1}):
        raise ValueError('Binary labels and one-dimensional groups required')
    valid = [i for i, value in enumerate(values) if value is not None]
    predictions = [dict(case_id=case_ids[i], label='cheating' if labels[i] else 'legitimate',
                        status='abstained', error='Insufficient eligible pre-shot windows')
                   for i, value in enumerate(values) if value is None]
    matrix = np.asarray([values[i] for i in valid], dtype=float)
    if valid and (matrix.ndim != 2 or matrix.shape[1] != 4 or not np.isfinite(matrix).all() or (matrix < 0).any()):
        raise ValueError('Four finite nonnegative measurements required')
    folds = []
    if len(set(groups[valid])) < 2:
        predictions.extend(dict(case_id=case_ids[i], label='cheating' if labels[i] else 'legitimate',
                                status='abstained', error='Insufficient independent eligible groups') for i in valid)
    else:
        prepared = np.log1p(matrix)
        for number, (train, test) in enumerate(LeaveOneGroupOut().split(prepared, labels[valid], groups[valid]), 1):
            train_ids = [valid[i] for i in train]; test_ids = [valid[i] for i in test]
            record = dict(fold=number, train_case_ids=[case_ids[i] for i in train_ids],
                          held_out_case_ids=[case_ids[i] for i in test_ids])
            if len(set(labels[train_ids])) < 2:
                record['status'] = 'abstained_single_training_class'
                predictions.extend(dict(case_id=case_ids[i], label='cheating' if labels[i] else 'legitimate',
                                        fold=number, status='abstained', error='Training fold has one class') for i in test_ids)
            else:
                scaler = StandardScaler().fit(prepared[train])
                training = scaler.transform(prepared[train])
                variance = float(training.var())
                gamma = 1. / (training.shape[1] * variance) if variance else 1.
                model = SVC(**dict(PARAMETERS, gamma=gamma)).fit(training, labels[train_ids])
                margins = model.decision_function(scaler.transform(prepared[test]))
                record.update(status='scored', scaler_mean=scaler.mean_.tolist(), scaler_scale=scaler.scale_.tolist(),
                              gamma=gamma, support_case_ids=[case_ids[train_ids[i]] for i in model.support_],
                              dual_coefficients=model.dual_coef_[0].tolist(), intercept=float(model.intercept_[0]))
                predictions.extend(dict(case_id=case_ids[i], label='cheating' if labels[i] else 'legitimate',
                                        fold=number, status='scored', decision_margin=float(margin), flagged=bool(margin >= 0))
                                   for i, margin in zip(test_ids, margins))
            folds.append(record)
    order = {case_id: i for i, case_id in enumerate(case_ids)}
    predictions.sort(key=lambda row: order[row['case_id']])
    metrics = evaluation_metrics(predictions)
    for name in ('detection_rate', 'false_positive_rate', 'precision', 'accuracy'):
        metrics[name].pop('exact_95_interval', None)
    metrics['diagnostic_only'] = True
    return dict(predictions=predictions, folds=folds, metrics=metrics)


def compare(pool, baseline_directory, output):
    pool, baseline_directory, output = map(Path, (pool, baseline_directory, output))
    manifest = json.loads((pool/'manifest.json').read_text())
    receipt = json.loads((pool/'pool-receipt.json').read_text())
    protocol = json.loads((baseline_directory/'protocol.json').read_text())
    inputs = json.loads((baseline_directory/'inputs.json').read_text())
    baseline = json.loads((baseline_directory/'comparison.json').read_text())
    if (manifest.get('role') != 'development' or manifest.get('features_inspected') is not True
            or receipt['manifest_sha256'] != digest(pool/'manifest.json')
            or protocol['manifest_sha256'] != digest(pool/'manifest.json')
            or baseline['protocol_sha256'] != digest(baseline_directory/'protocol.json')
            or baseline['inputs_sha256'] != digest(baseline_directory/'inputs.json')
            or inputs['groups'] != receipt['groups']
            or protocol['recipes']['speed_and_tracking'] != TRACKING_RECIPES['speed_and_tracking']
            or protocol['threshold'] != .5
            or protocol['hyperparameters'] != dict(C=1, class_weight='balanced', solver='lbfgs', max_iter=1000, random_state=0)):
        raise ValueError('Inspected development pool/baseline receipt mismatch')
    cases = manifest['cases']; ids = [case['case_id'] for case in cases]
    if len(set(ids)) != len(ids) or any(case['label'] not in ('cheating', 'legitimate') for case in cases):
        raise ValueError('Unique cases and known labels required')
    expected_groups = receipt['groups']
    membership = [case_id for members in expected_groups.values() for case_id in members]
    if len(membership) != len(set(membership)) or set(membership) != set(ids):
        raise ValueError('Full-participant group membership mismatch')
    group_by_case = {case_id: int(group) for group, members in expected_groups.items() for case_id in members}
    groups = np.array([group_by_case[case_id] for case_id in ids])
    if not all(len(value) == len(cases) for value in (receipt['cases'], inputs['cases'], inputs['tracking'])):
        raise ValueError('Source case counts mismatch')
    copied = baseline['models']['speed_and_tracking']
    if (len(copied['predictions']) != len(cases) or
            {row['case_id']: row['label'] for row in copied['predictions']} != {case['case_id']: case['label'] for case in cases}):
        raise ValueError('Baseline case labels/coverage mismatch')
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'protocol.json', dict(role='exploratory_development', recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        parameters=PARAMETERS, threshold=0., transform='log1p', features=TRACKING_RECIPES['speed_and_tracking']['features'],
        gamma='1/(feature count * training-scaled variance), or 1 for constant training data',
        manifest_sha256=digest(pool/'manifest.json'), baseline_sha256=digest(baseline_directory/'comparison.json'),
        code_sha256={name:digest(Path(__file__).with_name(name)) for name in
                     ('nonlinear_models.py', 'tracking_models.py', 'baseline.py', 'development_models.py')},
        dependencies={name:importlib.metadata.version(name) for name in ('numpy', 'scipy', 'scikit-learn')},
        note='One fixed nonlinear recipe; no parameter, threshold or feature search. Decision margins are not probabilities.'))
    values = []; provenance = []
    for index, case in enumerate(cases, 1):
        directory = pool/'analysis'/f'job_{index:04d}'
        path = pool/'tracking'/f'case_{index:04d}.json'
        expected, original, old_tracking = receipt['cases'][index-1], inputs['cases'][index-1], inputs['tracking'][index-1]
        record = json.loads(path.read_text()); report = json.loads((directory/'report.json').read_text())
        if (any(row['case_id'] != case['case_id'] for row in (expected, original, old_tracking, record['summary']))
                or expected['tracking_sha256'] != digest(path) or old_tracking['tracking_sha256'] != digest(path)
                or expected['report_sha256'] != digest(directory/'report.json')
                or original['report_sha256'] != digest(directory/'report.json')
                or report['source_sha256'] != case['demo_sha256'] or record['demo_sha256'] != case['demo_sha256']
                or record['summary']['label'] != case['label'] or report['steamid'] != case['steamid']
                or record['assumed_tickrate_hz'] != report['assumed_tickrate_hz']):
            raise ValueError('Source checksum/identity mismatch')
        for name in ('report.json', 'telemetry.csv', 'events.json'):
            if record['input_sha256'][name] != digest(directory/name):
                raise ValueError('Tracking input checksum mismatch')
        speed, _ = report_features(report)
        tracking, coverage = case_features(record['windows'], record['assumed_tickrate_hz'])
        if tracking != old_tracking['features']:
            raise ValueError('Tracking feature reproduction mismatch')
        value = None if tracking is None else [*speed, *tracking]
        values.append(value)
        provenance.append(dict(case_id=case['case_id'], features=value, report_sha256=digest(directory/'report.json'),
                               tracking_sha256=digest(path), **coverage))
    write_json(output/'inputs.json', dict(cases=provenance, groups=expected_groups))
    models = dict(linear_speed_and_tracking=copied,
                  rbf_speed_and_tracking=grouped_rbf(values, [int(c['label']=='cheating') for c in cases], groups, ids))
    result = dict(cases=len(cases), participant_groups=len(set(groups)), models=models,
                  protocol_sha256=digest(output/'protocol.json'), inputs_sha256=digest(output/'inputs.json'),
                  interpretation='Inspected development diagnostics only; no fresh accuracy or detector replacement claim.')
    write_json(output/'comparison.json', result)
    lines = ['# Fixed nonlinear development comparison', '',
             'Whole participant groups held out; training-only scaling and kernel width. Margins are not probabilities.', '',
             '| Recipe | TP | FN | FP | TN | Abstentions |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name, model in models.items():
        c = model['metrics']['confusion']
        lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {model['metrics']['abstentions']} |")
    lines += ['', result['interpretation'], 'No model is fitted on the full pool or frozen. Historical evaluation is unchanged.', '',
              '## Errors and decision changes', '',
              '| Case | Source label | Linear flag | RBF flag | RBF margin | Local review |',
              '| --- | --- | --- | --- | ---: | --- |']
    linear = {row['case_id']: row for row in copied['predictions']}
    for index, row in enumerate(models['rbf_speed_and_tracking']['predictions'], 1):
        old = linear[row['case_id']]
        if row['status'] != 'scored' or old['status'] != 'scored':
            lines.append(f"| {row['case_id']} | {row['label']} | {old['status']} | {row['status']} | — | — |")
        elif row['flagged'] != (row['label'] == 'cheating') or old['flagged'] != (row['label'] == 'cheating'):
            review = (pool/'analysis'/f'job_{index:04d}'/'review.html').resolve().as_uri()
            lines.append(f"| {row['case_id']} | {row['label']} | {old['flagged']} | {row['flagged']} | {row['decision_margin']:.4f} | [Trajectories]({review}) |")
    lines += ['', 'Source labels do not locate aimbot activation. Trajectories require human interpretation; geometry and visibility remain unverified.', '']
    (output/'report.md').write_text('\n'.join(lines)); print('\n'.join(lines), flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pool', type=Path); parser.add_argument('baseline_directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv); compare(args.pool, args.baseline_directory, args.output)


if __name__ == '__main__':
    main()

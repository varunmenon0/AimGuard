"""Explain grouped errors and test a training-only low-false-flag operating policy."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.preprocessing import StandardScaler

from aimguard.baseline import digest, evaluation_metrics, report_features, write_json
from aimguard.development_models import grouped_predictions
from aimguard.tracking_models import TRACKING_RECIPES, case_features

PARAMETERS = dict(C=1., class_weight='balanced', solver='lbfgs', max_iter=1000, random_state=0)


def metrics(rows):
    result = evaluation_metrics(rows)
    for name in ('detection_rate', 'false_positive_rate', 'precision', 'accuracy'):
        result[name].pop('exact_95_interval', None)
    result['diagnostic_only'] = True
    return result


def low_false_flag_predictions(values, labels, groups, ids):
    """Outer test labels never calibrate thresholds; inner folds keep groups whole."""
    values = np.asarray(values, dtype=float); labels = np.asarray(labels); groups = np.asarray(groups)
    if (values.ndim != 2 or values.shape[1] != 4 or not np.isfinite(values).all() or (values < 0).any()
            or labels.ndim != 1 or groups.ndim != 1 or not set(labels).issubset({0, 1})
            or len(values) != len(labels) or len(groups) != len(labels) or len(ids) != len(labels)
            or len(set(ids)) != len(ids) or len(set(groups)) < 3):
        raise ValueError('Need aligned finite four-feature cases, binary labels and three independent groups')
    predictions = []; folds = []; prepared = np.log1p(values)
    for number, (train, test) in enumerate(LeaveOneGroupOut().split(values, labels, groups), 1):
        train_ids = [ids[i] for i in train]
        record = dict(fold=number, train_case_ids=train_ids, held_out_case_ids=[ids[i] for i in test])
        error = None
        if len(set(labels[train])) < 2 or len(set(groups[train])) < 2:
            error = 'Insufficient training classes/groups for inner calibration'
        else:
            inner = grouped_predictions(values[train], labels[train], groups[train], train_ids, 'log1p')
            record['inner_calibration'] = inner
            negatives = [row for row in inner['predictions'] if row['label'] == 'legitimate']
            if not negatives or any(row['status'] != 'scored' for row in inner['predictions']):
                error = 'Incomplete inner out-of-group calibration; abstain rather than substitute training scores'
        if error:
            record.update(status='abstained', error=error)
            predictions.extend(dict(case_id=ids[i], label='cheating' if labels[i] else 'legitimate', fold=number,
                                    status='abstained', error=error) for i in test)
        else:
            cutoff = max(row['baseline_score'] for row in negatives)
            scaler = StandardScaler().fit(prepared[train])
            model = LogisticRegression(**PARAMETERS).fit(scaler.transform(prepared[train]), labels[train])
            scores = model.predict_proba(scaler.transform(prepared[test]))[:, 1]
            record.update(status='scored', cutoff=cutoff, comparison='strictly_greater_than',
                          calibration_legitimate_cases=len(negatives),
                          scaler_mean=scaler.mean_.tolist(), scaler_scale=scaler.scale_.tolist(),
                          coefficients=model.coef_[0].tolist(), intercept=float(model.intercept_[0]))
            predictions.extend(dict(case_id=ids[i], label='cheating' if labels[i] else 'legitimate', fold=number,
                                    status='scored', baseline_score=float(score), cutoff=cutoff, flagged=bool(score > cutoff))
                               for i, score in zip(test, scores))
        folds.append(record)
    order = {case_id: i for i, case_id in enumerate(ids)}
    predictions.sort(key=lambda row: order[row['case_id']])
    return dict(predictions=predictions, folds=folds, metrics=metrics(predictions))


def precision_at_prevalence(recall, false_positive_rate, prevalence):
    if not all(np.isfinite(x) and 0 <= x <= 1 for x in (recall, false_positive_rate, prevalence)):
        raise ValueError('Rates must be finite and between zero and one')
    true_flags = recall * prevalence
    all_flags = true_flags + false_positive_rate * (1-prevalence)
    return true_flags / all_flags if all_flags else None


def negative_sample_requirement(target_rate, confidence=.95):
    if not 0 < target_rate < 1 or not 0 < confidence < 1:
        raise ValueError('Target and confidence must lie inside (0,1)')
    return int(np.ceil(np.log1p(-confidence) / np.log1p(-target_rate)))


def explain_case(values, index, cases, fold):
    prepared = np.log1p(np.asarray(values, dtype=float))
    scale = np.asarray(fold['scaler_scale']); mean = np.asarray(fold['scaler_mean'])
    coefficients = np.asarray(fold['coefficients'])
    parts = coefficients * ((prepared[index]-mean)/scale)
    ids = [case['case_id'] for case in cases]; train = [ids.index(case_id) for case_id in fold['train_case_ids']]
    if index in train: raise ValueError('Explanation must use the case held-out fold')
    distance = np.linalg.norm((prepared[train]-prepared[index])/scale, axis=1)
    neighbours = [dict(case_id=ids[train[k]], label=cases[train[k]]['label'], distance=float(distance[k]))
                  for k in np.argsort(distance, kind='stable')[:3]]
    return dict(feature_values=list(map(float, values[index])), contributions=parts.tolist(), intercept=fold['intercept'],
                score=float(expit(fold['intercept']+parts.sum())), nearest_training_cases=neighbours,
                largest_positive_feature=int(np.argmax(parts)) if np.max(parts) > 0 else None)


def temporal_context(report, tracking, fold):
    """Descriptive chronological halves; never independent training cases."""
    windows = report['engagements']; tracks = tracking['windows']
    if len(windows) != len(tracks): raise ValueError('Window count mismatch')
    for published, track in zip(windows, tracks):
        if any(published[k] != track[k] for k in ('engagement_id', 'shot_ticks', 'weapon', 'round_id')):
            raise ValueError('Window identity mismatch')
    first_ticks = [w['shot_ticks'][0] for w in windows]
    if first_ticks != sorted(first_ticks): raise ValueError('Expected chronological windows')
    split = len(windows)//2; halves = []
    for start, stop in ((0, split), (split, len(windows))):
        selected = dict(report, engagements=windows[start:stop])
        feature, counts = case_features(tracks[start:stop], report['assumed_tickrate_hz'])
        row = dict(windows=stop-start, **counts)
        if feature is None or stop == start: row.update(score=None, features=None)
        else:
            speed, _ = report_features(selected); value = [*speed, *feature]
            parts = np.asarray(fold['coefficients'])*((np.log1p(value)-fold['scaler_mean'])/fold['scaler_scale'])
            row.update(score=float(expit(fold['intercept']+parts.sum())), features=value)
        halves.append(row)
    return dict(windows=len(windows), rounds=len({w['round_id'] for w in windows}),
                weapons=dict(Counter(w['weapon'] for w in windows)), chronological_halves=halves,
                note='Same held-out case fold applied descriptively to half-match medians; not new independent predictions or evidence of activation.')


def analyze(pool, baseline_directory, output):
    pool, baseline_directory, output = map(Path, (pool, baseline_directory, output))
    manifest = json.loads((pool/'manifest.json').read_text()); receipt = json.loads((pool/'pool-receipt.json').read_text())
    protocol = json.loads((baseline_directory/'protocol.json').read_text()); inputs = json.loads((baseline_directory/'inputs.json').read_text())
    baseline = json.loads((baseline_directory/'comparison.json').read_text())
    if (manifest.get('role') != 'development' or manifest.get('features_inspected') is not True
            or receipt['manifest_sha256'] != digest(pool/'manifest.json') or protocol['manifest_sha256'] != digest(pool/'manifest.json')
            or baseline['protocol_sha256'] != digest(baseline_directory/'protocol.json')
            or baseline['inputs_sha256'] != digest(baseline_directory/'inputs.json') or receipt['groups'] != inputs['groups']
            or protocol['recipes']['speed_and_tracking'] != TRACKING_RECIPES['speed_and_tracking']
            or protocol['threshold'] != .5 or protocol['hyperparameters'] != PARAMETERS):
        raise ValueError('Inspected pool/baseline receipt mismatch')
    cases = manifest['cases']; ids = [case['case_id'] for case in cases]
    membership = [case_id for members in receipt['groups'].values() for case_id in members]
    if len(set(ids)) != len(ids) or len(membership) != len(set(membership)) or set(membership) != set(ids):
        raise ValueError('Duplicate/missing group identities')
    if any(c['label'] not in ('cheating', 'legitimate') for c in cases): raise ValueError('Unknown label')
    groups_by_case = {case_id: int(group) for group, members in receipt['groups'].items() for case_id in members}
    groups = [groups_by_case[case_id] for case_id in ids]; labels = [int(c['label']=='cheating') for c in cases]
    original = baseline['models']['speed_and_tracking']
    if len(original['predictions']) != len(cases) or any(len(rows) != len(cases) for rows in (receipt['cases'], inputs['cases'], inputs['tracking'])):
        raise ValueError('Source case count mismatch')
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/'protocol.json', dict(role='post_feedback_development', recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        manifest_sha256=digest(pool/'manifest.json'), baseline_sha256=digest(baseline_directory/'comparison.json'),
        code_sha256=digest(__file__), hyperparameters=PARAMETERS,
        calibration='For each outer training pool, inner full-participant LOGO scores; cutoff=max legitimate score; flag strictly above cutoff',
        policy='One fixed conservative policy, no cutoff/parameter search. No false-positive guarantee; inner models differ from outer refit.',
        limitations='Inspected development cases; no independent accuracy estimate. Zero false flags in a small sample does not prove low population FPR.'))
    values = []; sources = []
    for index, case in enumerate(cases, 1):
        directory = pool/'analysis'/f'job_{index:04d}'; path = pool/'tracking'/f'case_{index:04d}.json'
        report = json.loads((directory/'report.json').read_text()); tracking = json.loads(path.read_text())
        for row in (receipt['cases'][index-1], inputs['cases'][index-1], inputs['tracking'][index-1]):
            if row['case_id'] != case['case_id']: raise ValueError('Source case identity mismatch')
        if (digest(directory/'report.json') != receipt['cases'][index-1]['report_sha256']
                or digest(directory/'report.json') != inputs['cases'][index-1]['report_sha256']
                or digest(path) != receipt['cases'][index-1]['tracking_sha256']
                or digest(path) != inputs['tracking'][index-1]['tracking_sha256']
                or tracking['summary']['case_id'] != case['case_id'] or tracking['summary']['label'] != case['label']
                or report['steamid'] != case['steamid'] or report['source_sha256'] != case['demo_sha256']
                or tracking['demo_sha256'] != case['demo_sha256'] or tracking['assumed_tickrate_hz'] != report['assumed_tickrate_hz']):
            raise ValueError('Source checksum/identity mismatch')
        for name in ('report.json', 'telemetry.csv', 'events.json'):
            if digest(directory/name) != tracking['input_sha256'][name]: raise ValueError('Tracking source mismatch')
        speed, _ = report_features(report); feature, coverage = case_features(tracking['windows'], tracking['assumed_tickrate_hz'])
        if feature is None: raise ValueError('Audit needs scored baseline coverage; do not silently omit cases')
        if feature != inputs['tracking'][index-1]['features']: raise ValueError('Tracking feature reproduction mismatch')
        values.append([*speed, *feature]); sources.append(dict(case_id=case['case_id'], coverage=coverage,
            report_sha256=digest(directory/'report.json'), tracking_sha256=digest(path), review=str((directory/'review.html').resolve())))
    reproduced = grouped_predictions(values, labels, groups, ids, 'log1p')
    old = {row['case_id']: row for row in original['predictions']}
    for row in reproduced['predictions']:
        previous = old[row['case_id']]
        if (previous['label'] != row['label'] or previous['status'] != 'scored'
                or abs(previous['baseline_score']-row['baseline_score']) > 1e-10 or previous['flagged'] != row['flagged']):
            raise ValueError('Baseline prediction reproduction mismatch')
    folds = {fold['fold']: fold for fold in reproduced['folds']}
    case_folds = {row['case_id']: folds[row['fold']] for row in reproduced['predictions']}
    explanations = []
    for index, case in enumerate(cases):
        row = old[case['case_id']]; explanation = explain_case(values, index, cases, case_folds[case['case_id']])
        if abs(explanation['score']-row['baseline_score']) > 1e-10: raise ValueError('Explanation score reproduction mismatch')
        directory = pool/'analysis'/f'job_{index+1:04d}'
        context = temporal_context(json.loads((directory/'report.json').read_text()),
                                   json.loads((pool/'tracking'/f'case_{index+1:04d}.json').read_text()),
                                   case_folds[case['case_id']])
        explanations.append(dict(case_id=case['case_id'], label=case['label'], flagged=row['flagged'], temporal_context=context,
            error=row['flagged'] != (case['label']=='cheating'), **explanation))
    write_json(output/'inputs.json', dict(values=values, sources=sources, groups=receipt['groups']))
    conservative = low_false_flag_predictions(values, labels, groups, ids)
    scenarios = [dict(prevalence=.01, recall=13/16, false_positive_rate=fpr,
                      precision=precision_at_prevalence(13/16, fpr, .01)) for fpr in (.1, .01, .001)]
    result = dict(role='inspected_development_only', feature_names=TRACKING_RECIPES['speed_and_tracking']['features'],
                  explanations=explanations, baseline=original, conservative=conservative, prevalence_illustrations=scenarios,
                  independent_zero_error_sample_planning={str(rate):negative_sample_requirement(rate) for rate in (.01, .001)},
                  protocol_sha256=digest(output/'protocol.json'), inputs_sha256=digest(output/'inputs.json'))
    write_json(output/'audit.json', result)
    lines = ['# Shared error and conservative operating-policy audit', '',
             'Previously inspected development data only. Contributions explain classifier arithmetic; neighbours are feature similarity, not behavioral ground truth.', '',
             '| Policy | TP | FN | FP | TN | Abstentions |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name, model in [('Existing cutoff 0.5', original), ('Nested training-only legitimate maximum', conservative)]:
        c = model['metrics']['confusion']; lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {model['metrics']['abstentions']} |")
    lines += ['', '## Baseline errors', '', '| Case | Label | Score | Largest positive feature | Nearest training cases |', '| --- | --- | ---: | --- | --- |']
    for row in explanations:
        if row['error']:
            feature = result['feature_names'][row['largest_positive_feature']] if row['largest_positive_feature'] is not None else 'none'
            neighbours = ', '.join(f"{r['case_id']} ({r['label']}, {r['distance']:.2f})" for r in row['nearest_training_cases'])
            lines.append(f"| {row['case_id']} | {row['label']} | {row['score']:.4f} | {feature} | {neighbours} |")
    lines += ['', '## Chronological context for baseline errors', '',
              '| Case | Windows | Eligible tracking, first / second half | Score, first / second half |',
              '| --- | ---: | --- | --- |']
    for row in explanations:
        if row['error']:
            context = row['temporal_context']; halves = context['chronological_halves']
            scores = ' / '.join('insufficient coverage' if h['score'] is None else f"{h['score']:.3f}" for h in halves)
            counts = ' / '.join(str(h['eligible_windows']) for h in halves)
            lines.append(f"| {row['case_id']} | {context['windows']} | {counts} | {scores} |")
    lines += ['', 'These half-match summaries are descriptive and use the same outer fold model; they are not independent predictions or validated aimbot activation intervals.']
    lines += ['', '## Base-rate illustrations', '', 'Assuming 1% cheating prevalence and 81.25% recall (illustrative inputs, not a deployment estimate):']
    for scenario in scenarios:
        lines.append(f"- FPR {scenario['false_positive_rate']:.1%}: {scenario['precision']:.1%} of flags would identify cheating.")
    lines += ['', 'For independent representative legitimate cases with zero false flags, a one-sided exact 95% upper FPR bound of 1% requires 299 cases; 0.1% requires 2,995. Grouped development predictions are not independent trials and do not establish either bound.',
              '', 'No model or policy is promoted or frozen; historical independent evaluation remains unchanged. Source cheating labels do not identify aimbot activation. Nearest horizontal opponent is not a validated intended target or visibility label.', '']
    (output/'report.md').write_text('\n'.join(lines)); print('\n'.join(lines[:9]), flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pool', type=Path); parser.add_argument('baseline_directory', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv); analyze(args.pool, args.baseline_directory, args.output)


if __name__ == '__main__': main()

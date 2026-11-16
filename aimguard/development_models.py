"""Exploratory grouped model comparisons on explicitly designated development data."""
import argparse
from datetime import datetime, timezone
import json
import importlib.metadata
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.preprocessing import StandardScaler

from aimguard.baseline import digest, evaluation_metrics, report_features, write_json

TIMING_FEATURES = ('near_shot_stop_fraction', 'near_shot_mean_turn',
                   'pre_post_speed_log_ratio', 'near_shot_peak_offset_seconds')
RECIPES = {
    'speed_acceleration': {'features': ['p95_speed', 'mean_accel'], 'transform': 'log1p'},
    'timing_direction': {'features': list(TIMING_FEATURES), 'transform': 'identity'},
}


def participant_groups(participants):
    """Connected components keep matches sharing any participant in one fold."""
    parents = list(range(len(participants)))
    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index
    seen = {}
    for index, members in enumerate(participants):
        if not members:
            raise ValueError('Participant lists must be nonempty')
        for member in sorted(members):
            if member in seen:
                parents[find(index)] = find(seen[member])
            seen[member] = index
    roots = [find(index) for index in range(len(participants))]
    identifiers = {root:index for index,root in enumerate(sorted(set(roots)))}
    return np.array([identifiers[root] for root in roots])


def load_development(manifest_path, analysis_root):
    from demoparser2 import DemoParser
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest.get('role') != 'development':
        raise ValueError('Use an explicitly designated development manifest')
    cases = manifest['cases']
    if len({case['steamid'] for case in cases}) != len(cases) or len({case['match_id'] for case in cases}) != len(cases):
        raise ValueError('Development targets and matches must be unique')
    matrices = {name:[] for name in RECIPES}
    participants, provenance = [], []
    for index,case in enumerate(cases,1):
        if case['label'] not in ('cheating','legitimate'):
            raise ValueError('Unknown development label')
        report_path = Path(analysis_root)/f'job_{index:04d}'/'report.json'
        report = json.loads(report_path.read_text())
        if report['steamid'] != case['steamid'] or report['source_sha256'] != case['demo_sha256']:
            raise ValueError('Report identity mismatch')
        speed, counts = report_features(report)
        matrices['speed_acceleration'].append(speed)
        timing = []
        for feature in TIMING_FEATURES:
            values = [w['shot_time_profile'][feature] for w in report['engagements']]
            eligible = [float(value) for value in values if value is not None and np.isfinite(value)]
            if not eligible:
                raise ValueError(f"No eligible {feature} observations for {case['case_id']}")
            timing.append(float(np.median(eligible)))
            counts[feature] = len(eligible)
        matrices['timing_direction'].append(timing)
        if digest(case['demo']) != case['demo_sha256']:
            raise ValueError('Demo checksum mismatch')
        info = DemoParser(case['demo']).parse_player_info()
        members = {str(int(value)) for value in info.steamid.dropna() if int(value)>0}
        if case['steamid'] not in members:
            raise ValueError('Selected player absent from demo participants')
        participants.append(members)
        provenance.append(dict(case_id=case['case_id'],report_sha256=digest(report_path),
                               demo_sha256=case['demo_sha256'],eligible_windows=counts))
    return cases, {name:np.asarray(values) for name,values in matrices.items()}, participants, provenance


def grouped_predictions(values, labels, groups, case_ids, transform):
    """Only deterministic elementwise transforms occur before group splitting."""
    values = np.asarray(values,dtype=float)
    labels, groups = np.asarray(labels), np.asarray(groups)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ValueError('Features must be a finite matrix')
    if len(values) != len(labels) or len(groups) != len(labels) or len(case_ids) != len(labels):
        raise ValueError('Features, labels, groups, and case IDs must align')
    if len(set(case_ids)) != len(case_ids):
        raise ValueError('Diagnostic case IDs must be unique')
    if len(set(groups)) < 2:
        raise ValueError('At least two independent participant groups are required')
    if transform == 'log1p':
        if (values < 0).any():
            raise ValueError('log1p baseline requires nonnegative measurements')
        prepared = np.log1p(values)
    elif transform == 'identity':
        prepared = values
    else:
        raise ValueError('Unknown transform')
    predictions, folds = [], []
    for fold,(train,test) in enumerate(LeaveOneGroupOut().split(prepared,labels,groups),1):
        if set(groups[train]) & set(groups[test]):
            raise ValueError('Participant group leakage')
        record = dict(fold=fold,train_case_ids=[case_ids[i] for i in train],
                      held_out_case_ids=[case_ids[i] for i in test])
        if len(set(labels[train])) < 2:
            record['status'] = 'abstained_single_training_class'
            for index in test:
                predictions.append(dict(case_id=case_ids[index],label='cheating' if labels[index] else 'legitimate',
                                        fold=fold,status='abstained',error='Training fold has one class'))
        else:
            scaler = StandardScaler().fit(prepared[train])
            model = LogisticRegression(C=1.0,class_weight='balanced',solver='lbfgs',
                                       max_iter=1000,random_state=0).fit(scaler.transform(prepared[train]),labels[train])
            scores = model.predict_proba(scaler.transform(prepared[test]))[:,1]
            record.update(status='scored',scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),
                          coefficients=model.coef_[0].tolist(),intercept=float(model.intercept_[0]))
            for index,score in zip(test,scores):
                predictions.append(dict(case_id=case_ids[index],label='cheating' if labels[index] else 'legitimate',
                                        fold=fold,status='scored',baseline_score=float(score),flagged=bool(score>=.5)))
        folds.append(record)
    if len(predictions) != len(labels) or len({p['case_id'] for p in predictions}) != len(labels):
        raise ValueError('Each case must have exactly one diagnostic prediction')
    metrics = evaluation_metrics(predictions)
    # Overlapping CV training folds do not provide independent binomial trials.
    for key in ('detection_rate','false_positive_rate','precision','accuracy'):
        metrics[key].pop('exact_95_interval',None)
    metrics['diagnostic_only'] = True
    return dict(predictions=predictions,folds=folds,metrics=metrics)


def compare_models(manifest_path, analysis_root, output):
    cases, matrices, participants, provenance = load_development(manifest_path,analysis_root)
    groups = participant_groups(participants)
    output = Path(output)
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        role='exploratory_development',recipes=RECIPES,hyperparameters=dict(C=1,class_weight='balanced',
        solver='lbfgs',max_iter=1000,random_state=0),threshold=.5,
        grouping='Connected components of all replay participants, including transitive links',
        manifest_sha256=digest(manifest_path),code_sha256=digest(__file__),
        dependencies={name:importlib.metadata.version(name) for name in ('numpy','pandas','scikit-learn','scipy','demoparser2')},
        source_code_sha256={name:digest(Path(__file__).with_name(name)) for name in ('development_models.py','baseline.py','combat.py','gameplay.py','core.py')},
        cases=provenance,groups={str(g):[c['case_id'] for c,k in zip(cases,groups) if k==g] for g in np.unique(groups)},
        note='Features and labels have been inspected during development. Grouped CV diagnostics do not establish fresh held-out performance.'))
    labels = np.array([int(c['label']=='cheating') for c in cases])
    case_ids = [c['case_id'] for c in cases]
    results = {name:grouped_predictions(matrices[name],labels,groups,case_ids,recipe['transform'])
               for name,recipe in RECIPES.items()}
    result = dict(cases=len(cases),participant_groups=len(set(groups)),models=results,
                  interpretation='Exploratory development comparison. Feature selection was informed by this pool, and CV folds share training data. Fresh cases are required for later performance claims.')
    write_json(output/'comparison.json',result)
    lines=['# Grouped development model diagnostics','',
           f"{len(cases)} selected player/match cases in {len(set(groups))} connected participant groups.",
           'Each diagnostic prediction holds out its entire participant component. Scaling and fitting use training groups only.',
           'This is exploratory development feedback. Feature choices were informed by this pool, and the results are not a fresh held-out evaluation.',
           '', '| Recipe | True positives | False negatives | False positives | True negatives | Abstentions |',
           '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,value in results.items():
        m=value['metrics'];c=m['confusion']
        lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {m['abstentions']} |")
    lines+=['','The speed recipe re-fits the original two measurements within every training fold. It differs from the preserved six-case frozen model evaluated earlier.',
            'The timing recipe uses case medians of stop fraction, mean turn angle, before/after log speed difference, and signed near-shot peak timing. Neither recipe uses window rows as independent training cases.',
            'Both use class-balanced logistic regression with C=1 and cutoff 0.5. No hyperparameter or cutoff search is performed.',
            'protocol.json records recipes, input hashes, case eligibility, and participant components. comparison.json records training/held-out case IDs, scaler statistics, and predictions for every fold.',
            'No production model is selected or fitted on the entire pool by this command. Original baseline results remain preserved. Source label subtype and identity-precision limits continue to apply.', '']
    (output/'report.md').write_text('\n'.join(lines))
    print('\n'.join(lines[:11]))
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('analysis_root',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        compare_models(args.manifest,args.analysis_root,args.output)
    except (OSError,ValueError,KeyError) as exc:
        parser.error(str(exc))


if __name__=='__main__':
    main()

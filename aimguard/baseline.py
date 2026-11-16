"""Freeze and evaluate a small player/match baseline using gameplay reports."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
from scipy.special import expit
from scipy.stats import binomtest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from aimguard.gameplay import FEATURE_VERSION, analyze_demo
from aimguard.batch import validate_windows

FEATURES = ('p95_speed', 'mean_accel')
EXPECTED_CONFIGURATION = {'weapon_mode': 'firearms', 'near_shot_seconds': 0.1,
                          'pre_seconds': 0.5, 'post_seconds': 0.5, 'shot_gap_seconds': 0.5}


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write('\n')


def report_features(report):
    if report['feature_version'] != FEATURE_VERSION:
        raise ValueError('Feature version differs from the frozen extractor')
    if any(report['configuration'].get(k) != v for k, v in EXPECTED_CONFIGURATION.items()):
        raise ValueError('Report configuration differs from the baseline protocol')
    values, counts = [], {}
    for name in FEATURES:
        measurements = [w['movement_context']['near_shot'][name] for w in report['engagements']]
        valid = [float(x) for x in measurements if x is not None and np.isfinite(x) and x >= 0]
        if not valid:
            raise ValueError(f'No eligible windows for {name}')
        values.append(float(np.median(valid)))
        counts[name] = len(valid)
    return values, counts


def model_score(bundle, features):
    values = np.asarray(features, dtype=float)
    if values.shape != (len(FEATURES),) or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('Invalid match features')
    standardized = (np.log1p(values) - np.asarray(bundle['scaler_mean'])) / np.asarray(bundle['scaler_scale'])
    margin = bundle['intercept'] + np.dot(bundle['coefficients'], standardized)
    return float(expit(margin))


def freeze(development_manifest, analysis_root, output):
    cases = json.loads(Path(development_manifest).read_text())
    features, labels, provenance = [], [], []
    for index, case in enumerate(cases, 1):
        path = Path(analysis_root) / f'job_{index:04d}' / 'report.json'
        report = json.loads(path.read_text())
        if report['steamid'] != case['steamid'] or report['source_sha256'] != case['demo_sha256']:
            raise ValueError('Development report identity mismatch')
        values, counts = report_features(report)
        if case['study_label'] not in ('cheating', 'legitimate'):
            raise ValueError('Unknown development label')
        features.append(values)
        labels.append(int(case['study_label'] == 'cheating'))
        provenance.append(dict(case=case['case'], match_id=case['match_id'], steamid=case['steamid'],
                               demo_sha256=case['demo_sha256'], report_sha256=digest(path),
                               features=values, eligible_windows=counts, label=case['study_label']))
    if len(set(labels)) != 2:
        raise ValueError('Development requires both labels')
    if len({r['steamid'] for r in provenance}) != len(provenance) or len({r['match_id'] for r in provenance}) != len(provenance):
        raise ValueError('Development targets and matches must be unique')
    scaler = StandardScaler().fit(np.log1p(features))
    transformed = scaler.transform(np.log1p(features))
    model = LogisticRegression(C=1.0, class_weight='balanced', solver='lbfgs', max_iter=1000,
                               random_state=0).fit(transformed, labels)
    bundle = dict(schema_version=1, frozen_at_utc=datetime.now(timezone.utc).isoformat(),
                  feature_version=FEATURE_VERSION, feature_names=list(FEATURES),
                  aggregation='Median of eligible per-window near-shot measurements per selected player/match',
                  transformation='log1p followed by StandardScaler fitted on development cases only',
                  model='LogisticRegression', hyperparameters=dict(C=1.0, class_weight='balanced',
                      solver='lbfgs', max_iter=1000, random_state=0),
                  threshold=0.5, classes=[0,1], configuration=EXPECTED_CONFIGURATION,
                  assumed_tickrate_hz=64.0,
                  scaler_mean=scaler.mean_.tolist(), scaler_scale=scaler.scale_.tolist(),
                  coefficients=model.coef_[0].tolist(), intercept=float(model.intercept_[0]),
                  development=provenance, development_manifest_sha256=digest(development_manifest),
                  code_sha256={p.name:digest(p) for p in (Path(__file__), Path(__file__).with_name('gameplay.py'),
                      Path(__file__).with_name('combat.py'), Path(__file__).with_name('core.py'),
                      Path(__file__).with_name('batch.py'))},
                  dependencies={name:importlib.metadata.version(name) for name in
                      ('numpy','scipy','scikit-learn','pandas','demoparser2')},
                  score_note='Uncalibrated logistic baseline score; not a validated cheating probability')
    for values, expected in zip(features, model.predict_proba(transformed)[:,1]):
        if not np.isclose(model_score(bundle, values), expected, atol=1e-12):
            raise ValueError('Exported model does not reproduce fitted scores')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'model.json', bundle)
    (output / 'model.sha256').write_text(digest(output / 'model.json') + '\n')
    return bundle


def evaluation_metrics(rows):
    scored = [r for r in rows if r['status'] == 'scored']
    positives = [r for r in scored if r['label'] == 'cheating']
    negatives = [r for r in scored if r['label'] == 'legitimate']
    tp = sum(r['flagged'] for r in positives)
    fp = sum(r['flagged'] for r in negatives)
    tn, fn = len(negatives) - fp, len(positives) - tp
    def rate(k, n):
        if not n:
            return dict(numerator=k, denominator=n, value=None, exact_95_interval=None)
        interval = binomtest(k,n).proportion_ci(confidence_level=0.95, method='exact')
        return dict(numerator=k, denominator=n, value=k/n,
                    exact_95_interval=[float(interval.low),float(interval.high)])
    return dict(cases=len(rows),scored=len(scored),abstentions=len(rows)-len(scored),
                confusion=dict(true_positive=tp,false_positive=fp,true_negative=tn,false_negative=fn),
                detection_rate=rate(tp,len(positives)),false_positive_rate=rate(fp,len(negatives)),
                precision=rate(tp,tp+fp),accuracy=rate(tp+tn,len(scored)),
                rates_conditioned_on_successful_analysis=True,
                abstentions_by_label={label:sum(r['status']!='scored' and r['label']==label for r in rows)
                                      for label in ('cheating','legitimate')})


def evaluate(model_directory, reserved_manifest, output):
    import pandas as pd
    model_directory, reserved_manifest, output = map(Path,(model_directory,reserved_manifest,output))
    model_path = model_directory / 'model.json'
    model_hash = digest(model_path)
    if model_hash != (model_directory / 'model.sha256').read_text().strip():
        raise ValueError('Model checksum mismatch')
    bundle = json.loads(model_path.read_text())
    if bundle['feature_names'] != list(FEATURES):
        raise ValueError('Unexpected frozen feature names')
    for name, expected in bundle['code_sha256'].items():
        if digest(Path(__file__).with_name(name)) != expected:
            raise ValueError(f'Frozen code changed: {name}')
    for name, expected in bundle['dependencies'].items():
        if importlib.metadata.version(name) != expected:
            raise ValueError(f'Frozen dependency changed: {name}')
    receipt_path = reserved_manifest.with_suffix('.sha256')
    if digest(reserved_manifest) != receipt_path.read_text().strip():
        raise ValueError('Reserved manifest checksum mismatch')
    reserved = json.loads(reserved_manifest.read_text())
    cases = reserved['cases']
    development_targets = {r['steamid'] for r in bundle['development']}
    development_matches = {r['match_id'] for r in bundle['development']}
    development_hashes = {r['demo_sha256'] for r in bundle['development']}
    targets, matches, hashes = set(),set(),set()
    for case in cases:
        if case['label'] not in ('cheating','legitimate'):
            raise ValueError('Unknown evaluation label')
        if case['steamid'] in targets | development_targets or case['match_id'] in matches | development_matches or case['demo_sha256'] in hashes | development_hashes:
            raise ValueError('Duplicate or development-overlapping evaluation case')
        targets.add(case['steamid'])
        matches.add(case['match_id'])
        hashes.add(case['demo_sha256'])
        if not isinstance(case['steamid'],str) or not case['steamid'].isdigit():
            raise ValueError('Exact string SteamIDs are required')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'start-receipt.json',dict(started_at_utc=datetime.now(timezone.utc).isoformat(),
        model_sha256=model_hash,reserved_manifest_sha256=digest(reserved_manifest),
        feature_version=bundle['feature_version'],threshold=bundle['threshold'],
        note='Frozen model and configuration recorded before reserved feature extraction'))
    rows = []
    for index, case in enumerate(cases,1):
        row = dict(case_id=index,match_id=case['match_id'],steamid=case['steamid'],label=case['label'])
        try:
            if digest(case['demo']) != case['demo_sha256'] or digest(case['source_label_file']) != case['source_label_sha256']:
                raise ValueError('Case source checksum mismatch')
            directory = output / f'case_{index:02d}'
            report = analyze_demo(case['demo'],case['steamid'],directory,
                                  tickrate=bundle['assumed_tickrate_hz'],max_plots=0)
            player = pd.read_csv(directory/'telemetry.csv',dtype={'steamid':str})
            events = pd.DataFrame(json.loads((directory/'events.json').read_text()))
            if events.empty:
                events = pd.DataFrame(columns=['tick','event_type','player_role','segment_id'])
            violations = validate_windows(player,events,report)
            if violations:
                raise ValueError(f'Structural violations: {violations}')
            values, counts = report_features(report)
            score = model_score(bundle,values)
            row.update(status='scored',baseline_score=score,flagged=score>=bundle['threshold'],
                       features=dict(zip(FEATURES,values)),eligible_windows=counts,
                       windows=report['engagement_count'],round_warnings=report['data_quality']['round_event_anomalies'],
                       report_sha256=digest(directory/'report.json'))
        except Exception as exc:
            row.update(status='abstained',error_type=type(exc).__name__,error=str(exc))
        rows.append(row)
        write_json(output/f'prediction_{index:02d}.json',row)
        print(f"{index}/{len(cases)}: {row['status']} {case['match_id']}",flush=True)
    result = dict(model_sha256=model_hash,reserved_manifest_sha256=digest(reserved_manifest),
                  completed_at_utc=datetime.now(timezone.utc).isoformat(),threshold=bundle['threshold'],
                  metrics=evaluation_metrics(rows),predictions=rows,
                  caveats=reserved.get('caveats',[]) + [
                      'Six selected development cases, including only two legitimate cases, cannot establish a robust model.',
                      'Eleven archive-order evaluation targets form a small convenience sample with source-label precision limits.',
                      'Confidence intervals are exact binomial intervals and assume independent outcomes. Non-target overlap and source sampling may violate that assumption.',
                      'Scores are uncalibrated. Features do not account for visibility, target-relative aim, or recoil.',
                      'The reserved sample has now been evaluated. Further tuning on its results makes it development data.'])
    write_json(output/'evaluation.json',result)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_subparsers(dest='action',required=True)
    training=actions.add_parser('freeze')
    training.add_argument('development_manifest',type=Path)
    training.add_argument('analysis_root',type=Path)
    training.add_argument('--output',required=True,type=Path)
    evaluation=actions.add_parser('evaluate')
    evaluation.add_argument('model_directory',type=Path)
    evaluation.add_argument('reserved_manifest',type=Path)
    evaluation.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        if args.action=='freeze':
            freeze(args.development_manifest,args.analysis_root,args.output)
        else:
            result=evaluate(args.model_directory,args.reserved_manifest,args.output)
            print(json.dumps(result['metrics'],indent=2))
    except (OSError,ValueError,KeyError) as exc:
        parser.error(str(exc))


if __name__=='__main__':
    main()

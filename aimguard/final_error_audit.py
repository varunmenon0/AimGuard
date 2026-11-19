"""Bounded descriptive audit of the consumed mixed-cohort false flag and miss."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.baseline import digest, write_json
from aimguard.combat import interval_motion
from aimguard.core import angle_delta
from aimguard.offline_detector import load
from aimguard.phase_development import speed_features, verify_live
from aimguard.shot_motion_audit import window_motion
from aimguard.tracking_models import case_features, window_features


def movement(part, window, rate):
    """Describe held view updates and a fixed two-tick velocity estimate."""
    times=part.tick.to_numpy(float)/rate
    if len(times)<4 or not np.allclose(np.diff(times),1/rate,rtol=0,atol=1e-10):
        raise ValueError('Nonconsecutive window support')
    yaw=part.yaw.to_numpy(float);pitch=part.pitch.to_numpy(float)
    dy=angle_delta(np.diff(yaw));dp=np.diff(pitch)
    held=(dy==0)&(dp==0)
    near=interval_motion(part,window['shot_ticks'],rate)
    mask=abs(near['shot_offset_seconds'])<=.1
    # Velocity averaged over two actual ticks, then differenced at its true 1-tick spacing.
    v=np.column_stack((dy[:-1]+dy[1:],dp[:-1]+dp[1:]))/(times[2:]-times[:-2])[:,None]
    speed=np.linalg.norm(v,axis=1)
    supported=mask[:-1]&mask[1:]
    acc=np.diff(speed)/np.diff((times[2:]+times[:-2])/2)
    acc_support=supported[:-1]&supported[1:]
    return dict(held_fraction=float(held[mask].mean()) if mask.any() else None,
        alternation_fraction=float(np.mean(held[1:]!=held[:-1])),
        two_tick_features=[float(np.percentile(speed[supported],95)) if supported.any() else None,
                           float(np.abs(acc[acc_support]).mean()) if acc_support.any() else None])


def run(evaluation, model, output):
    evaluation,model,output=map(Path,(evaluation,model,output));bundle=load(model)
    result=json.loads((evaluation/'evaluation.json').read_text());rows=result['predictions']
    errors=[(i,r) for i,r in enumerate(rows,1) if r['status'] in ('flag_for_review','not_flagged') and
            (r['flagged']!=(r['label']=='cheating'))]
    if len(errors)!=2 or {(r['case_id'],r['label']) for _,r in errors}!={('B1-F-013','legitimate'),('P-SHARED-002','cheating')}:
        raise ValueError('Expected exactly the recorded false flag and miss')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='consumed_case_diagnostic_not_fresh_evaluation',
        evaluation_sha256=digest(evaluation/'evaluation.json'),model_sha256=digest(model/'model.json'),
        code_sha256=digest(__file__),case_ids=[r['case_id'] for _,r in errors],
        selection='All recorded classification errors. Representative curve: smallest standardized log-feature distance to that player case medians.',
        bounds='One audit and, only if measurement evidence supports it, one fixed development-only candidate. No threshold/feature grid, model promotion, replay download or fresh-evaluation reuse.',
        note='Local geometry is not visibility or verified target intention. Post-shot motion does not establish recoil causation. Generic positive label does not prove active aimbot.'))
    records=[];plot_data=[]
    for index,row in errors:
        directory=evaluation/f'case_{index:03d}';analysis=directory/'analysis'
        prediction=json.loads((directory/'prediction.json').read_text());report=json.loads((analysis/'report.json').read_text());track=json.loads((directory/'tracking.json').read_text())
        if digest(analysis/'report.json')!=prediction['report_sha256'] or digest(directory/'tracking.json')!=prediction['tracking_sha256']:
            raise ValueError('Source receipts differ')
        for name,sha in track['input_sha256'].items():
            if digest(analysis/name)!=sha:raise ValueError('Tracking inputs changed')
        verify_live(analysis,report);features=[*speed_features(report),*case_features(track['windows'],64)[0]]
        if not np.allclose(features,prediction['features'],rtol=0,atol=1e-10):raise ValueError('Frozen feature mismatch')
        frame=pd.read_csv(analysis/'telemetry.csv',usecols=['tick','yaw','pitch','segment_id','active','phase_status'])
        windows=[];parts=[];association=Counter()
        for w,t in zip(report['engagements'],track['windows']):
            if w['engagement_id']!=t['engagement_id']:raise ValueError('Window identity mismatch')
            part=frame.loc[frame.segment_id.eq(w['segment_id'])&frame.tick.between(w['start_tick'],w['end_tick'])]
            if len(part)!=w['samples'] or not part.active.all() or not part.phase_status.eq('live').all():raise ValueError('Window support invalid')
            timing=window_motion(part,w,64);m=movement(part,w,64);tracking,reason=window_features(t,64)
            if reason:raise ValueError('Unexpected tracking exclusion')
            association['candidate_changes_at_first_shot']+=int(t['nearest_before_first_shot']!=t['nearest_at_first_shot'])
            if len(t['damage_recipients'])==1:
                association['single_damage_windows']+=1
                association['candidate_matches_single_damage_recipient']+=int(t['nearest_before_first_shot']==t['damage_recipients'][0])
            windows.append(dict(engagement_id=w['engagement_id'],weapon=w['weapon'],round_id=w['round_id'],
                **m,timing=timing,tracking_features=tracking,features=[*timing['original_features'],*tracking]))
            parts.append((part,w,t))
        matrix=np.asarray([w['features'] for w in windows]);distances=np.linalg.norm((np.log1p(matrix)-np.log1p(features))/bundle['scaler_scale'],axis=1)
        representative=int(np.argmin(distances))
        def med(key):return [float(np.median([w[key][i] for w in windows if w[key][i] is not None])) for i in range(2)]
        timing_counts={k:sum(w['timing'][k] for w in windows) for k in ('near_speed_intervals','near_speed_at_or_after_first','near_acceleration_samples','near_acceleration_at_or_after_first')}
        reference={label:{name:float(100*np.mean([np.log1p(c['features'][j])<=np.log1p(features[j]) for c in bundle['training'] if c['label']==label]))
                          for j,name in enumerate(bundle['feature_names'])} for label in ('legitimate','cheating')}
        record=dict(case_id=row['case_id'],label=row['label'],score=row['score'],features=features,
            contributions=prediction['contributions'],intercept=prediction['intercept'],windows=len(windows),
            held_fraction_median=float(np.median([w['held_fraction'] for w in windows])),
            alternation_fraction_median=float(np.median([w['alternation_fraction'] for w in windows])),
            two_tick_case_features=med('two_tick_features'),
            pre_first_case_features=[float(np.median([w['timing']['pre_first_features'][i] for w in windows if w['timing']['pre_first_features'][i] is not None])) for i in range(2)],
            shot_timing_counts=timing_counts,association=dict(association),development_feature_percentiles=reference,
            representative_engagement_id=windows[representative]['engagement_id'],per_window=windows,
            report_sha256=prediction['report_sha256'],tracking_sha256=prediction['tracking_sha256'],
            quality='All windows live, contiguous, identity-matched and eligible; all frozen features reproduced. Round-event warnings retained.')
        records.append(record);plot_data.append((record,parts[representative]))
    write_json(output/'audit.json',dict(cases=records,models_changed=False,protocol_sha256=digest(output/'protocol.json')))
    render(plot_data,bundle,output/'curves.png')
    print(json.dumps([{k:v for k,v in r.items() if k!='per_window'} for r in records],indent=2),flush=True)
    return records


def render(data,bundle,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,4,figsize=(19,8),layout='constrained')
    names=['Speed','Acceleration','Aim alignment','Relative motion']
    for axrow,(record,(part,w,t)) in zip(axes,data):
        values=list(record['contributions'].values());ax=axrow[0]
        ax.barh(names,values,color=['#bd503d' if v>0 else '#327ca1' for v in values]);ax.axvline(0,color='black',lw=.7)
        ax.set_title(record['case_id']+' / '+record['label']+'\nscore '+f'{record["score"]:.3f}');ax.set_xlabel('Signed log-odds contribution')
        candidate=next(tr for tr in t['tracks'] if tr['opponent_id']==t['nearest_before_first_shot'])
        ticks=np.asarray(candidate['ticks']);seconds=(ticks-w['shot_ticks'][0])/64;mask=(seconds>=-.3)&(seconds<=.2)
        ax=axrow[1];ax.plot(seconds[mask],np.asarray(candidate['signed_error_degrees'],float)[mask],color='#335c81',marker='.',ms=3);ax.axhline(0,color='grey',lw=.7)
        ax.set_title(f'Representative window {w["engagement_id"]}: aim error');ax.set_ylabel('Horizontal degrees')
        ax=axrow[2]
        for key,label in [('yaw_rate_dps','View yaw'),('bearing_rate_dps','Opponent bearing')]:ax.plot(seconds[mask],np.asarray(candidate[key],float)[mask],label=label,marker='.',ms=3)
        ax.set_title('View and geometric bearing rates');ax.set_ylabel('Degrees / second');ax.legend(fontsize=8)
        motion=interval_motion(part,w['shot_ticks'],64);ts=(part.tick.to_numpy()[1:]-w['shot_ticks'][0])/64;sel=(ts>=-.3)&(ts<=.2)
        ax=axrow[3];ax.plot(ts[sel],motion['speed'][sel],marker='.',ms=3,color='#854b94');ax.set_title('Recorded angular speed');ax.set_ylabel('Degrees / second')
        for ax in axrow[1:]:
            ax.axvspan(-.2,0,color='#e5edda',alpha=.65);ax.axvline(0,color='black',ls='--',lw=.8);ax.set_xlabel('Seconds from first shot');ax.grid(alpha=.2)
    fig.suptitle('Consumed-case diagnostic: frozen contributions and fixed-opponent curves\nShading: 200 ms pre-shot feature period. Geometry does not establish visibility or aim assistance.',fontsize=13)
    fig.savefig(path,dpi=140);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('evaluation',type=Path);p.add_argument('model',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.evaluation,a.model,a.output)

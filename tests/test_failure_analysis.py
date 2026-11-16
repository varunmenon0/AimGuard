import numpy as np
import pytest
from aimguard.failure_analysis import contributions,summarize


def bundle():
    return dict(feature_names=['speed','error'],scaler_mean=[1.,1.],scaler_scale=[2.,.5],coefficients=[1.,-2.],intercept=.2,threshold=.5)


def test_contributions_reconstruct_logistic_margin_with_standardization():
    b=bundle();values=[4.,2.];r=contributions(b,values)
    z=(np.log1p(values)-np.array([1.,1.]))/np.array([2.,.5])
    assert list(r['contributions'].values())==pytest.approx([z[0],-2*z[1]])
    assert r['margin']==pytest.approx(.2+z[0]-2*z[1])
    assert r['frozen_score']==pytest.approx(1/(1+np.exp(-r['margin'])))
    assert r['flagged']==(r['frozen_score']>=.5)


def test_lower_error_with_negative_weight_raises_the_frozen_score():
    assert contributions(bundle(),[4.,.1])['frozen_score']>contributions(bundle(),[4.,10.])['frozen_score']


def test_invalid_vectors_do_not_produce_explanations():
    for values in ([1.],[-1.,2.],[np.nan,2.]):
        with pytest.raises(ValueError,match='feature vector'):contributions(bundle(),values)


def test_case_summaries_keep_cohort_and_label_separate():
    records=[dict(cohort='old',label='legitimate',**contributions(bundle(),[1.,2.])),
        dict(cohort='old',label='legitimate',**contributions(bundle(),[3.,4.])),
        dict(cohort='new',label='cheating',**contributions(bundle(),[100.,100.]))]
    r=summarize(records,['speed','error'])
    old=next(row for row in r if row['cohort']=='old')
    assert old['cases']==2 and old['features']['speed']['median']==2


def test_failed_frozen_receipts_do_not_create_diagnostics(tmp_path,monkeypatch):
    import json
    import aimguard.failure_analysis as module
    from aimguard.baseline import digest
    model=tmp_path/'model';model.mkdir();(model/'model.json').write_text('fixture')
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps(dict(role='development',cases=[])))
    evaluation=tmp_path/'evaluation';evaluation.mkdir()
    receipt=dict(model_sha256='wrong',reserved_manifest_sha256='reserved',threshold=.5)
    (evaluation/'evaluation.json').write_text(json.dumps(receipt))
    (evaluation/'start-receipt.json').write_text(json.dumps(receipt))
    monkeypatch.setattr(module,'load_model',lambda _:dict(feature_names=[],development_manifest_sha256=digest(manifest),development=[]))
    output=tmp_path/'diagnostics'
    with pytest.raises(ValueError,match='frozen receipt mismatch'):
        module.analyze(model,manifest,tmp_path,tmp_path,evaluation,output)
    assert not output.exists()


def test_weapon_context_is_descriptive_and_checks_window_identity():
    from aimguard.failure_analysis import context
    track=dict(engagement_id=0,weapon='ak47',shot_ticks=[20],nearest_before_first_shot='a',
        tracks=[dict(opponent_id='a',ticks=list(range(26)),segment_ids=[0]*26,
            signed_error_degrees=[2.]*26,yaw_rate_dps=[5.]*26,bearing_rate_dps=[2.]*26)])
    report=dict(assumed_tickrate_hz=64,engagements=[dict(engagement_id=0,weapon='ak47',shot_ticks=[20],
        movement_context=dict(near_shot=dict(p95_speed=10.,mean_accel=100.)))])
    value=context(report,dict(windows=[track]))
    assert value['weapon_fractions']=={'ak47':1.}
    assert value['per_weapon_features']['ak47']['medians']==[10.,100.,2.,3.]
    track['engagement_id']=1
    with pytest.raises(ValueError,match='window identity mismatch'):
        context(report,dict(windows=[track]))

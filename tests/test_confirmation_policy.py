import copy
import json
import numpy as np
import pytest
from aimguard.confirmation_policy import confirm,verify_folds,run
from aimguard.development_models import grouped_predictions


def prediction(score,label='legitimate'):
    return dict(case_id='A',label=label,status='scored',baseline_score=score,flagged=score>=.5)


def test_fixed_agreement_and_disagreement_decisions():
    assert confirm(prediction(.8),prediction(.6))['decision']=='flag'
    assert confirm(prediction(.2),prediction(.4))['decision']=='not_flagged'
    for a,b in [(.8,.4),(.2,.7)]:
        r=confirm(prediction(a),prediction(b))
        assert r['decision']=='review_disagreement' and r['flagged'] is None
    assert confirm(prediction(.5),prediction(.5))['flagged'] is True


def test_missing_evidence_is_unresolved_and_cannot_be_counted_clean():
    missing=dict(case_id='A',label='legitimate',status='abstained')
    r=confirm(prediction(.2),missing)
    assert r['decision']=='review_missing_evidence' and r['flagged'] is None
    with pytest.raises(ValueError):confirm(prediction(.2),dict(missing,case_id='B'))
    p=prediction(.9);p['flagged']=False
    with pytest.raises(ValueError):confirm(p,prediction(.9))


def test_matched_fold_scores_verify_and_outer_leakage_rejected():
    x=np.arange(42,dtype=float).reshape(6,7);labels=[0,1]*3;groups=['a','a','b','b','c','c'];ids=list('ABCDEF')
    a=grouped_predictions(x[:,:4],labels,groups,ids,'identity');b=grouped_predictions(x,labels,groups,ids,'identity')
    inputs=dict(cases=[dict(case_id=cid,label='cheating' if label else 'legitimate',features=v.tolist()) for cid,label,v in zip(ids,labels,x)],groups={g:[cid for cid,k in zip(ids,groups) if k==g] for g in set(groups)})
    verify_folds(a,b,inputs)
    bad=copy.deepcopy(b);bad['folds'][0]['train_case_ids'].append('A')
    with pytest.raises(ValueError):verify_folds(a,bad,inputs)


def test_tampered_receipt_fails_before_output(tmp_path):
    for name,v in [('comparison.json',{'protocol_sha256':'wrong'}),('inputs.json',{}),('protocol.json',{})]:
        (tmp_path/name).write_text(json.dumps(v))
    with pytest.raises(ValueError,match='receipt'):run(tmp_path,tmp_path/'out')
    assert not (tmp_path/'out').exists()

import copy
import numpy as np
import pytest
from aimguard.evidence_score import FAMILIES,fit_stack,stack_score,meta_rows,evaluate


def sample():
    rng=np.random.default_rng(4);rows=[]
    for i in range(8):
        label='cheating' if i%2 else 'legitimate'
        rows.append(dict(case_id=str(i),label=label,group=str(i//2),families={f:(rng.normal(size=2)+i%2).tolist() for f in FAMILIES}))
    return rows


def test_meta_training_is_group_cross_fitted_and_outer_data_excluded():
    rows=sample();train=rows[2:];model=fit_stack(train)
    for f in model['inner_folds']:
        assert not set(f['train_case_ids'])&set(f['held_out_case_ids'])
        assert not (set(f['train_case_ids'])|set(f['held_out_case_ids']))&{'0','1'}
        groups={r['case_id']:r['group'] for r in train}
        assert not {groups[c] for c in f['train_case_ids']}&{groups[c] for c in f['held_out_case_ids']}
    assert {r['case_id'] for r in model['cross_fitted_margins']}=={r['case_id'] for r in train}


def test_missing_values_have_explicit_flags_and_low_coverage_abstains():
    assert meta_rows([[None,1,None,-2]],[3,4,5,6])==[[3,1,5,-2,1,0,1,0]]
    rows=sample();model=fit_stack(rows)
    target=copy.deepcopy(rows[0]);target['families']['burst']=None
    assert stack_score(model,target)['family_margins'][2] is None
    target['families']={f:None for f in FAMILIES};target['families']['tracking']=[1,2]
    p=stack_score(model,target)
    assert p['status']=='abstained' and p['flagged'] is None


def test_outer_held_out_feature_or_label_changes_do_not_change_fitted_models():
    rows=sample();a=evaluate(rows);changed=copy.deepcopy(rows)
    for r in changed[:2]:
        r['families']={f:[99,100] for f in FAMILIES};r['label']='legitimate'
    b=evaluate(changed)
    assert a['folds'][0]['model']==b['folds'][0]['model']
    assert a['predictions'][0]['priority_score']!=b['predictions'][0]['priority_score']


def test_case_identity_and_training_group_guards():
    rows=sample();rows[1]['case_id']=rows[0]['case_id']
    with pytest.raises(ValueError):evaluate(rows)
    with pytest.raises(ValueError):fit_stack(sample()[:4])

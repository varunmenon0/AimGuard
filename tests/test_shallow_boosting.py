import numpy as np
import pytest
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.utils.class_weight import compute_sample_weight
from aimguard.shallow_boosting import PARAMETERS,fit_trees,tree_score,evaluate


def sample():
    x=np.random.default_rng(2).uniform(0,10,(24,4));y=(x[:,0]>5).astype(int)
    return x,y


def test_exported_trees_reproduce_library_predictions():
    x,y=sample();bundle=fit_trees(x,y)
    fitted=GradientBoostingClassifier(**PARAMETERS).fit(np.log1p(x),y,sample_weight=compute_sample_weight('balanced',y))
    assert np.allclose([tree_score(bundle,v) for v in x],fitted.predict_proba(np.log1p(x))[:,1],atol=1e-12)
    assert len(bundle['trees'])==100
    with pytest.raises(ValueError):tree_score(bundle,[-.1,1,2,3])


def test_outer_held_out_feature_and_label_changes_do_not_change_trees():
    x,y=sample();g=[str(i//2) for i in range(24)];ids=[str(i) for i in range(24)]
    a=evaluate(x,y,g,ids);x[:2]+=100;y[:2]=0;b=evaluate(x,y,g,ids)
    assert a['folds'][0]==b['folds'][0]
    assert a['predictions'][0]['baseline_score']!=b['predictions'][0]['baseline_score']


def test_invalid_features_and_sparse_training_classes():
    with pytest.raises(ValueError):fit_trees([[np.nan]*4]*3,[0,1,0])
    r=evaluate(np.ones((4,4)),[0,0,0,1],list('abcd'),list('ABCD'))
    assert r['metrics']['abstentions']==1

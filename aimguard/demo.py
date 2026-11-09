"""Synthetic smoke-test data, NOT empirical cheat detection evidence."""
import argparse
import json
from pathlib import Path
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import confusion_matrix, precision_score, recall_score
from .core import FEATURE_NAMES, extract_features

def generate_trace(rng, automated=False, n=96, hz=64):
    t = np.arange(n)/hz
    start = rng.uniform(-120,120)
    amplitude = rng.uniform(15,75) * rng.choice([-1,1])
    x = np.linspace(0,1,n)
    if automated:
        # Deliberately simplified deterministic easing, not a real cheat implementation.
        progress = 3*x*x-2*x*x*x
        yaw = start + amplitude*progress + rng.normal(0,0.025,n)
        pitch = 4*progress + rng.normal(0,0.025,n)
    else:
        progress = np.clip(x+rng.normal(0,0.025,n).cumsum()/8,0,1)
        yaw = start + amplitude*progress + rng.normal(0,0.22,n)
        pitch = 4*progress + rng.normal(0,0.18,n)
    return t,yaw,pitch

def dataset(seed=42, sessions=100, windows=4):
    rng = np.random.default_rng(seed)
    X=[]; labels=[]; groups=[]
    for session in range(sessions):
        label = session % 2
        for _ in range(windows):
            trace = generate_trace(rng, bool(label))
            features = extract_features(*trace)
            X.append([features[k] for k in FEATURE_NAMES])
            labels.append(label); groups.append(session)
    return np.asarray(X),np.asarray(labels),np.asarray(groups)

def run(output):
    X,y,groups=dataset()
    # Entire sessions held out, preventing leakage from correlated windows.
    train=groups<70
    model=HistGradientBoostingClassifier(max_iter=75,max_leaf_nodes=7,random_state=42)
    model.fit(X[train],y[train])
    probs=model.predict_proba(X[~train])[:,1]
    pred=(probs>=0.5).astype(int)
    report={"dataset":"synthetic smoke test only", "train_sessions":70,"test_sessions":30,
            "test_windows":int((~train).sum()),"threshold":0.5,
            "recall":float(recall_score(y[~train],pred,zero_division=0)),
            "precision":float(precision_score(y[~train],pred,zero_division=0)),
            "confusion_matrix_TN_FP_FN_TP":confusion_matrix(y[~train],pred,labels=[0,1]).ravel().tolist(),
            "warning":"Scores are not evidence of real-world anti-cheat effectiveness. Synthetic classes intentionally differ."}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",default="outputs/synthetic_report.json")
    run(parser.parse_args().output)

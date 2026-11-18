"""Plot saved review-ranking curves without fitting or selecting a cutoff."""
import argparse
import json
from pathlib import Path
import numpy as np
from sklearn.metrics import average_precision_score,precision_recall_curve


def render(directory):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    directory=Path(directory);result=json.loads((directory/'comparison.json').read_text());fig,axis=plt.subplots(figsize=(7,4.8),layout='constrained');statistics={}
    for name,model in result['models'].items():
        rows=model['predictions']
        if any(r['status']!='scored' for r in rows):raise ValueError('Ranking plot requires complete scores; do not silently drop abstentions')
        y=np.array([r['label']=='cheating' for r in rows]);scores=np.array([r['baseline_score'] for r in rows]);precision,recall,_=precision_recall_curve(y,scores);ap=float(average_precision_score(y,scores));order=np.argsort(-scores,kind='stable')
        statistics[name]=dict(average_precision=ap,review_budgets={str(k):dict(cheating_labels=int(y[order[:k]].sum()),legitimate_labels=int(k-y[order[:k]].sum())) for k in (5,10,20) if k<=len(rows)})
        axis.step(recall,precision,where='post',label=f'{name.replace("_"," ")} (AP {ap:.3f})')
    cases=len(next(iter(result['models'].values()))['predictions']);axis.set(xlabel='Fraction of cheating-labeled cases retrieved',ylabel='Fraction of reviewed cases with cheating labels',xlim=(0,1),ylim=(0,1.04),title=f'Review ranking · {cases} inspected development cases\nParticipant-held-out scores; no cutoff selected');axis.legend();axis.grid(alpha=.2);fig.savefig(directory/'ranking.png',dpi=160);plt.close(fig)
    (directory/'ranking.json').write_text(json.dumps(dict(statistics=statistics,note='Post-fit descriptive review budgets, not independent evaluation or a selected deployment cutoff. Ties use saved case order.'),indent=2)+'\n')
    print(json.dumps(statistics),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args();render(a.directory)

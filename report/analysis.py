import json, numpy as np, pandas as pd
from sklearn.metrics import precision_score, recall_score, f1_score, accuracy_score, roc_auc_score
from sklearn.linear_model import LogisticRegression
from tensorflow import keras
import config
from preprocessing.preprocessing import run_preprocessing
from fault_prediction.create_sequences import build_all_splits
feat, _ = run_preprocessing(save=False)
sp = build_all_splits(feat)
model = keras.models.load_model("models/lstm_fault_model.keras")
thr = json.load(open("models/threshold.json"))["threshold"]
out = {}
def m(y, pred, p=None):
    d = dict(acc=accuracy_score(y, pred), prec=precision_score(y, pred, zero_division=0), rec=recall_score(y, pred), f1=f1_score(y, pred))
    if p is not None: d["auc"] = roc_auc_score(y, p)
    return d
P = {}
for s in ("val", "test"):
    X, y, meta = sp[s]; P[s] = model.predict(X, batch_size=512, verbose=0).ravel()
# threshold sweep
out["sweep"] = {s: {str(t): m(sp[s][1], (P[s] >= t).astype(int)) for t in (0.10, 0.22, 0.30, 0.40, 0.50, 0.60)} for s in ("val", "test")}
# per device test
X, y, meta = sp["test"]; dev = np.array([k["device_name"] for k in meta]); pred = (P["test"] >= thr).astype(int)
out["per_device"] = {d: dict(n=int((dev == d).sum()), pos=int(y[dev == d].sum()), **m(y[dev == d], pred[dev == d])) if len(set(y[dev == d])) else {} for d in sorted(set(dev))}
# persistence baseline: label at window end -> predict same at t+1
idx = feat.set_index(["device_name", "timestamp"])["fault"]
cur = np.array([idx.loc[(k["device_name"], k["window_end_timestamp"])] for k in meta])
out["persistence_test"] = m(y, cur)
out["always_fault_test"] = m(y, np.ones_like(y))
# logistic regression on flattened window
Xtr, ytr, _ = sp["train"]
lr = LogisticRegression(max_iter=300).fit(Xtr.reshape(len(Xtr), -1), ytr)
pl = lr.predict_proba(X.reshape(len(X), -1))[:, 1]
pv = lr.predict_proba(sp["val"][0].reshape(len(sp["val"][0]), -1))[:, 1]
best = max(np.arange(0.05, 0.96, 0.01), key=lambda t: f1_score(sp["val"][1], (pv >= t).astype(int)))
out["logreg_test"] = dict(thr=float(best), **m(y, (pl >= best).astype(int), pl))
out["lstm_test"] = m(y, pred, P["test"])
# per-device non-healthy rate by split
out["dev_rate"] = feat.groupby("device_name")["fault"].mean().round(3).to_dict()
json.dump(out, open("report/analysis.json", "w"), indent=1, default=float)
print(json.dumps(out, indent=1, default=float))

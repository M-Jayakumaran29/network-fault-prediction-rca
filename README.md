# AI-Based Network Fault Prediction and Root Cause Analysis System

A two-objective system over the **LCORE-D** dataset (*A Benchmark Dataset for Core
Network Analysis*, Mendeley Data, DOI [10.17632/77sztrg5ks.2](https://data.mendeley.com/datasets/77sztrg5ks/2), v2, CC BY 4.0):

1. **Fault Prediction** — an LSTM predicts whether a device is heading
   into a fault state, from a sliding window of its own recent metrics.
2. **Root Cause Analysis** — rule-based (no ML) by default (`RCA_METHOD = "rules"` in
   `config.py`). An optional ML fault-type classifier exists (`RCA_METHOD = "ml"`,
   see section 6b) but was disabled because its accuracy is low.

> A third stage, simulated self-healing, was built earlier and then removed from
> the project scope. Its code is kept, unused, in `_archive/self_healing/`.

A Flask + vanilla-JS dashboard replays a device's held-out test data
tick-by-tick through the pipeline so you can watch prediction → RCA
happen on real (never trained-on) rows.

> **Status of results in this document:** the pipeline has been run
> end-to-end against the real dataset during development (see the
> "Verified so far" note in each section). Headline accuracy/F1/ROC-AUC
> numbers for a full training run are written into
> `models/threshold.json` and `models/figures/` **only after you run
> `python -m fault_prediction.train_lstm` and `python -m
> fault_prediction.evaluate` yourself** — they are not hard-coded here.

---

## 1. What's actually in the dataset (read this before touching the code)

LCORE-D was inspected file-by-file before any feature/column was assumed
(see `preprocessing/data_loader.py` docstring for the full detail). The
short version:

- 7 CSVs, one per device (`CORE-R1`…`CORE-R6`, `EDGE-MS`), ~24k rows each,
  60-second sampling, with occasional monitoring gaps (up to ~90h).
- Each device has a **different number of interfaces** and the column
  names are inconsistently spaced/typo'd across files (`"B7_ Bits
  _received"` vs `"Bits_ received"`); two files even use different names
  for the common columns (`router_name` vs `Device_name`). All of this is
  normalized programmatically, not hand-mapped.
- `class` label: `H` (healthy, 73,593 rows), `T` (transient fault, not
  intentionally injected, 93,466 rows), `F` (hard/injected fault, 2,622
  rows), plus one stray `TH` row. **Objective 1's binary target is `fault =
  1 if class != 'H' else 0`.**
- `Bits_received`/`Bits_sent` are **not** cumulative SNMP counters (they
  are non-monotonic across time) — they are already per-interval values,
  so `throughput_bps = (bits_received + bits_sent) / 60`.
- `path_up` is constant `1` for every single row in the dataset — it
  cannot be used as a down/up signal, unlike the assignment brief's
  illustrative example rule assumed.
- `operational_status` is `1.0` (up) for 533,298 of 533,392 interface-rows
  and otherwise missing — it almost never reports "down" outright.
- The real `Fault Log` (81 events, 69 with a parseable ID) contains fault
  types **not** in the assignment brief's example list: `Misconfiguration`,
  `ICMP Blocked (Firewall)`, `SNMP agent failure`, alongside `Single/
  Multiple Link Failure`, `Routing Misconfiguration`, `Line card Failure`,
  `Node failure`. RCA's fault-type vocabulary matches these real labels.
- There is no explicit adjacency list. The 7-node topology used by RCA is
  **reconstructed** from `hop_to_core` / `hop_to_server` /
  `downstream_dependents` (see `rca/topology.py`):

  ```
  SERVER -- EDGE-MS -- CORE-R1(core) -- CORE-R2 -- CORE-R3 --+-- CORE-R4
                                                               +-- CORE-R5
                                                               +-- CORE-R6
  ```

---

## 2. Project structure

```
cn/
├── data/LCORE-D/            raw CSVs (downloaded from Mendeley) + Fault Log
├── data/processed/          device_features.csv written by preprocessing
├── preprocessing/
│   ├── data_loader.py        column normalization, raw CSV -> common/long frames
│   ├── feature_engineering.py  interface aggregation -> device-level features
│   └── preprocessing.py      segmenting, chronological split, imputation, scaling
├── fault_prediction/
│   ├── create_sequences.py   windowing (leakage-safe, gap-safe, device-safe)
│   ├── train_lstm.py         model definition + training
│   ├── evaluate.py           threshold selection (on val) + test metrics/plots
│   └── predict.py            inference helper (used by the backend)
├── rca/
│   ├── topology.py           reconstructed topology graph + graph helpers
│   ├── rules.py               individual rule functions
│   └── root_cause.py         orchestrates rules -> structured RCA result
├── backend/
│   ├── simulation.py         replays test-split rows through the full pipeline
│   └── app.py                Flask API + serves frontend/
├── presentation/             project slides (build_deck.py makes the .pptx)
├── _archive/self_healing/    removed Stage 3 code, kept for reference
├── frontend/                 dashboard (vanilla HTML/CSS/JS + Chart.js via CDN)
├── models/                   trained model, scaler, threshold, figures (generated)
├── config.py                 every tunable in one place (window size, threshold
│                              selection strategy, split fractions, paths, ...)
└── requirements.txt
```

`config.py` is the single place for the assignment's "must be configurable"
requirements: `WINDOW_SIZE`, `PREDICTION_HORIZON`, split fractions,
architecture sizes, etc.

---

## 3. Setup

```bash
cd cn
python -m venv .venv
.venv/Scripts/activate        # Windows
pip install -r requirements.txt
```

The dataset is already extracted under `data/LCORE-D/`. If you need to
re-download it: [Mendeley Data page](https://data.mendeley.com/datasets/77sztrg5ks/2) → "Download All" → unzip into `data/LCORE-D/` so you have
`data/LCORE-D/LCORE-D R1.csv` … `R7.csv` and `data/LCORE-D/Fault Log/FAULT_LOG.csv`.

---

## 4. Instructions to train the LSTM (Objective 1)

```bash
python -m fault_prediction.train_lstm
```

This runs the full pipeline: load → normalize → aggregate → segment →
chronological split (70/15/15 by **time**, not row count — see note below)
→ impute → scale (fit on train only) → build sequences → train with
EarlyStopping. It writes:

- `models/lstm_fault_model.keras` — the trained model
- `models/scaler.joblib` — the StandardScaler fit on the train split
- `models/model_metadata.json` — window size, horizon, feature list used
- `models/training_history.json` — per-epoch loss/accuracy/precision/recall/AUC

Then select the threshold and get test metrics:

```bash
python -m fault_prediction.evaluate
```

This scans thresholds on the **validation** set, picks the one maximizing
F1, writes it to `models/threshold.json` together with full validation and
test metrics (accuracy, precision, recall, F1, false-positive rate,
confusion matrix, ROC-AUC), and saves `models/figures/confusion_matrix.png`,
`roc_curve.png`, `training_curves.png`.

**Note on the 70/15/15 split:** the split cutoffs are computed on the
*time range*, not row index, and applied identically to every device (see
`preprocessing/preprocessing.py:chronological_split`). Because the dataset
has a large idle gap, the resulting row counts aren't exactly 70/15/15 —
that's expected for a time-based split and is what prevents any
train/val/test leakage.

Configurable knobs (in `config.py`): `WINDOW_SIZE` (default 10 steps = 10
minutes at the dataset's 60s resolution), `PREDICTION_HORIZON` (default 1
step ahead), `LSTM_UNITS`, `DROPOUT_RATE`, `BATCH_SIZE`, `MAX_EPOCHS`,
`EARLY_STOPPING_PATIENCE`, `TRAIN_FRAC`/`VAL_FRAC`/`TEST_FRAC`.

## 5. Instructions to run prediction standalone

```bash
python -m fault_prediction.predict
```

Loads the saved model/scaler/threshold and prints a fault-probability
prediction for the most recent window of one device, as a sanity check
outside the dashboard.

## 6. Instructions to test RCA standalone

```bash
python -m rca.root_cause
```

Computes each device's healthy baseline from the train split, then runs
the full rule engine on the first real `class == 'F'` row found in the
dataset and prints the structured RCA JSON (`fault_detected`,
`affected_device`, `affected_interface`, `probable_fault_type`,
`root_cause`, `evidence`, `confidence`). **Verified so far:** running this
against `CORE-R1`'s first hard-fault row correctly triggers the
`severe_icmp_loss` rule (100% ICMP loss vs a 0% baseline) end-to-end.

## 6b. ML-based RCA: training and (honest) results

```bash
python -m rca.train_ml_rca
```

Labels: each device-minute that is class T/F and falls inside a Fault Log
event window gets that event's fault type (the log has no device column, so
this is approximate); naturally occurring T minutes outside every window
become `transient_fault`. Split chronologically and by whole event.
Features (`rca/ml_features.py`) use metrics only -- never the H/T/F label.

Measured results (`models/ml_rca_report.json`):

| | Accuracy | Macro-F1 |
|---|---|---|
| Random forest, held-out later events (382 rows, 1-2 events/class) | 0.31 | 0.20 |
| Rule engine, same rows | 0.41 | 0.11 |
| Always guessing the most common type, same rows | 0.43 | - |
| Random forest, grouped 5-fold CV over all events (9 classes) | 0.22 | 0.16 |
| Always guessing the most common class (all events) | 0.19 | - |

**Conclusion:** neither rules nor ML name the Fault Log's fault type better than
simply guessing the most common type (43% on the later-event rows, 19% over all
events). The rules' 41% on those rows is mostly an artifact: they say "multiple link
failure" almost every time, which happens to be the most common label in that slice.
Nearly every fault minute hits 5 to 7 of the 7 devices at once, only 69 faults are
logged, and different fault types look alike in the metrics, so the shared-upstream
rule (rule 8) decides about 96% of diagnoses on real fault rows. Treat the exact fault
type as a weak suggestion; the evidence lines and the topology are the useful output.

## 7. Instructions to start the web dashboard

Train the model first (step 4), then:

```bash
python backend/app.py
```

Open `http://localhost:5000`. Use the device dropdown to pick which of the
7 devices to replay, **Step** to advance one 60-second tick at a time, or
**Play** to auto-advance. The dashboard is driven entirely by
`backend/simulation.py`, which replays that device's **held-out test
split** (rows the model never trained on) through
LSTM → threshold → RCA on every tick, so what you see is
the real trained model's behavior on real data, not scripted output.

---

## 9. Design notes / where each requirement was implemented

| Requirement | Where |
|---|---|
| Don't use `class` as an LSTM input | `config.LSTM_FEATURE_COLUMNS` excludes it; `feature_engineering.py` keeps it only as `class_raw`/`fault` (target) |
| Don't use `timestamp` as a numeric feature | used only for ordering/segmenting/splitting, never in `LSTM_FEATURE_COLUMNS` |
| Don't use topology fields in Objective 1 | `hop_to_core`/`hop_to_server`/`downstream_dependents` are carried through `preprocessing` for RCA only, never scaled/windowed for the LSTM |
| Don't randomly shuffle time-series / mix devices | `create_sequences.py` windows per `(device_name, segment_id)` group, in order, and only within one split |
| Configurable window size / threshold | `config.WINDOW_SIZE`, threshold selected in `evaluate.py` off validation data and stored, never derived from weights |
| Scalers fit on train only | `preprocessing.py:scale_features` |
| RCA method | Rule engine `rca/rules.py` (default). Optional ML typing in `rca/ml_rca.py` via `RCA_METHOD="ml"` (disabled, low accuracy) |
| Future ML-based RCA pluggable without touching Objective 1 | `rca/root_cause.py` only depends on a plain `metrics`/`interfaces` dict contract, not on `fault_prediction/*` internals |

---

## 10. Example output

Produced by `python -m rca.root_cause` against a real `class == 'F'` row
from `CORE-R1` (after the LSTM stage flags the device):

```json
{
  "fault_detected": true,
  "affected_device": "CORE-R1",
  "affected_interface": "u",
  "probable_fault_type": "link_failure",
  "root_cause": "CORE-R1, interface u (severe_icmp_loss)",
  "evidence": ["ICMP loss on CORE-R1 = 100.0% (severe, threshold 80.0%)."],
  "confidence": "medium (rule-based evidence level, not an ML probability)"
}
```

Full LSTM training/evaluation metrics (accuracy, precision, recall, F1,
confusion matrix, ROC-AUC) are written to `models/threshold.json` and
`models/figures/` when you run step 4 above -- see that file for the
actual numbers from your training run rather than a number pasted here.

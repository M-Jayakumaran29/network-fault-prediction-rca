"""
Central configuration for the AI-Based Network Fault Prediction, Root Cause Analysis system. Values here were chosen after inspecting the actual
LCORE-D dataset (see preprocessing/data_loader.py for the inspection-derived
column mapping) -- nothing here is guessed ahead of inspection.
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "LCORE-D")
FAULT_LOG_PATH = os.path.join(DATA_DIR, "Fault Log", "FAULT_LOG.csv")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")

os.makedirs(MODELS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Data resolution facts (measured from the dataset, not assumed):
#   - Sampling interval: 60 seconds (median gap between consecutive rows).
#   - Large gaps (session breaks) exist -- up to ~90 hours -- so sequences
#     must never be built across a gap. See preprocessing.segment_contiguous.
# ---------------------------------------------------------------------------
EXPECTED_INTERVAL_SECONDS = 60
MAX_ALLOWED_GAP_SECONDS = 60  # a gap > this breaks a contiguous segment

# ---------------------------------------------------------------------------
# Stage 1: LSTM fault prediction
# ---------------------------------------------------------------------------
WINDOW_SIZE = 10          # number of 60s steps of history fed to the LSTM (10 min)
PREDICTION_HORIZON = 1    # predict `class` this many steps AFTER the window
                           # (1 step = 60s ahead). Configurable per assignment rules.

TRAIN_FRAC = 0.70
VAL_FRAC = 0.15
TEST_FRAC = 0.15

LSTM_UNITS = 64
DROPOUT_RATE = 0.3
DENSE_UNITS = 32
BATCH_SIZE = 64
MAX_EPOCHS = 60
EARLY_STOPPING_PATIENCE = 6
LEARNING_RATE = 1e-3

# Fault probability threshold. This is NOT derived from the network's
# weights -- it is selected on the validation set after training by
# scanning thresholds and maximising F1 (see fault_prediction/evaluate.py),
# then held fixed for validation/test/inference.
DEFAULT_THRESHOLD = 0.5  # overwritten by the value learned in models/threshold.json

# Input feature list for the LSTM (device-level, aggregated across that
# device's interfaces). Chosen strictly from the candidate features in the
# assignment brief; `class`, `timestamp` and topology fields are excluded.
LSTM_FEATURE_COLUMNS = [
    "icmp_loss",            # Packet Loss (%)
    "icmp_response_time",   # Latency (ms)
    "throughput_bps",       # derived Throughput (bits/s)
    "discards_total",       # Packets Discarded (in+out, all interfaces)
    "errors_total",         # Packets With Errors (in+out, all interfaces)
    "oper_status_up_frac",  # Operational Status, encoded as fraction of
                             # this device's interfaces reporting "up"
]

# ---------------------------------------------------------------------------
# Objective 2: Root cause analysis
# ---------------------------------------------------------------------------
# Devices as found in the dataset (file -> device name), used to build the
# topology graph. See rca/topology.py for how hop_to_core / hop_to_server /
# downstream_dependents were used to reconstruct the adjacency.
DEVICE_FILES = {
    "CORE-R1": "LCORE-D R1.csv",
    "CORE-R2": "LCORE-D R2.csv",
    "CORE-R3": "LCORE-D R3.csv",
    "CORE-R4": "LCORE-D R4.csv",
    "CORE-R5": "LCORE-D R5.csv",
    "CORE-R6": "LCORE-D R6.csv",
    "EDGE-MS": "LCORE-D R7.csv",
}

# "ml" -> trained classifier picks the fault type (falls back to rules if the
# model file is missing); "rules" -> original rule-based fault typing.
RCA_METHOD = "rules"

RANDOM_SEED = 42

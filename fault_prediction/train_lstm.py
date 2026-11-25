"""
Trains the Stage-1 LSTM fault predictor.

Architecture (per the assignment brief):
    Input sequence -> LSTM -> Dropout -> Dense -> Sigmoid -> fault probability

Loss: Binary Cross-Entropy. Optimizer: Adam. Callback: EarlyStopping on
validation loss (restores best weights). The classification threshold is
NOT touched here -- it is selected afterwards on the validation set by
fault_prediction/evaluate.py and then held fixed.
"""
import os
import json
import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

import config
from preprocessing.preprocessing import run_preprocessing
from fault_prediction.create_sequences import build_all_splits, scaled_feature_columns

MODEL_PATH = os.path.join(config.MODELS_DIR, "lstm_fault_model.keras")
HISTORY_PATH = os.path.join(config.MODELS_DIR, "training_history.json")
METADATA_PATH = os.path.join(config.MODELS_DIR, "model_metadata.json")


def build_model(window_size: int, n_features: int) -> keras.Model:
    model = keras.Sequential([
        layers.Input(shape=(window_size, n_features)),
        layers.LSTM(config.LSTM_UNITS),
        layers.Dropout(config.DROPOUT_RATE),
        layers.Dense(config.DENSE_UNITS, activation="relu"),
        layers.Dense(1, activation="sigmoid"),
    ])
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=config.LEARNING_RATE),
        loss="binary_crossentropy",
        metrics=[
            keras.metrics.BinaryAccuracy(name="accuracy"),
            keras.metrics.Precision(name="precision"),
            keras.metrics.Recall(name="recall"),
            keras.metrics.AUC(name="auc"),
        ],
    )
    return model


def train(window_size=config.WINDOW_SIZE, horizon=config.PREDICTION_HORIZON, save=True):
    tf.random.set_seed(config.RANDOM_SEED)
    np.random.seed(config.RANDOM_SEED)

    feat, scaler = run_preprocessing(save=save)
    splits = build_all_splits(feat, window_size=window_size, horizon=horizon)
    X_train, y_train, _ = splits["train"]
    X_val, y_val, _ = splits["val"]
    X_test, y_test, _ = splits["test"]

    print(f"Train: {X_train.shape}, Val: {X_val.shape}, Test: {X_test.shape}")

    n_features = X_train.shape[2]
    model = build_model(window_size, n_features)
    model.summary()

    # mild class weighting in case a given window/horizon combination
    # produces an imbalanced split (measured on the fly, not assumed)
    fault_frac = y_train.mean()
    class_weight = None
    if 0 < fault_frac < 1:
        class_weight = {
            0: 0.5 / (1 - fault_frac),
            1: 0.5 / fault_frac,
        }

    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=config.EARLY_STOPPING_PATIENCE,
            restore_best_weights=True,
        ),
    ]

    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=config.MAX_EPOCHS,
        batch_size=config.BATCH_SIZE,
        class_weight=class_weight,
        callbacks=callbacks,
        verbose=2,
    )

    if save:
        model.save(MODEL_PATH)
        with open(HISTORY_PATH, "w") as f:
            json.dump({k: [float(x) for x in v] for k, v in history.history.items()}, f, indent=2)
        with open(METADATA_PATH, "w") as f:
            json.dump({
                "window_size": window_size,
                "horizon": horizon,
                "feature_columns": config.LSTM_FEATURE_COLUMNS,
                "scaled_feature_columns": scaled_feature_columns(),
                "n_features": n_features,
                "train_fault_frac": float(fault_frac),
            }, f, indent=2)
        print(f"Saved model -> {MODEL_PATH}")
        print(f"Saved training history -> {HISTORY_PATH}")
        print(f"Saved model metadata -> {METADATA_PATH}")

    return model, history, splits


if __name__ == "__main__":
    train()

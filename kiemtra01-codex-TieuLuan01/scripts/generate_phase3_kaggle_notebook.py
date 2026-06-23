import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = ROOT / "notebooks" / "phase3_kaggle_training_2a.ipynb"


def _source(text):
    text = text.strip("\n")
    if not text:
        return []
    return [f"{line}\n" for line in text.splitlines()]


def _markdown_cell(text):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": _source(text),
    }


def _code_cell(text):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": _source(text),
    }


def build_notebook():
    cells = [
        _markdown_cell(
            """
# Phase 3 - Kaggle Training for 2a

This notebook trains and compares three TensorFlow/Keras sequence models on `data_user500.csv`:

- `RNN`
- `LSTM`
- `biLSTM`

The pipeline is intentionally independent from the Django runtime:

- input: `data_user500.csv`
- default sequence length: `5`
- per-event features: `behavior_type`, `category_slug`, `price_bucket`, `device_type`
- target: `target_next_category_slug`
- same split, same preprocess, same training loop shape for all three models

Expected outputs:

- `model_rnn.keras`
- `model_lstm.keras`
- `model_bilstm.keras`
- `model_best.keras`
- `metrics_comparison.csv`
- `confusion_matrix_rnn.png`
- `confusion_matrix_lstm.png`
- `confusion_matrix_bilstm.png`
- `history_rnn.png`
- `history_lstm.png`
- `history_bilstm.png`
- `model_best_reason.txt`
- `tokenizer_or_vocab.json`
- `label_encoder.json`
"""
        ),
        _code_cell(
            """
import json
import os
import shutil
from pathlib import Path
from time import perf_counter

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

SEED = 20260420
SEQUENCE_LENGTH = 5
BATCH_SIZE = 128
MAX_EPOCHS = 25
BEST_TIE_TOLERANCE = 0.002
OUTPUT_DIR = Path("/kaggle/working/phase3_artifacts")
LOCAL_FALLBACK_DATASET = Path("/kaggle/input/data_user500/data_user500.csv")

OFFICIAL_BEHAVIOR_TYPES = [
    "search",
    "view_product",
    "chatbot_ask",
    "save_item",
    "compare_item",
    "add_to_cart",
    "checkout",
    "pay_order",
]

OFFICIAL_CATEGORY_SLUGS = [
    "business-laptops",
    "gaming-laptops",
    "ultrabooks",
    "smartphones",
    "tablets",
    "smartwatches",
    "audio",
    "keyboards-mice",
    "chargers-cables",
    "bags-stands",
]

PRICE_BUCKETS = [
    "under_500",
    "500_1000",
    "1000_2000",
    "above_2000",
    "unknown",
]

DEVICE_TYPES = [
    "desktop",
    "mobile",
    "tablet",
    "unknown",
]

DATASET_COLUMNS = [
    "user_ref",
    "event_ts",
    "step_index",
    "behavior_type",
    "category_slug",
    "product_id",
    "price_bucket",
    "device_type",
    "search_query",
    "session_id",
    "target_next_category_slug",
]

FEATURE_COLUMNS = [
    "behavior_type",
    "category_slug",
    "price_bucket",
    "device_type",
]

FEATURE_VOCABS = {
    "behavior_type": OFFICIAL_BEHAVIOR_TYPES,
    "category_slug": [""] + OFFICIAL_CATEGORY_SLUGS,
    "price_bucket": PRICE_BUCKETS,
    "device_type": DEVICE_TYPES,
}

LABEL_VOCAB = OFFICIAL_CATEGORY_SLUGS
MODEL_OUTPUT_FILENAMES = {
    "rnn": "model_rnn.keras",
    "lstm": "model_lstm.keras",
    "bilstm": "model_bilstm.keras",
}
MODEL_SIMPLICITY_RANK = {"rnn": 0, "lstm": 1, "bilstm": 2}
EMBED_DIMS = {
    "behavior_type": 8,
    "category_slug": 12,
    "price_bucket": 6,
    "device_type": 4,
}

tf.keras.utils.set_random_seed(SEED)
try:
    tf.config.experimental.enable_op_determinism()
except Exception:
    pass

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
pd.set_option("display.max_columns", None)
"""
        ),
        _code_cell(
            """
def discover_dataset_path():
    kaggle_candidates = sorted(Path("/kaggle/input").glob("**/data_user500.csv"))
    if kaggle_candidates:
        return kaggle_candidates[0]
    local_candidates = [
        LOCAL_FALLBACK_DATASET,
        Path("/kaggle/working/data_user500.csv"),
        Path("services/chatbot_service/chatbot/artifacts/data_user500.csv"),
        Path("data_user500.csv"),
    ]
    for candidate in local_candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find data_user500.csv in /kaggle/input or local fallback paths.")


def normalize_feature_value(feature_name, value):
    value = "" if pd.isna(value) else str(value)
    if feature_name == "category_slug":
        return value if value in FEATURE_VOCABS[feature_name] else ""
    if feature_name in {"behavior_type", "price_bucket", "device_type"}:
        return value if value in FEATURE_VOCABS[feature_name] else "[OOV]"
    return value


def validate_dataset_contract(df):
    normalized_df = df.fillna("")

    if list(normalized_df.columns) != DATASET_COLUMNS:
        raise ValueError(
            "Unexpected CSV columns. Expected exact order:\\n"
            + ", ".join(DATASET_COLUMNS)
            + "\\nGot:\\n"
            + ", ".join(normalized_df.columns.tolist())
        )

    invalid_behaviors = sorted(set(normalized_df["behavior_type"]) - set(OFFICIAL_BEHAVIOR_TYPES))
    invalid_price_buckets = sorted(set(normalized_df["price_bucket"]) - set(PRICE_BUCKETS))
    invalid_devices = sorted(set(normalized_df["device_type"]) - set(DEVICE_TYPES))
    allowed_category_values = set([""] + OFFICIAL_CATEGORY_SLUGS)
    invalid_feature_categories = sorted(set(normalized_df["category_slug"]) - allowed_category_values)
    invalid_targets = sorted(
        set(normalized_df["target_next_category_slug"]) - set([""] + OFFICIAL_CATEGORY_SLUGS)
    )

    problems = []
    if invalid_behaviors:
        problems.append(f"Invalid behavior_type values: {invalid_behaviors}")
    if invalid_price_buckets:
        problems.append(f"Invalid price_bucket values: {invalid_price_buckets}")
    if invalid_devices:
        problems.append(f"Invalid device_type values: {invalid_devices}")
    if invalid_feature_categories:
        problems.append(f"Invalid category_slug values: {invalid_feature_categories}")
    if invalid_targets:
        problems.append(f"Invalid target_next_category_slug values: {invalid_targets}")
    if problems:
        raise ValueError("\\n".join(problems))


def add_session_key(df):
    df = df.copy()
    df["session_key"] = df["user_ref"].astype(str) + "||" + df["session_id"].astype(str)
    return df


def build_session_manifest(supervised_df):
    manifest_rows = []
    for session_key, group in supervised_df.groupby("session_key", sort=True):
        target_counts = group["target_next_category_slug"].value_counts()
        session_label = target_counts.idxmax()
        manifest_rows.append(
            {
                "session_key": session_key,
                "session_label": session_label,
                "sample_count": int(len(group)),
            }
        )
    manifest = pd.DataFrame(manifest_rows).sort_values("session_key").reset_index(drop=True)
    if manifest.empty:
        raise ValueError("No supervised rows found after filtering target_next_category_slug.")
    return manifest


def maybe_stratify(frame, column_name):
    value_counts = frame[column_name].value_counts()
    if value_counts.empty or value_counts.min() < 2:
        return None
    return frame[column_name]


def split_session_keys(session_manifest, seed=SEED):
    train_frame, temp_frame = train_test_split(
        session_manifest,
        test_size=0.30,
        random_state=seed,
        stratify=maybe_stratify(session_manifest, "session_label"),
    )
    val_frame, test_frame = train_test_split(
        temp_frame,
        test_size=0.50,
        random_state=seed,
        stratify=maybe_stratify(temp_frame, "session_label"),
    )
    return (
        set(train_frame["session_key"]),
        set(val_frame["session_key"]),
        set(test_frame["session_key"]),
    )


def build_supervised_sequences(df, session_keys):
    selected = df[df["session_key"].isin(session_keys)].copy()
    feature_sequences = {feature_name: [] for feature_name in FEATURE_COLUMNS}
    labels = []

    for _, group in selected.groupby("session_key", sort=True):
        rows = group.to_dict("records")
        for index, row in enumerate(rows):
            target_value = str(row["target_next_category_slug"])
            if not target_value:
                continue

            window_rows = rows[max(0, index - SEQUENCE_LENGTH + 1) : index + 1]
            pad_count = SEQUENCE_LENGTH - len(window_rows)

            for feature_name in FEATURE_COLUMNS:
                padded_values = ["[PAD]"] * pad_count
                padded_values.extend(
                    normalize_feature_value(feature_name, event_row.get(feature_name, ""))
                    for event_row in window_rows
                )
                feature_sequences[feature_name].append(padded_values)

            labels.append(target_value)

    if not labels:
        raise ValueError("No training samples were generated for the requested split.")
    return feature_sequences, labels


def describe_split(name, labels):
    label_counts = pd.Series(labels).value_counts().sort_index()
    summary = {
        "split": name,
        "samples": int(len(labels)),
        "label_distribution": label_counts.to_dict(),
    }
    return summary
"""
        ),
        _code_cell(
            """
def build_feature_index(vocab_values):
    index = {"[PAD]": 0, "[OOV]": 1}
    for token in vocab_values:
        if token not in index:
            index[token] = len(index)
    return index


FEATURE_INDEXES = {
    feature_name: build_feature_index(vocab_values)
    for feature_name, vocab_values in FEATURE_VOCABS.items()
}
LABEL_TO_ID = {label: index for index, label in enumerate(LABEL_VOCAB)}
ID_TO_LABEL = {index: label for label, index in LABEL_TO_ID.items()}


def encode_feature_sequences(feature_sequences):
    encoded = {}
    for feature_name, sequences in feature_sequences.items():
        feature_index = FEATURE_INDEXES[feature_name]
        encoded[feature_name] = np.asarray(
            [
                [feature_index.get(token, feature_index["[OOV]"]) for token in sequence]
                for sequence in sequences
            ],
            dtype=np.int32,
        )
    return encoded


def encode_labels(labels):
    return np.asarray([LABEL_TO_ID[label] for label in labels], dtype=np.int32)


def export_vocab_metadata(output_dir):
    tokenizer_payload = {
        "sequence_length": SEQUENCE_LENGTH,
        "feature_order": FEATURE_COLUMNS,
        "features": {},
    }
    for feature_name, vocab_values in FEATURE_VOCABS.items():
        tokenizer_payload["features"][feature_name] = {
            "pad_token": "[PAD]",
            "oov_token": "[OOV]",
            "vocab": vocab_values,
            "index": FEATURE_INDEXES[feature_name],
        }

    label_payload = {
        "label_name": "target_next_category_slug",
        "labels": LABEL_VOCAB,
        "index": LABEL_TO_ID,
    }

    (output_dir / "tokenizer_or_vocab.json").write_text(
        json.dumps(tokenizer_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    (output_dir / "label_encoder.json").write_text(
        json.dumps(label_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
"""
        ),
        _code_cell(
            """
def make_model_inputs(encoded_features):
    return {feature_name: encoded_features[feature_name] for feature_name in FEATURE_COLUMNS}


def recurrent_backbone(backbone_name):
    if backbone_name == "rnn":
        return tf.keras.layers.SimpleRNN(64, dropout=0.20, name="recurrent")
    if backbone_name == "lstm":
        return tf.keras.layers.LSTM(64, dropout=0.20, name="recurrent")
    if backbone_name == "bilstm":
        return tf.keras.layers.Bidirectional(
            tf.keras.layers.LSTM(64, dropout=0.20),
            name="recurrent",
        )
    raise ValueError(f"Unsupported backbone: {backbone_name}")


def build_model(backbone_name):
    inputs = []
    embedded_tensors = []
    reference_input = None

    for feature_name in FEATURE_COLUMNS:
        input_layer = tf.keras.Input(
            shape=(SEQUENCE_LENGTH,),
            dtype="int32",
            name=feature_name,
        )
        embedding_layer = tf.keras.layers.Embedding(
            input_dim=len(FEATURE_INDEXES[feature_name]),
            output_dim=EMBED_DIMS[feature_name],
            mask_zero=False,
            name=f"{feature_name}_embedding",
        )(input_layer)
        inputs.append(input_layer)
        embedded_tensors.append(embedding_layer)
        if reference_input is None:
            reference_input = input_layer

    merged = tf.keras.layers.Concatenate(axis=-1, name="merge_features")(embedded_tensors)
    padding_mask = tf.keras.layers.Lambda(
        lambda x: tf.cast(tf.not_equal(x, 0), tf.float32),
        name="padding_mask",
    )(reference_input)
    padding_mask = tf.keras.layers.Lambda(
        lambda x: tf.expand_dims(x, axis=-1),
        name="padding_mask_expand",
    )(padding_mask)
    merged = tf.keras.layers.Multiply(name="apply_padding_mask")([merged, padding_mask])
    encoded = recurrent_backbone(backbone_name)(merged)
    encoded = tf.keras.layers.Dense(64, activation="relu", name="dense")(encoded)
    encoded = tf.keras.layers.Dropout(0.20, name="dropout")(encoded)
    output_layer = tf.keras.layers.Dense(
        len(LABEL_VOCAB),
        activation="softmax",
        name="target_next_category_slug",
    )(encoded)

    model = tf.keras.Model(inputs=inputs, outputs=output_layer, name=f"{backbone_name}_sequence_model")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def compute_macro_metrics(y_true, y_pred):
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_precision": float(
            precision_score(y_true, y_pred, average="macro", zero_division=0)
        ),
        "macro_recall": float(
            recall_score(y_true, y_pred, average="macro", zero_division=0)
        ),
        "macro_f1": float(
            f1_score(y_true, y_pred, average="macro", zero_division=0)
        ),
    }


def plot_history(history, title, output_path):
    history_frame = pd.DataFrame(history.history)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    axes[0].plot(history_frame["loss"], label="train_loss")
    axes[0].plot(history_frame["val_loss"], label="val_loss")
    axes[0].set_title(f"{title} Loss")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].legend()

    axes[1].plot(history_frame["accuracy"], label="train_accuracy")
    axes[1].plot(history_frame["val_accuracy"], label="val_accuracy")
    axes[1].set_title(f"{title} Accuracy")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Accuracy")
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_confusion(y_true, y_pred, title, output_path):
    matrix = confusion_matrix(y_true, y_pred, labels=list(range(len(LABEL_VOCAB))))
    fig, ax = plt.subplots(figsize=(10, 8))
    display = ConfusionMatrixDisplay(confusion_matrix=matrix, display_labels=LABEL_VOCAB)
    display.plot(ax=ax, cmap="Blues", colorbar=False, xticks_rotation=45)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def training_callbacks():
    return [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=5,
            restore_best_weights=True,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=2,
            min_lr=1e-5,
        ),
    ]
"""
        ),
        _code_cell(
            """
dataset_path = discover_dataset_path()
print(f"Dataset path: {dataset_path}")

raw_df = pd.read_csv(dataset_path, keep_default_na=False)
validate_dataset_contract(raw_df)

df = raw_df.fillna("").copy()
df["event_ts"] = pd.to_datetime(df["event_ts"], utc=True)
df["step_index"] = df["step_index"].astype(int)
df = df.sort_values(["user_ref", "session_id", "event_ts", "step_index"]).reset_index(drop=True)
df = add_session_key(df)

supervised_df = df[df["target_next_category_slug"].astype(str) != ""].copy()
session_manifest = build_session_manifest(supervised_df)
train_keys, val_keys, test_keys = split_session_keys(session_manifest)

train_sequences, train_labels = build_supervised_sequences(df, train_keys)
val_sequences, val_labels = build_supervised_sequences(df, val_keys)
test_sequences, test_labels = build_supervised_sequences(df, test_keys)

X_train = encode_feature_sequences(train_sequences)
X_val = encode_feature_sequences(val_sequences)
X_test = encode_feature_sequences(test_sequences)
y_train = encode_labels(train_labels)
y_val = encode_labels(val_labels)
y_test = encode_labels(test_labels)

train_inputs = make_model_inputs(X_train)
val_inputs = make_model_inputs(X_val)
test_inputs = make_model_inputs(X_test)

class_weights_array = compute_class_weight(
    class_weight="balanced",
    classes=np.unique(y_train),
    y=y_train,
)
class_weight = {
    int(label_id): float(weight)
    for label_id, weight in zip(np.unique(y_train), class_weights_array)
}

export_vocab_metadata(OUTPUT_DIR)

split_overview = [
    describe_split("train", train_labels),
    describe_split("validation", val_labels),
    describe_split("test", test_labels),
]

print(pd.DataFrame(split_overview))
print("Train shapes:", {name: values.shape for name, values in X_train.items()}, y_train.shape)
print("Validation shapes:", {name: values.shape for name, values in X_val.items()}, y_val.shape)
print("Test shapes:", {name: values.shape for name, values in X_test.items()}, y_test.shape)
"""
        ),
        _code_cell(
            """
results = []

for model_name in ["rnn", "lstm", "bilstm"]:
    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(SEED)

    model = build_model(model_name)
    start_time = perf_counter()
    history = model.fit(
        train_inputs,
        y_train,
        validation_data=(val_inputs, y_val),
        epochs=MAX_EPOCHS,
        batch_size=BATCH_SIZE,
        class_weight=class_weight,
        verbose=2,
        callbacks=training_callbacks(),
    )
    elapsed_seconds = perf_counter() - start_time

    model_path = OUTPUT_DIR / MODEL_OUTPUT_FILENAMES[model_name]
    model.save(model_path)

    y_pred = np.argmax(model.predict(test_inputs, verbose=0), axis=1)
    metrics = compute_macro_metrics(y_test, y_pred)

    plot_history(
        history,
        title=model_name.upper(),
        output_path=OUTPUT_DIR / f"history_{model_name}.png",
    )
    plot_confusion(
        y_test,
        y_pred,
        title=f"{model_name.upper()} Confusion Matrix",
        output_path=OUTPUT_DIR / f"confusion_matrix_{model_name}.png",
    )

    result_row = {
        "model_name": model_name,
        "accuracy": round(metrics["accuracy"], 6),
        "macro_precision": round(metrics["macro_precision"], 6),
        "macro_recall": round(metrics["macro_recall"], 6),
        "macro_f1": round(metrics["macro_f1"], 6),
        "params": int(model.count_params()),
        "best_epoch": int(np.argmin(history.history["val_loss"]) + 1),
        "best_val_loss": round(float(np.min(history.history["val_loss"])), 6),
        "best_val_accuracy": round(float(np.max(history.history["val_accuracy"])), 6),
        "training_seconds": round(float(elapsed_seconds), 2),
        "artifact_model": model_path.name,
    }
    results.append(result_row)

metrics_df = pd.DataFrame(results).sort_values(
    ["macro_f1", "macro_precision", "accuracy", "params"],
    ascending=[False, False, False, True],
).reset_index(drop=True)

metrics_df["is_best"] = False
metrics_df.to_csv(OUTPUT_DIR / "metrics_comparison.csv", index=False)
metrics_df
"""
        ),
        _code_cell(
            """
max_macro_f1 = metrics_df["macro_f1"].max()
best_candidates = metrics_df[
    metrics_df["macro_f1"] >= (max_macro_f1 - BEST_TIE_TOLERANCE)
].copy()
best_candidates["simplicity_rank"] = best_candidates["model_name"].map(MODEL_SIMPLICITY_RANK)
best_row = best_candidates.sort_values(
    ["params", "simplicity_rank", "model_name"],
    ascending=[True, True, True],
).iloc[0]

best_model_name = best_row["model_name"]
best_model_source_path = OUTPUT_DIR / MODEL_OUTPUT_FILENAMES[best_model_name]
best_model_path = OUTPUT_DIR / "model_best.keras"
shutil.copy2(best_model_source_path, best_model_path)

metrics_df["is_best"] = metrics_df["model_name"] == best_model_name
metrics_df.to_csv(OUTPUT_DIR / "metrics_comparison.csv", index=False)

winner_row = metrics_df.loc[metrics_df["model_name"] == best_model_name].iloc[0]
reason_lines = [
    f"Selected model_best: {best_model_name}",
    f"Selection rule: prioritize macro F1, then prefer lighter/simple models when macro F1 gap <= {BEST_TIE_TOLERANCE:.3f}.",
    f"Winner macro F1: {winner_row['macro_f1']:.6f}",
    f"Winner accuracy: {winner_row['accuracy']:.6f}",
    f"Winner macro precision: {winner_row['macro_precision']:.6f}",
    f"Winner macro recall: {winner_row['macro_recall']:.6f}",
    f"Winner params: {int(winner_row['params'])}",
]

if len(best_candidates) > 1:
    reason_lines.append("Multiple models were within the tie tolerance, so model size and inference simplicity were used as the final tie-break.")
else:
    reason_lines.append("This model had the strongest macro F1 on the held-out test split, so it wins directly.")

(OUTPUT_DIR / "model_best_reason.txt").write_text(
    "\\n".join(reason_lines) + "\\n",
    encoding="utf-8",
)

print(metrics_df)
print("\\nGenerated files:")
for path in sorted(OUTPUT_DIR.iterdir()):
    print("-", path.name)
"""
        ),
        _markdown_cell(
            """
## Download checklist

After the notebook finishes:

1. Download every file from `/kaggle/working/phase3_artifacts/`.
2. Copy the files into `services/chatbot_service/chatbot/artifacts/` in the repo.
3. Keep the filenames unchanged so Phase 5 runtime integration can load them later without a Kaggle dependency.
"""
        ),
    ]

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.10",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main():
    notebook = build_notebook()
    NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTEBOOK_PATH.write_text(json.dumps(notebook, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"Wrote {NOTEBOOK_PATH}")


if __name__ == "__main__":
    main()

import json
import math
import tempfile
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .category_taxonomy import category_items, detect_category_matches, fetch_catalog_categories
from .models import BehaviorEvent

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_BEHAVIOR_PATH = ARTIFACT_DIR / "model_behavior.json"
TRAINING_DATA_PATH = ARTIFACT_DIR / "training_data_behavior.json"
MODEL_BEST_PATH = ARTIFACT_DIR / "model_best.keras"
LABEL_ENCODER_PATH = ARTIFACT_DIR / "label_encoder.json"
TOKENIZER_VOCAB_PATH = ARTIFACT_DIR / "tokenizer_or_vocab.json"
MODEL_BEST_REASON_PATH = ARTIFACT_DIR / "model_best_reason.txt"

_MODEL_BEST_LOADER = None
_MODEL_BEST_SIGNATURE = None
_DEVICE_HINTS_BY_CATEGORY = {
    "business-laptops": "desktop",
    "gaming-laptops": "desktop",
    "ultrabooks": "desktop",
    "smartphones": "mobile",
    "tablets": "tablet",
    "smartwatches": "mobile",
    "audio": "mobile",
    "keyboards-mice": "desktop",
    "chargers-cables": "mobile",
    "bags-stands": "mobile",
}


def _ensure_artifact_dir():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_decimal(value, default="0"):
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return Decimal(default)


def _price_bucket(value):
    amount = _safe_decimal(value)
    if amount <= 0:
        return "unknown"
    if amount < 500:
        return "under_500"
    if amount < 1000:
        return "500_1000"
    if amount < 2000:
        return "1000_2000"
    return "above_2000"


def _normalize_device_type(value):
    normalized = str(value or "").strip().lower()
    if normalized in {"desktop", "mobile", "tablet"}:
        return normalized
    return "unknown"


def _category_hint_from_question(question, categories):
    matches = detect_category_matches(question or "", categories=categories)
    return matches[0] if matches else ""


def _infer_device_type(current_product=None, user_context=None):
    current_product = current_product or {}
    user_context = user_context or {}
    category_slug = str(current_product.get("category_slug") or current_product.get("service") or "").strip().lower()
    if category_slug in _DEVICE_HINTS_BY_CATEGORY:
        return _DEVICE_HINTS_BY_CATEGORY[category_slug]

    combined = " ".join(
        str(item or "")
        for key in ["cart_items", "saved_items", "recent_paid_items"]
        for item in (user_context.get(key) or [])
    ).lower()
    if "tablet" in combined or "ipad" in combined:
        return "tablet"
    if any(token in combined for token in ["phone", "mobile", "watch", "earbuds", "headphones", "charger", "cable"]):
        return "mobile"
    if any(token in combined for token in ["laptop", "desktop", "keyboard", "mouse", "monitor"]):
        return "desktop"
    return "unknown"


def _catalog_categories(extra_slugs=None, model_categories=None):
    seed_categories = category_items(fetch_catalog_categories())
    allowed_slugs = {item["slug"] for item in seed_categories}
    normalized_model_categories = [
        item
        for item in (model_categories or [])
        if str((item or {}).get("slug") or "").strip().lower() in allowed_slugs
    ]
    event_slugs = list(
        BehaviorEvent.objects.exclude(category_slug="")
        .values_list("category_slug", flat=True)
        .distinct()
    )
    valid_extra_slugs = [
        str(slug or "").strip().lower()
        for slug in [*(extra_slugs or []), *event_slugs]
        if str(slug or "").strip().lower() in allowed_slugs
    ]
    return category_items(seed_categories + normalized_model_categories, extra_slugs=valid_extra_slugs)


def record_behavior_event(user_ref, message, current_product=None, user_context=None):
    user_ref = str(user_ref or "").strip() or "anonymous"
    current_product = current_product or {}
    user_context = user_context or {}
    category_slug = str(current_product.get("category_slug") or current_product.get("service") or "").strip().lower()
    device_type = _infer_device_type(current_product=current_product, user_context=user_context)
    price_bucket = _price_bucket(current_product.get("price"))

    BehaviorEvent.objects.create(
        user_ref=user_ref,
        event_type=BehaviorEvent.EVENT_CHATBOT_ASK,
        category_slug=category_slug[:120],
        product_id=max(0, _safe_int(current_product.get("id"), 0)),
        metadata={
            "message": str(message or "")[:500],
            "current_category_slug": category_slug[:120],
            "cart_items_count": len(user_context.get("cart_items") or []),
            "saved_items_count": len(user_context.get("saved_items") or []),
            "recent_paid_items_count": len(user_context.get("recent_paid_items") or []),
            "device_type": device_type,
            "price_bucket": price_bucket,
        },
    )


def _score_event(event, categories):
    metadata = event.metadata or {}
    category_scores = {item["slug"]: 0.0 for item in categories}
    for category_slug in detect_category_matches(metadata.get("message") or "", categories=categories):
        category_scores[category_slug] += 2.0

    current_category_slug = str(metadata.get("current_category_slug") or event.category_slug or "").strip().lower()
    if current_category_slug in category_scores:
        category_scores[current_category_slug] += 3.0

    cart_count = _safe_int(metadata.get("cart_items_count"), 0)
    saved_count = _safe_int(metadata.get("saved_items_count"), 0)
    paid_count = _safe_int(metadata.get("recent_paid_items_count"), 0)
    if current_category_slug in category_scores:
        category_scores[current_category_slug] += min(4.0, cart_count * 0.2 + saved_count * 0.15 + paid_count * 0.25)
    return category_scores


def _history_scores(user_ref, categories):
    scores = {item["slug"]: 0.0 for item in categories}
    events = list(BehaviorEvent.objects.filter(user_ref=user_ref).order_by("-id")[:400])
    for event in events:
        event_scores = _score_event(event, categories)
        for slug, value in event_scores.items():
            scores[slug] += value
    return scores, len(events)


def _normalize_probabilities(scores):
    total = sum(max(0.0, value) for value in scores.values())
    if total <= 0:
        base = 1.0 / max(1, len(scores))
        return {slug: round(base, 4) for slug in scores}
    return {slug: round(max(0.0, value) / total, 4) for slug, value in scores.items()}


def _build_training_samples():
    categories = _catalog_categories()
    user_refs = list(BehaviorEvent.objects.values_list("user_ref", flat=True).distinct())
    samples = []
    global_scores = {item["slug"]: 0.0 for item in categories}
    for user_ref in user_refs:
        scores, event_count = _history_scores(user_ref, categories)
        if sum(scores.values()) <= 0:
            continue
        for slug, value in scores.items():
            global_scores[slug] += value
        dominant_slug = max(scores, key=scores.get)
        samples.append(
            {
                "user_ref": user_ref,
                "event_count": event_count,
                "category_affinity": _normalize_probabilities(scores),
                "dominant_category_slug": dominant_slug,
            }
        )
    return samples, global_scores, len(user_refs), categories


def train_and_save_behavior_model():
    samples, global_scores, distinct_users, categories = _build_training_samples()
    priors = _normalize_probabilities(global_scores)
    payload = {
        "version": 3,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "categories": categories,
        "priors": priors,
        "metrics": {
            "samples": len(samples),
            "distinct_users": distinct_users,
            "total_events": BehaviorEvent.objects.count(),
            "category_count": len(categories),
            "loss": None,
        },
    }

    training_payload = {
        "version": 3,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "categories": categories,
        "source_stats": payload["metrics"],
        "samples": samples,
    }

    _ensure_artifact_dir()
    MODEL_BEHAVIOR_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    TRAINING_DATA_PATH.write_text(json.dumps(training_payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return payload


def _load_behavior_model():
    if not MODEL_BEHAVIOR_PATH.exists():
        return None
    try:
        payload = json.loads(MODEL_BEHAVIOR_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("version") or 0) < 3:
        return None
    if not isinstance(payload.get("categories"), list) or not isinstance(payload.get("priors"), dict):
        return None
    return payload


class BehaviorModelBestLoader:
    def __init__(self, model_path, label_path, vocab_path, reason_path):
        self.model_path = Path(model_path)
        self.label_path = Path(label_path)
        self.vocab_path = Path(vocab_path)
        self.reason_path = Path(reason_path)
        self._metadata = None
        self._metadata_error = None
        self._model = None
        self._model_error = None
        self._archive_config = None

    def _read_json(self, path):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _load_archive_config(self):
        if self._archive_config is not None:
            return self._archive_config
        try:
            with zipfile.ZipFile(self.model_path, "r") as archive:
                config_payload = json.loads(archive.read("config.json").decode("utf-8"))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            return None
        if not isinstance(config_payload, dict):
            return None
        self._archive_config = config_payload
        return self._archive_config

    def _layer_configs(self):
        archive_config = self._load_archive_config() or {}
        model_config = archive_config.get("config") or {}
        layers = model_config.get("layers") or []
        return {
            str(layer.get("name") or ""): layer
            for layer in layers
            if isinstance(layer, dict) and str(layer.get("name") or "").strip()
        }

    def _rebuild_model_from_archive(self):
        metadata = self.load_metadata()
        layer_configs = self._layer_configs()
        if metadata is None or not layer_configs:
            return None

        try:
            import keras
            from keras import layers, ops
        except Exception as exc:
            self._model_error = f"keras_backend_unavailable:{exc.__class__.__name__}"
            return None

        sequence_length = int(metadata.get("sequence_length") or 5)
        inputs = {}
        embedding_outputs = []
        for feature_name in metadata["feature_order"]:
            embedding_layer = layer_configs.get(f"{feature_name}_embedding") or {}
            embedding_config = embedding_layer.get("config") or {}
            input_dim = _safe_int(embedding_config.get("input_dim"), 0)
            output_dim = _safe_int(embedding_config.get("output_dim"), 0)
            if input_dim <= 0 or output_dim <= 0:
                self._model_error = f"invalid_embedding_config:{feature_name}"
                return None

            feature_input = layers.Input(shape=(sequence_length,), dtype="int32", name=feature_name)
            feature_embedding = layers.Embedding(
                input_dim=input_dim,
                output_dim=output_dim,
                name=f"{feature_name}_embedding",
            )(feature_input)
            inputs[feature_name] = feature_input
            embedding_outputs.append(feature_embedding)

        mask_source = inputs.get(metadata["feature_order"][0])
        padding_mask = layers.Lambda(
            lambda x: ops.cast(ops.not_equal(x, 0), "float32"),
            output_shape=(sequence_length,),
            name="padding_mask",
        )(mask_source)
        padding_mask_expand = layers.Lambda(
            lambda x: ops.expand_dims(x, axis=-1),
            output_shape=(sequence_length, 1),
            name="padding_mask_expand",
        )(padding_mask)
        merged = layers.Concatenate(axis=-1, name="merge_features")(embedding_outputs)
        masked = layers.Multiply(name="apply_padding_mask")([merged, padding_mask_expand])

        recurrent_layer = layer_configs.get("recurrent") or {}
        recurrent_class = str(recurrent_layer.get("class_name") or "").strip()
        recurrent_config = recurrent_layer.get("config") or {}
        recurrent_kwargs = {
            "name": "recurrent",
            "trainable": True,
            "units": _safe_int(recurrent_config.get("units"), 64),
            "dropout": float(recurrent_config.get("dropout") or 0.0),
            "recurrent_dropout": float(recurrent_config.get("recurrent_dropout") or 0.0),
            "return_sequences": bool(recurrent_config.get("return_sequences")),
        }
        if recurrent_class == "SimpleRNN":
            recurrent = layers.SimpleRNN(
                activation=recurrent_config.get("activation") or "tanh",
                use_bias=bool(recurrent_config.get("use_bias", True)),
                **recurrent_kwargs,
            )(masked)
        elif recurrent_class == "LSTM":
            recurrent = layers.LSTM(
                activation=recurrent_config.get("activation") or "tanh",
                recurrent_activation=recurrent_config.get("recurrent_activation") or "sigmoid",
                use_bias=bool(recurrent_config.get("use_bias", True)),
                **recurrent_kwargs,
            )(masked)
        elif recurrent_class == "Bidirectional":
            inner_layer_config = (recurrent_config.get("layer") or {}).get("config") or {}
            inner_name = str(inner_layer_config.get("name") or "bidirectional_inner")
            inner_layer = layers.LSTM(
                units=_safe_int(inner_layer_config.get("units"), 64),
                activation=inner_layer_config.get("activation") or "tanh",
                recurrent_activation=inner_layer_config.get("recurrent_activation") or "sigmoid",
                dropout=float(inner_layer_config.get("dropout") or 0.0),
                recurrent_dropout=float(inner_layer_config.get("recurrent_dropout") or 0.0),
                return_sequences=bool(inner_layer_config.get("return_sequences")),
                use_bias=bool(inner_layer_config.get("use_bias", True)),
                name=inner_name,
            )
            recurrent = layers.Bidirectional(
                inner_layer,
                merge_mode=recurrent_config.get("merge_mode") or "concat",
                name="recurrent",
            )(masked)
        else:
            self._model_error = f"unsupported_model_best_architecture:{recurrent_class or 'unknown'}"
            return None

        dense_layer = layer_configs.get("dense") or {}
        dense_config = dense_layer.get("config") or {}
        dense = layers.Dense(
            units=_safe_int(dense_config.get("units"), 64),
            activation=dense_config.get("activation") or "relu",
            name="dense",
        )(recurrent)

        dropout_layer = layer_configs.get("dropout") or {}
        dropout_config = dropout_layer.get("config") or {}
        dense = layers.Dropout(
            rate=float(dropout_config.get("rate") or 0.0),
            name="dropout",
        )(dense)

        output_layer = layer_configs.get("target_next_category_slug") or {}
        output_config = output_layer.get("config") or {}
        outputs = layers.Dense(
            units=_safe_int(output_config.get("units"), len(metadata["labels"])),
            activation=output_config.get("activation") or "softmax",
            name="target_next_category_slug",
        )(dense)
        model = keras.Model(
            inputs=[inputs[feature_name] for feature_name in metadata["feature_order"]],
            outputs=outputs,
            name=str((self._load_archive_config() or {}).get("config", {}).get("name") or "model_best_runtime"),
        )

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                weights_path = Path(temp_dir) / "model.weights.h5"
                with zipfile.ZipFile(self.model_path, "r") as archive:
                    with weights_path.open("wb") as handle:
                        handle.write(archive.read("model.weights.h5"))
                model.load_weights(str(weights_path))
        except Exception as exc:
            self._model_error = f"manual_weight_load_failed:{exc.__class__.__name__}"
            return None
        self._model_error = None
        return model

    def load_metadata(self):
        if self._metadata is not None or self._metadata_error is not None:
            return self._metadata
        if not self.model_path.exists():
            self._metadata_error = "missing_model_best_artifact"
            return None

        label_payload = self._read_json(self.label_path)
        vocab_payload = self._read_json(self.vocab_path)
        if not isinstance(label_payload, dict) or not isinstance(vocab_payload, dict):
            self._metadata_error = "missing_model_best_metadata"
            return None

        labels = label_payload.get("labels")
        feature_order = vocab_payload.get("feature_order")
        features = vocab_payload.get("features")
        sequence_length = _safe_int(vocab_payload.get("sequence_length"), 0)
        if not isinstance(labels, list) or not isinstance(feature_order, list) or not isinstance(features, dict) or sequence_length <= 0:
            self._metadata_error = "invalid_model_best_metadata"
            return None

        try:
            reason_text = self.reason_path.read_text(encoding="utf-8").strip() if self.reason_path.exists() else ""
        except OSError:
            reason_text = ""

        self._metadata = {
            "labels": [str(label or "").strip().lower() for label in labels if str(label or "").strip()],
            "feature_order": [str(name or "").strip() for name in feature_order if str(name or "").strip()],
            "features": features,
            "sequence_length": sequence_length,
            "reason_text": reason_text,
            "model_path": str(self.model_path),
        }
        return self._metadata

    def metadata_error(self):
        self.load_metadata()
        return self._metadata_error

    def model_error(self):
        self.load_metadata()
        return self._model_error or self._metadata_error

    def backend_available(self):
        return self.load_metadata() is not None and self._load_model() is not None

    def _load_model(self):
        if self._model is not None or self._model_error is not None:
            return self._model
        if self.load_metadata() is None:
            self._model_error = self._metadata_error
            return None
        try:
            try:
                from keras.saving import load_model
            except Exception:
                from keras.models import load_model
        except Exception as exc:
            self._model_error = f"keras_backend_unavailable:{exc.__class__.__name__}"
            return None

        try:
            self._model = load_model(str(self.model_path), safe_mode=False)
        except TypeError:
            try:
                self._model = load_model(str(self.model_path))
            except Exception as exc:
                self._model_error = f"model_load_failed:{exc.__class__.__name__}"
                self._model = self._rebuild_model_from_archive()
                return self._model
        except Exception as exc:
            self._model_error = f"model_load_failed:{exc.__class__.__name__}"
            self._model = self._rebuild_model_from_archive()
            return self._model
        return self._model

    def _encode_feature_sequence(self, sequence_rows, feature_name):
        metadata = self.load_metadata()
        feature_payload = (metadata or {}).get("features", {}).get(feature_name) or {}
        feature_index = feature_payload.get("index") or {}
        pad_index = _safe_int(feature_index.get(feature_payload.get("pad_token") or "[PAD]"), 0)
        oov_index = _safe_int(feature_index.get(feature_payload.get("oov_token") or "[OOV]"), 1)
        encoded = []
        for row in sequence_rows[: metadata["sequence_length"]]:
            raw_value = str((row or {}).get(feature_name) or "").strip().lower()
            encoded.append(_safe_int(feature_index.get(raw_value), oov_index if raw_value else pad_index))
        while len(encoded) < metadata["sequence_length"]:
            encoded.insert(0, pad_index)
        return encoded[-metadata["sequence_length"] :]

    def predict_distribution(self, sequence_rows):
        metadata = self.load_metadata()
        model = self._load_model()
        if metadata is None or model is None:
            return None

        try:
            import numpy as np
        except Exception as exc:
            self._model_error = f"numpy_unavailable:{exc.__class__.__name__}"
            return None

        inputs = {
            feature_name: np.asarray([self._encode_feature_sequence(sequence_rows, feature_name)], dtype="int32")
            for feature_name in metadata["feature_order"]
        }
        try:
            prediction = model.predict(inputs, verbose=0)
        except TypeError:
            prediction = model.predict(inputs)
        except Exception as exc:
            self._model_error = f"model_predict_failed:{exc.__class__.__name__}"
            return None

        try:
            values = prediction.tolist() if hasattr(prediction, "tolist") else prediction
            row = values[0] if isinstance(values, list) and values else []
            if not isinstance(row, list):
                return None
        except (TypeError, ValueError, IndexError):
            return None

        scores = {}
        for index, label in enumerate(metadata["labels"]):
            if index >= len(row):
                break
            try:
                scores[label] = float(row[index])
            except (TypeError, ValueError):
                scores[label] = 0.0
        return _normalize_probabilities(scores) if scores else None


def _get_model_best_loader():
    global _MODEL_BEST_LOADER, _MODEL_BEST_SIGNATURE
    signature = (
        str(MODEL_BEST_PATH),
        str(LABEL_ENCODER_PATH),
        str(TOKENIZER_VOCAB_PATH),
        str(MODEL_BEST_REASON_PATH),
    )
    if _MODEL_BEST_LOADER is None or _MODEL_BEST_SIGNATURE != signature:
        _MODEL_BEST_SIGNATURE = signature
        _MODEL_BEST_LOADER = BehaviorModelBestLoader(
            model_path=MODEL_BEST_PATH,
            label_path=LABEL_ENCODER_PATH,
            vocab_path=TOKENIZER_VOCAB_PATH,
            reason_path=MODEL_BEST_REASON_PATH,
        )
    return _MODEL_BEST_LOADER


def _build_runtime_sequence_rows(user_ref, question="", current_product=None, user_context=None, categories=None, sequence_length=5):
    current_product = current_product or {}
    user_context = user_context or {}
    categories = categories or _catalog_categories()
    recent_events = list(
        BehaviorEvent.objects.filter(user_ref=user_ref)
        .order_by("-created_at")[: max(0, sequence_length - 1)]
    )
    recent_events.reverse()

    sequence_rows = []
    for event in recent_events:
        metadata = event.metadata or {}
        sequence_rows.append(
            {
                "behavior_type": str(event.event_type or BehaviorEvent.EVENT_CHATBOT_ASK).strip().lower() or BehaviorEvent.EVENT_CHATBOT_ASK,
                "category_slug": str(metadata.get("current_category_slug") or event.category_slug or "").strip().lower(),
                "price_bucket": str(metadata.get("price_bucket") or "unknown").strip().lower() or "unknown",
                "device_type": _normalize_device_type(metadata.get("device_type")),
            }
        )

    runtime_category = str(current_product.get("category_slug") or current_product.get("service") or "").strip().lower()
    if not runtime_category:
        runtime_category = _category_hint_from_question(question, categories)
    sequence_rows.append(
        {
            "behavior_type": BehaviorEvent.EVENT_CHATBOT_ASK,
            "category_slug": runtime_category,
            "price_bucket": _price_bucket(current_product.get("price")),
            "device_type": _infer_device_type(current_product=current_product, user_context=user_context),
        }
    )
    return sequence_rows[-max(1, sequence_length) :]


def _predict_heuristic_behavior_signal(user_ref, question="", current_product=None, user_context=None):
    user_ref = str(user_ref or "").strip() or "anonymous"
    current_product = current_product or {}
    user_context = user_context or {}

    model_payload = _load_behavior_model()
    base_model_payload = model_payload or {"categories": fetch_catalog_categories(), "priors": {}}
    categories = _catalog_categories(
        extra_slugs=[current_product.get("category_slug") or current_product.get("service")],
        model_categories=base_model_payload.get("categories") or [],
    )
    scores = {
        item["slug"]: 0.2 + float(base_model_payload.get("priors", {}).get(item["slug"], 0.0))
        for item in categories
    }

    history_scores, event_count = _history_scores(user_ref, categories)
    for slug, value in history_scores.items():
        scores[slug] += value

    for slug in detect_category_matches(question, categories=categories):
        scores[slug] += 3.0

    current_category_slug = str(current_product.get("category_slug") or current_product.get("service") or "").strip().lower()
    if current_category_slug in scores:
        scores[current_category_slug] += 2.5

    for text in (user_context.get("cart_items") or []) + (user_context.get("saved_items") or []) + (user_context.get("recent_paid_items") or []):
        for slug in detect_category_matches(text, categories=categories):
            scores[slug] += 0.4

    normalized = _normalize_probabilities(scores)
    dominant_category_slug = max(normalized, key=normalized.get) if normalized else ""
    context_count = len(user_context.get("cart_items") or []) + len(user_context.get("saved_items") or []) + len(user_context.get("recent_paid_items") or [])
    intent_score = min(0.95, 0.2 + (math.log1p(event_count) * 0.12) + (context_count * 0.04))

    return {
        "intent_score": round(intent_score, 4),
        "category_scores": normalized,
        "dominant_category_slug": dominant_category_slug,
        "source": "model_behavior" if model_payload else "heuristic",
        "model_metrics": base_model_payload.get("metrics") or {},
        "categories": categories,
    }


def predict_behavior_for_user_ref(user_ref, question="", current_product=None, user_context=None):
    heuristic_signal = _predict_heuristic_behavior_signal(
        user_ref=user_ref,
        question=question,
        current_product=current_product,
        user_context=user_context,
    )
    categories = heuristic_signal.get("categories") or []
    category_slugs = [item["slug"] for item in categories]
    loader = _get_model_best_loader()
    metadata = loader.load_metadata()

    if metadata is None:
        heuristic_signal["model_best"] = {
            "available": False,
            "selected_category_slug": "",
            "reason": "",
            "error": loader.metadata_error(),
        }
        return heuristic_signal

    sequence_rows = _build_runtime_sequence_rows(
        user_ref=str(user_ref or "").strip() or "anonymous",
        question=question,
        current_product=current_product,
        user_context=user_context,
        categories=categories,
        sequence_length=metadata.get("sequence_length") or 5,
    )
    model_scores = loader.predict_distribution(sequence_rows)
    if not model_scores:
        heuristic_signal["model_best"] = {
            "available": False,
            "selected_category_slug": "",
            "reason": metadata.get("reason_text") or "",
            "error": loader.model_error(),
        }
        return heuristic_signal

    filtered_model_scores = {
        slug: float(model_scores.get(slug, 0.0))
        for slug in category_slugs
    }
    combined_scores = {}
    heuristic_scores = heuristic_signal.get("category_scores") or {}
    for slug in category_slugs:
        combined_scores[slug] = (float(heuristic_scores.get(slug, 0.0)) * 0.35) + (filtered_model_scores.get(slug, 0.0) * 0.65)
    normalized = _normalize_probabilities(combined_scores)
    dominant_category_slug = max(normalized, key=normalized.get) if normalized else heuristic_signal.get("dominant_category_slug") or ""
    predicted_category_slug = max(filtered_model_scores, key=filtered_model_scores.get) if filtered_model_scores else ""

    return {
        **heuristic_signal,
        "category_scores": normalized,
        "dominant_category_slug": dominant_category_slug,
        "source": "model_best",
        "model_best": {
            "available": True,
            "selected_category_slug": predicted_category_slug,
            "reason": metadata.get("reason_text") or "",
            "error": None,
        },
    }

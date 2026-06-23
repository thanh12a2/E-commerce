# Phase 3 Kaggle Training for 2a

This phase adds a standalone Kaggle notebook for TensorFlow/Keras training and comparison of three sequence models:

- `RNN`
- `LSTM`
- `biLSTM`

The notebook lives at [notebooks/phase3_kaggle_training_2a.ipynb](/C:/Users/nguye/Desktop/kiemtra01/notebooks/phase3_kaggle_training_2a.ipynb).

## Input contract

- Input file: `data_user500.csv`
- Default sequence length: `5`
- Per-event features:
  - `behavior_type`
  - `category_slug`
  - `price_bucket`
  - `device_type`
- Target:
  - `target_next_category_slug`

The notebook validates the Phase 1 CSV contract before training and uses the same split plus the same preprocessing pipeline for all three models.

## Split and preprocess choices

- Group split is done by `user_ref + session_id` to avoid train/test leakage across events in the same session.
- Session split is fixed by seed `20260420`.
- Feature vocabularies are fixed from the shared contract instead of being learned loosely from the dataset.
- Labels are fixed to the 10 official category slugs from Phase 1.
- Class weights are computed from the training split only and reused for all three models.

## Output artifacts

The notebook writes the following files under `/kaggle/working/phase3_artifacts/`:

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

Selection rule for `model_best`:

- First priority: highest macro F1 on the held-out test split
- Tie-break: if macro F1 difference is very small, prefer the lighter model with simpler inference

## Kaggle usage

1. Upload `services/chatbot_service/chatbot/artifacts/data_user500.csv` to a Kaggle dataset or notebook input.
2. Open `notebooks/phase3_kaggle_training_2a.ipynb` in Kaggle.
3. Run all cells.
4. Download the files from `/kaggle/working/phase3_artifacts/`.
5. Copy the downloaded artifacts into `services/chatbot_service/chatbot/artifacts/` without renaming them.

## Scope guard

- Kaggle is training-only in this phase.
- No chatbot runtime code is changed here.
- Phase 5 can later load the exported `.keras`, vocab, and label files from the repo artifact directory.

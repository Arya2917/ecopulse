"""
Model Detector Service
Loads a serialised model and identifies its type / task.
Currently handles: ML path (sklearn-compatible)
LLM path: reserved — plug in HuggingFace / LangChain detection here later.
"""

import joblib
import numpy as np


def detect_model_type(model_path: str) -> dict:
    """
    Returns a dict describing the loaded model:
      {
        "framework":   "sklearn",
        "model_class": "RandomForestClassifier",
        "task":        "classification" | "regression",
        "path":        "ml",          # "ml" | "llm"  (llm reserved)
        "n_features":  int | None,
        "n_classes":   int | None,    # classification only
        "n_outputs":   int | None,
      }
    """
    model = joblib.load(model_path)
    info  = {
        "framework":   "sklearn",
        "model_class": type(model).__name__,
        "task":        None,
        "path":        "ml",
        "n_features":  None,
        "n_classes":   None,
        "n_outputs":   None,
    }

    # ── LLM detection hook (future) ──────────────────────────────────────────
    # if isinstance(model, transformers.PreTrainedModel):
    #     info["path"]      = "llm"
    #     info["framework"] = "huggingface"
    #     return info
    # ─────────────────────────────────────────────────────────────────────────

    # Task detection
    if hasattr(model, "predict_proba") or hasattr(model, "classes_"):
        info["task"] = "classification"
    elif hasattr(model, "predict"):
        info["task"] = "regression"

    # Feature count
    if hasattr(model, "n_features_in_"):
        info["n_features"] = int(model.n_features_in_)
    elif hasattr(model, "n_features_"):
        info["n_features"] = int(model.n_features_)

    # Class count
    if hasattr(model, "classes_"):
        info["n_classes"] = int(len(model.classes_))

    # Output count
    if hasattr(model, "n_outputs_"):
        info["n_outputs"] = int(model.n_outputs_)

    return info
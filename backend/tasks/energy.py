# backend/tasks/energy.py
# ─────────────────────────────────────────────────────────────────────────────
# Energy Efficiency module — powered by CodeCarbon.
# Integrates with the unified audit orchestrator in app.py.
#
# CONTRACT (matches MODULE_RUNNERS signature):
#   run_energy(csv_path, target, sensitive, model_path, **kwargs) -> dict
# ─────────────────────────────────────────────────────────────────────────────

import os
import math
import platform
import pickle
import tempfile
import joblib

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

try:
    from codecarbon import EmissionsTracker
    CODECARBON_AVAILABLE = True
except ImportError:
    CODECARBON_AVAILABLE = False


# ── helpers ────────────────────────────────────────────────────────────────

def _get_system_info() -> dict:
    return {
        "platform":       platform.platform(),
        "python_version": platform.python_version(),
        "cpu_count":      os.cpu_count() or 0,
    }


def _detect_feature_count(model) -> int:
    if hasattr(model, "n_features_in_"):
        return int(model.n_features_in_)
    if hasattr(model, "feature_count_"):
        return int(model.feature_count_)
    return 10   # safe fallback


def _sanitize(obj):
    """Recursively replace NaN/Inf with None for JSON safety."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(i) for i in obj]
    return obj


def _read_last_emissions_row(emissions_csv="emissions.csv") -> dict:
    """Try to read hardware details from the CodeCarbon CSV."""
    try:
        if os.path.exists(emissions_csv):
            df = pd.read_csv(emissions_csv)
            if not df.empty:
                return df.tail(3).where(df.notna(), None).to_dict(orient="records")
    except Exception:
        pass
    return []


def _run_tracker_epoch(fn) -> tuple:
    """
    Run fn() under a CodeCarbon tracker for one epoch.
    Returns (energy_kwh, carbon_kg).
    """
    if not CODECARBON_AVAILABLE:
        fn()
        return 0.0, 0.0

    tracker = EmissionsTracker(save_to_file=True, output_dir=".", log_level="error")
    tracker.start()
    fn()
    emissions_obj = tracker.stop()

    # codecarbon ≥0.3 returns a float (kg CO₂); older versions return an object
    if isinstance(emissions_obj, float):
        carbon = emissions_obj
        energy = None
    else:
        carbon = getattr(emissions_obj, "emissions", None) or 0.0
        energy = getattr(emissions_obj, "energy_consumed", None)

    # Fall back to reading from CSV if energy not returned directly
    if energy is None:
        try:
            df = pd.read_csv("emissions.csv")
            energy = float(df["energy_consumed"].iloc[-1])
        except Exception:
            energy = 0.0

    return float(energy or 0.0), float(carbon or 0.0)


def generate_recommendations(results: dict) -> list:
    recs = []
    energy  = results.get("energy_kwh", 0) or 0
    carbon  = results.get("carbon_kg",  0) or 0
    samples = results.get("num_samples", 0) or 0
    features = results.get("num_features", 0) or 0
    model   = results.get("model", "")
    epochs  = results.get("epochs", 1) or 1
    per_epoch = results.get("energy_per_epoch", []) or []
    cpu     = (results.get("system_info") or {}).get("cpu_count", 0) or 0

    if energy < 0.01:
        recs.append("Energy consumption is very low — configuration is already efficient.")
    elif energy < 0.1:
        recs.append("Moderate energy usage — early stopping can further reduce cost.")
    else:
        recs.append("High energy usage detected — consider reducing model complexity or dataset size.")

    if carbon > 0.5:
        recs.append("High carbon footprint — prefer renewable-powered or low-carbon-intensity infrastructure.")

    if epochs > 10:
        recs.append("High epoch count — implement early stopping based on validation loss.")

    if len(per_epoch) > 2 and per_epoch[-1] >= per_epoch[-2]:
        recs.append("Energy plateau detected across epochs — early stopping is strongly recommended.")

    if samples > 200_000:
        recs.append("Large dataset — consider stratified sampling or distributed training to reduce per-run cost.")

    if features > 1000:
        recs.append("High feature dimensionality — apply PCA or feature selection before training.")

    if "randomforest" in model.lower():
        recs.append("RandomForest detected — reduce n_estimators or max_depth to lower energy per training run.")

    if cpu >= 16:
        recs.append("Many CPU cores available — parallel/distributed training can improve energy efficiency.")

    recs.append("Apply model pruning, quantization, or mixed precision to reduce compute footprint.")
    recs.append("Schedule batch training during off-peak or low-carbon-intensity electricity hours.")

    return recs


# ── public entry point ─────────────────────────────────────────────────────

def run_energy(
    csv_path: str,
    target: str = "",
    sensitive: str = "",
    model_path=None,
    epochs: int = 1,
    **kwargs,
) -> dict:
    """
    Run an energy efficiency audit using CodeCarbon.

    Supports two modes:
      • CSV dataset  → trains a Random Forest and tracks training energy.
      • .pkl model   → runs inference on synthetic data and tracks that energy.

    Returns a dict compatible with the unified report generator.
    """

    if not CODECARBON_AVAILABLE:
        return {
            "module":  "energy",
            "status":  "error",
            "message": (
                "codecarbon is not installed. "
                "Run: pip install codecarbon"
            ),
        }

    epochs = max(1, int(epochs))
    system_info = _get_system_info()

    # ── Decide mode ─────────────────────────────────────────────────────────
    # If a model file (.pkl) was uploaded, run inference audit.
    # Otherwise, train a Random Forest on the CSV.

    if model_path and os.path.exists(model_path) and model_path.endswith(".pkl"):
        return _run_inference_audit(model_path, epochs, system_info)
    else:
        return _run_training_audit(csv_path, target, epochs, system_info)


# ── training audit ──────────────────────────────────────────────────────────

def _run_training_audit(csv_path: str, target: str, epochs: int, system_info: dict) -> dict:
    df = pd.read_csv(csv_path)

    # Auto-pick last column as target if not specified
    tgt = target if target and target in df.columns else df.columns[-1]

    X = df.drop(columns=[tgt])
    y = df[tgt]

    # Encode categoricals
    cat_cols = X.select_dtypes(include=["object"]).columns
    if len(cat_cols):
        X = pd.get_dummies(X, drop_first=True)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = RandomForestClassifier(n_estimators=100, random_state=42)

    energy_list, total_energy, total_carbon = [], 0.0, 0.0

    for ep in range(epochs):
        energy, carbon = _run_tracker_epoch(lambda: model.fit(X_train, y_train))
        energy_list.append(energy)
        total_energy += energy
        total_carbon += carbon

    raw_preview = _read_last_emissions_row()

    result = {
        "module":            "energy",
        "status":            "done",
        "file_type":         "dataset_training",
        "energy_kwh":        total_energy,
        "carbon_kg":         total_carbon,
        "energy_per_epoch":  energy_list,
        "epochs":            epochs,
        "num_samples":       int(len(X)),
        "num_features":      int(X.shape[1]),
        "model":             "RandomForest",
        "system_info":       system_info,
        "raw_emissions_preview": raw_preview,
    }

    result["recommendations"] = generate_recommendations(result)
    return _sanitize(result)


# ── inference audit ─────────────────────────────────────────────────────────

def _run_inference_audit(model_path: str, epochs: int, system_info: dict) -> dict:
    with open(model_path, "rb") as f:
       model = joblib.load(model_path)

    n_features = _detect_feature_count(model)
    X_sample = np.random.rand(1000, n_features)

    energy_list, total_energy, total_carbon = [], 0.0, 0.0

    for ep in range(epochs):
        energy, carbon = _run_tracker_epoch(lambda: model.predict(X_sample))
        energy_list.append(energy)
        total_energy += energy
        total_carbon += carbon

    raw_preview = _read_last_emissions_row()

    result = {
        "module":            "energy",
        "status":            "done",
        "file_type":         "model_inference",
        "energy_kwh":        total_energy,
        "carbon_kg":         total_carbon,
        "energy_per_epoch":  energy_list,
        "epochs":            epochs,
        "model":             type(model).__name__,
        "system_info":       system_info,
        "raw_emissions_preview": raw_preview,
    }

    result["recommendations"] = generate_recommendations(result)
    return _sanitize(result)
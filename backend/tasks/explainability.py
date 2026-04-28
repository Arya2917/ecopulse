# backend/tasks/explainability.py
# ─────────────────────────────────────────────────────────────────────────────
# REAL SHAP / LIME implementation — integrated from Arya2917/ecopulse
#
# CONTRACT (unchanged — matches the orchestrator in app.py):
#   run_explainability(csv_path, target, sensitive, model_path, **kwargs) -> dict
#
# The returned dict is JSON-serialisable and is stored in:
#   JOBS[job_id]["module_results"]["explainability"]
#
# Key design decisions:
#   * Uses model_detector  -> detects model class / task automatically
#   * Uses shap_service    -> TreeExplainer / LinearExplainer / KernelExplainer
#   * Uses lime_service    -> LimeTabularExplainer on a single sample
#   * Uses aggregator      -> consensus top-features across SHAP & LIME
#   * Works WITHOUT a model_path: trains a quick Random-Forest baseline on the
#     CSV so the module is useful even when only a dataset is uploaded
#   * All chart images are returned as base64 strings (JSON-safe)
#   * Raises on hard errors — the orchestrator catches and marks "error"
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
import uuid
import tempfile
import joblib
import pandas as pd
import numpy as np

from services.model_detector import detect_model_type
from services.shap_service   import run_shap_analysis
from services.lime_service   import run_lime_analysis
from services.aggregator     import aggregate_results


# ── Helpers ────────────────────────────────────────────────────────────────

def _train_baseline(csv_path: str, target: str):
    """
    Train a quick RandomForestClassifier/Regressor on the CSV and save it
    to a temp .pkl file.
    Returns (model_path, transformed_csv_path).
    """
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.preprocessing import LabelEncoder, StandardScaler, OrdinalEncoder
    from sklearn.pipeline import Pipeline
    from sklearn.compose import ColumnTransformer

    df = pd.read_csv(csv_path)
    if target not in df.columns:
        raise ValueError(f"Target column '{target}' not found in CSV.")

    X = df.drop(columns=[target])
    y = df[target]

    cat_cols = X.select_dtypes(include=["object", "category"]).columns.tolist()
    num_cols = X.select_dtypes(exclude=["object", "category"]).columns.tolist()

    transformers = []
    if cat_cols:
        transformers.append(("cat", OrdinalEncoder(
            handle_unknown="use_encoded_value", unknown_value=-1), cat_cols))
    if num_cols:
        transformers.append(("num", StandardScaler(), num_cols))

    preprocessor = ColumnTransformer(transformers, remainder="drop")

    # Detect task
    is_classification = y.dtype == object or y.nunique() <= 20
    if is_classification:
        le = LabelEncoder()
        y  = le.fit_transform(y.astype(str))
        estimator = RandomForestClassifier(n_estimators=50, random_state=42,
                                           n_jobs=-1, max_depth=6)
    else:
        estimator = RandomForestRegressor(n_estimators=50, random_state=42,
                                          n_jobs=-1, max_depth=6)

    pipe = Pipeline([("pre", preprocessor), ("clf", estimator)])
    pipe.fit(X, y)

    # Save just the inner estimator (shap/lime need a plain sklearn model)
    inner_model = pipe.named_steps["clf"]
    tmp_model = tempfile.NamedTemporaryFile(suffix=".pkl", delete=False)
    joblib.dump(inner_model, tmp_model.name)
    tmp_model.close()

    # Write a fully-numeric CSV for shap/lime to consume
    X_t = preprocessor.fit_transform(X)
    feature_names = (
        [f"{c}_enc" for c in cat_cols] + num_cols if cat_cols else num_cols
    )
    df_transformed = pd.DataFrame(X_t, columns=feature_names)
    df_transformed[target] = np.array(y)

    transformed_csv = tmp_model.name.replace(".pkl", "_data.csv")
    df_transformed.to_csv(transformed_csv, index=False)

    return tmp_model.name, transformed_csv


def _prepare_dataset_for_explain(csv_path: str, target: str) -> str:
    """
    Ensure the target column is last (shap/lime convention).
    Returns path to a (possibly rewritten) CSV.
    """
    df = pd.read_csv(csv_path)
    if target not in df.columns:
        return csv_path  # let downstream raise a meaningful error

    cols = [c for c in df.columns if c != target] + [target]
    if list(df.columns) == cols:
        return csv_path

    reordered_path = csv_path.replace(".csv", "_reordered.csv")
    df[cols].to_csv(reordered_path, index=False)
    return reordered_path


# ── Public contract ────────────────────────────────────────────────────────

def run_explainability(
    csv_path:  str,
    target:    str,
    sensitive: str = "",
    model_path=None,   # str path or None
    **kwargs,
) -> dict:
    """
    Run SHAP + LIME explainability and return a unified JSON-serialisable dict.

    Parameters
    ----------
    csv_path   : path to the uploaded CSV dataset
    target     : name of the target / label column
    sensitive  : name of the sensitive attribute column (accepted to match
                 the orchestrator's unified call signature; not used here)
    model_path : path to a user-uploaded .pkl / .joblib model, or None
    **kwargs   : absorbs train_baseline, wrap_model, dp_threshold, etc.
                 Also accepts:
                   max_shap_samples  (int, default 150)
                   lime_sample_idx   (int, default 0)
                   lime_num_features (int, default 10)
    """

    # Create a private working directory for plots
    session_dir = os.path.join(
        os.path.dirname(csv_path),
        f"explain_{uuid.uuid4().hex[:8]}"
    )
    os.makedirs(session_dir, exist_ok=True)

    baseline_trained = False

    # ── 1. Resolve model & dataset ─────────────────────────────────────────
    if model_path and os.path.exists(str(model_path)):
        try:
            joblib.load(model_path)
        except Exception as exc:
            raise ValueError(f"Cannot load model from '{model_path}': {exc}")
        dataset_path = _prepare_dataset_for_explain(csv_path, target)

    else:
        # No model supplied → train a lightweight baseline
        model_path, dataset_path = _train_baseline(csv_path, target)
        baseline_trained = True

    # ── 2. Detect model type ───────────────────────────────────────────────
    model_info = detect_model_type(model_path)

    # ── 3. SHAP analysis ───────────────────────────────────────────────────
    shap_result = run_shap_analysis(
        model_path   = model_path,
        dataset_path = dataset_path,
        model_info   = model_info,
        max_samples  = int(kwargs.get("max_shap_samples", 150)),
        session_dir  = session_dir,
    )

    # ── 4. LIME analysis ───────────────────────────────────────────────────
    lime_result = run_lime_analysis(
        model_path   = model_path,
        dataset_path = dataset_path,
        model_info   = model_info,
        sample_idx   = int(kwargs.get("lime_sample_idx", 0)),
        num_features = int(kwargs.get("lime_num_features", 10)),
        session_dir  = session_dir,
    )

    # ── 5. Aggregate SHAP + LIME ───────────────────────────────────────────
    aggregated = aggregate_results(shap_result, lime_result)

    # ── 6. Clean up temp baseline files ───────────────────────────────────
    if baseline_trained:
        for tmp_path in [model_path, dataset_path]:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    # ── 7. Build final result dict ─────────────────────────────────────────
    return {
        "module": "explainability",
        "status": "done",

        # ── Model metadata ─────────────────────────────────────────────────
        "model_info": {
            "framework":        model_info.get("framework"),
            "model_class":      model_info.get("model_class"),
            "task":             model_info.get("task"),
            "explainer_used":   shap_result.get("explainer_type"),
            "baseline_trained": baseline_trained,
        },

        # ── SHAP results ───────────────────────────────────────────────────
        "shap": {
            "explainer_type":     shap_result.get("explainer_type"),
            "feature_names":      shap_result.get("feature_names", []),
            "feature_importance": shap_result.get("feature_importance", {}),
            "top_features":       shap_result.get("top_features", []),
            "shap_values_sample": shap_result.get("shap_values_sample", []),
            "n_samples":          shap_result.get("n_samples"),
            "n_features":         shap_result.get("n_features"),
            # Base64-encoded PNGs (use directly in <img src="data:image/png;base64,...">)
            "summary_plot_b64":   shap_result.get("summary_plot_b64"),
            "bar_plot_b64":       shap_result.get("bar_plot_b64"),
        },

        # ── LIME results ───────────────────────────────────────────────────
        "lime": {
            "sample_index":     lime_result.get("sample_index"),
            "mode":             lime_result.get("mode"),
            "feature_names":    lime_result.get("feature_names", []),
            "contributions":    lime_result.get("contributions", {}),
            "top_positive":     lime_result.get("top_positive", []),
            "top_negative":     lime_result.get("top_negative", []),
            "prediction":       lime_result.get("prediction"),
            "prediction_proba": lime_result.get("prediction_proba"),
            "num_features":     lime_result.get("num_features"),
            # Base64-encoded PNG
            "lime_plot_b64":    lime_result.get("lime_plot_b64"),
        },

        # ── Aggregated consensus ───────────────────────────────────────────
        "aggregated": {
            "agreement_score":        aggregated.get("agreement_score"),
            "consensus_top_features": aggregated.get("consensus_top_features", []),
            "shap_top_features":      aggregated.get("shap_top_features", []),
            "lime_top_features":      aggregated.get("lime_top_features", []),
            "per_feature_table":      aggregated.get("per_feature_table", []),
        },
    }




















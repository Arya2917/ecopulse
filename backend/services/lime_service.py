"""
LIME Analysis Service
Runs LIME (Local Interpretable Model-agnostic Explanations) on a single sample.

For classification  → LimeTabularExplainer with predict_proba
For regression      → LimeTabularExplainer with predict
"""

import os
import base64
import numpy  as np
import pandas as pd
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from lime import lime_tabular


def _img_to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def run_lime_analysis(model_path, dataset_path, model_info,
                      sample_idx=0, num_features=10,
                      session_dir=".") -> dict:

    model = joblib.load(model_path)
    df    = pd.read_csv(dataset_path)

    feature_names = list(df.columns[:-1])
    X             = df.iloc[:, :-1]
    X             = pd.get_dummies(X)
    feature_names = list(X.columns)
    X_np          = X.values.astype(float)

    task = model_info.get("task", "classification")

    # Clamp sample index
    sample_idx = min(sample_idx, len(X_np) - 1)
    instance   = X_np[sample_idx]

    # ── Build LIME explainer ──────────────────────────────────────────────────
    mode = "classification" if task == "classification" else "regression"

    explainer = lime_tabular.LimeTabularExplainer(
        training_data   = X_np,
        feature_names   = feature_names,
        mode            = mode,
        discretize_continuous = True,
        random_state    = 42,
    )

    # ── Generate explanation ──────────────────────────────────────────────────
    if task == "classification" and hasattr(model, "predict_proba"):
        predict_fn = model.predict_proba
        exp = explainer.explain_instance(
            instance, predict_fn,
            num_features=num_features, num_samples=1000
        )
        label_used = exp.available_labels()[0]
    else:
        predict_fn = lambda x: model.predict(x).reshape(-1)
        exp = explainer.explain_instance(
            instance, predict_fn,
            num_features=num_features, num_samples=1000
        )
        label_used = 0

    # ── Extract feature contributions ────────────────────────────────────────
    contributions = exp.as_list(label=label_used)   # [(feature_str, weight), ...]
    contrib_dict  = {feat: float(weight) for feat, weight in contributions}

    # ── Save LIME plot ────────────────────────────────────────────────────────
    lime_plot_path = os.path.join(session_dir, f"lime_sample_{sample_idx}.png")
    fig = exp.as_pyplot_figure(label=label_used)
    fig.set_size_inches(10, 6)
    fig.tight_layout()
    fig.savefig(lime_plot_path, dpi=120, bbox_inches="tight")
    plt.close(fig)

    # ── Prediction info ───────────────────────────────────────────────────────
    pred_label = int(model.predict(instance.reshape(1, -1))[0])
    pred_proba = None
    if hasattr(model, "predict_proba"):
        proba      = model.predict_proba(instance.reshape(1, -1))[0]
        pred_proba = {str(i): float(p) for i, p in enumerate(proba)}

    return {
        "sample_index":   sample_idx,
        "feature_names":  feature_names,
        "contributions":  contrib_dict,
        "top_positive":   sorted(contrib_dict.items(), key=lambda x: x[1], reverse=True)[:5],
        "top_negative":   sorted(contrib_dict.items(), key=lambda x: x[1])[:5],
        "prediction":     pred_label,
        "prediction_proba": pred_proba,
        "lime_plot_b64":  _img_to_b64(lime_plot_path),
        "lime_plot_path": lime_plot_path,
        "num_features":   num_features,
        "mode":           mode,
    }
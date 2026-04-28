"""
SHAP Analysis Service
Runs SHAP explainability on a trained sklearn model.

Supports:
  - Tree-based models     → TreeExplainer   (fast, exact)
  - Linear models         → LinearExplainer
  - Any other model       → KernelExplainer (slow but universal)

Outputs:
  - shap_values (list of lists, JSON-serialisable)
  - feature_importance (mean |SHAP|)
  - summary_plot_path (PNG saved to session dir)
  - bar_plot_path     (PNG)
"""

import os
import json
import base64
import numpy  as np
import pandas as pd
import shap
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# sklearn tree-based classes
_TREE_MODELS   = {"RandomForestClassifier","RandomForestRegressor",
                  "GradientBoostingClassifier","GradientBoostingRegressor",
                  "DecisionTreeClassifier","DecisionTreeRegressor",
                  "ExtraTreesClassifier","ExtraTreesRegressor",
                  "XGBClassifier","XGBRegressor",
                  "LGBMClassifier","LGBMRegressor"}

_LINEAR_MODELS = {"LinearRegression","Ridge","Lasso","ElasticNet",
                  "LogisticRegression","SGDClassifier","SGDRegressor"}


def _img_to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def run_shap_analysis(model_path, dataset_path, model_info,
                      max_samples=100, session_dir=".") -> dict:

    model = joblib.load(model_path)
    df    = pd.read_csv(dataset_path)

    # --- Auto-detect target column (last column convention) ---
    feature_names = list(df.columns[:-1])
    X = df.iloc[:, :-1]

    # Encode categoricals naively
    X = pd.get_dummies(X)
    feature_names = list(X.columns)

    # Subsample for performance
    if len(X) > max_samples:
        X = X.sample(max_samples, random_state=42)

    X_np = X.values.astype(float)

    model_class = model_info.get("model_class", "")

    # ── Choose explainer ──────────────────────────────────────────────────────
    if model_class in _TREE_MODELS:
        explainer   = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_np)
    elif model_class in _LINEAR_MODELS:
        background  = shap.maskers.Independent(X_np, max_samples=min(50, len(X_np)))
        explainer   = shap.LinearExplainer(model, background)
        shap_values = explainer.shap_values(X_np)
    else:
        background  = shap.kmeans(X_np, min(10, len(X_np)))
        explainer   = shap.KernelExplainer(model.predict, background)
        shap_values = explainer.shap_values(X_np, nsamples=50)

    # Normalise to 2-D array (handle multiclass lists and 3-D arrays)
    if isinstance(shap_values, list):
        # list of arrays: one per class — pick class 1 for binary, class 0 for multiclass
        pick = 1 if len(shap_values) == 2 else 0
        sv2d = np.array(shap_values[pick])
    else:
        sv2d = np.array(shap_values)

    # If TreeExplainer returns 3-D array (n_samples, n_features, n_classes), take class 1
    if sv2d.ndim == 3:
        pick = 1 if sv2d.shape[2] == 2 else 0
        sv2d = sv2d[:, :, pick]

    # Ensure float64 to avoid scalar conversion issues
    sv2d = sv2d.astype(np.float64)

    # Feature importance: mean absolute SHAP
    importance = np.abs(sv2d).mean(axis=0)
    fi_dict    = {feat: float(imp) for feat, imp in
                  zip(feature_names, importance)}
    fi_sorted  = dict(sorted(fi_dict.items(), key=lambda x: x[1], reverse=True))

    # ── Summary plot ─────────────────────────────────────────────────────────
    summary_path = os.path.join(session_dir, "shap_summary.png")
    plt.figure(figsize=(10, 6))
    shap.summary_plot(sv2d, X_np, feature_names=feature_names,
                      show=False, plot_type="dot")
    plt.tight_layout()
    plt.savefig(summary_path, dpi=120, bbox_inches="tight")
    plt.close()

    # ── Bar plot ──────────────────────────────────────────────────────────────
    bar_path = os.path.join(session_dir, "shap_bar.png")
    plt.figure(figsize=(10, 6))
    shap.summary_plot(sv2d, X_np, feature_names=feature_names,
                      show=False, plot_type="bar")
    plt.tight_layout()
    plt.savefig(bar_path, dpi=120, bbox_inches="tight")
    plt.close()

    return {
        "explainer_type":    _pick_explainer_name(model_class),
        "feature_names":     feature_names,
        "feature_importance": fi_sorted,
        "top_features":      list(fi_sorted.keys())[:10],
        "shap_values_sample": sv2d[:5].tolist(),   # first 5 rows only
        "summary_plot_b64":  _img_to_b64(summary_path),
        "bar_plot_b64":      _img_to_b64(bar_path),
        "summary_plot_path": summary_path,
        "bar_plot_path":     bar_path,
        "n_samples":         len(X_np),
        "n_features":        len(feature_names),
    }


def _pick_explainer_name(model_class):
    if model_class in _TREE_MODELS:   return "TreeExplainer"
    if model_class in _LINEAR_MODELS: return "LinearExplainer"
    return "KernelExplainer"




















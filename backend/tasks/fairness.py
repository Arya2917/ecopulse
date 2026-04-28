import pandas as pd
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.fairness_metrics import (
    compute_fairness_metrics,
    generate_user_specific_suggestions,
    compute_performance_metrics,
    analyze_data_quality,
)

import pickle
import joblib
from utils.mitigation import train_baseline_only, build_transformer


def run_fairness(
    csv_path: str,
    target: str,
    sensitive: str,
    pred_col=None,
    train_baseline=True,
    model_path=None,
    wrap_model=False,
    dp_threshold=0.1,
    eo_threshold=0.1,
    fpr_threshold=0.1,
    fnr_threshold=0.1,
    **kwargs,
) -> dict:

    if not target or not sensitive:
        raise ValueError("Fairness module requires 'target' and 'sensitive' columns.")

    df = pd.read_csv(csv_path)

    # ── determine prediction source ───────────────────────────────────────
    if model_path:
        ext = os.path.splitext(model_path)[1].lower()
        try:
            if ext in ('.pkl', '.joblib'):
                model = joblib.load(model_path)
            else:
                with open(model_path, "rb") as fh:
                    model = pickle.load(fh)
        except Exception as e:
            raise ValueError(f"Failed to load model from '{model_path}': {e}")

        is_dl = False

        if hasattr(model, "predict_with_sensitive"):
            df["y_pred"] = model.predict_with_sensitive(
                df, target_col=target, sensitive_col=sensitive)
        else:
            feat_cols = [c for c in df.columns if c not in (target, sensitive)]
            X = df[feat_cols]

            # Align feature columns to what the model was trained on
            if hasattr(model, "feature_names_in_"):
                trained_features = list(model.feature_names_in_)
                for missing_col in trained_features:
                    if missing_col not in X.columns:
                        X = X.copy()
                        X[missing_col] = 0
                X = X[trained_features]

            if wrap_model:
                transformer, _strategy, _te = build_transformer(df, target, sensitive)
                X = transformer.fit_transform(X)

            df["y_pred"] = model.predict(X)

        pred_col = "y_pred"

    elif train_baseline:
        baseline_res = train_baseline_only(df, target, sensitive)
        clf = baseline_res.get("pipeline")

        if clf is None:
            raise ValueError("Baseline training did not return a trained pipeline.")

        feat_cols = [c for c in df.columns if c not in (target, sensitive)]
        df["y_pred"] = clf.predict(df[feat_cols])
        pred_col = "y_pred"
        is_dl = False

    elif pred_col and pred_col in df.columns:
        is_dl = False

    else:
        raise ValueError(
            "Fairness: no prediction source. Upload a model, provide a "
            "prediction column, or enable baseline training."
        )

    # ── compute metrics ───────────────────────────────────────────────────
    res = compute_fairness_metrics(df, target, sensitive, pred_col=pred_col)

    suggestions = generate_user_specific_suggestions(
        df, res, target, sensitive,
        dp_threshold=dp_threshold,
        eo_threshold=eo_threshold,
        fpr_threshold=fpr_threshold,
        fnr_threshold=fnr_threshold,
    )

    perf = compute_performance_metrics(df[target], df[pred_col])
    dq   = analyze_data_quality(df, target, sensitive)

    return {
        **res,
        "suggestions": suggestions,
        "performance": perf,
        "data_quality": dq,
        "is_dl_model": is_dl if model_path else False,
        "module": "fairness",
        "status": "ok",
    }
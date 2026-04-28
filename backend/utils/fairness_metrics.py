def generate_user_specific_suggestions(df, metrics, target_col, sensitive_col,
                                       dp_threshold=0.1, eo_threshold=0.1,
                                       fpr_threshold=0.1, fnr_threshold=0.1):
    """
    Generate tailored suggestions for dataset/model improvements based on metrics and dataset properties.
    Args:
        df: pandas DataFrame
        metrics: dict from compute_fairness_metrics
        target_col: str
        sensitive_col: str
    Returns:
        List of suggestion strings
    """
    suggestions = []
    overall = metrics.get("overall", {})
    dp_diff = overall.get("Demographic Parity Difference", 0)
    eo_diff = overall.get("Equalized Odds Difference", 0)
    fpr_diff = overall.get("False Positive Rate Difference", 0)
    fnr_diff = overall.get("False Negative Rate Difference", 0)

    # Fairness metric thresholds
    if abs(dp_diff) > dp_threshold:
        suggestions.append(f"Demographic Parity Difference is {dp_diff:.4f}. Consider balancing sensitive groups or applying fairness mitigation.")
    if abs(eo_diff) > eo_threshold:
        suggestions.append(f"Equalized Odds Difference is {eo_diff:.4f}. Consider collecting more data for underrepresented groups or using fairness-aware algorithms.")
    if abs(fpr_diff) > fpr_threshold or abs(fnr_diff) > fnr_threshold:
        suggestions.append("False positive/negative rate differences are high between groups. Review feature selection and data balance.")

    # Class balance
    if target_col in df.columns:
        class_counts = df[target_col].value_counts()
        if class_counts.min() / class_counts.max() < 0.5:
            suggestions.append("Target classes are imbalanced. Consider collecting more data for the minority class.")

    # Sensitive attribute balance
    if sensitive_col in df.columns:
        sensitive_counts = df[sensitive_col].value_counts()
        if sensitive_counts.min() / sensitive_counts.max() < 0.5:
            suggestions.append("Sensitive attribute groups are imbalanced. Consider collecting more data for underrepresented groups.")

    # Missing values
    missing = df.isnull().sum()
    if missing.any():
        missing_cols = missing[missing > 0].index.tolist()
        if missing_cols:
            suggestions.append(f"Columns with missing values: {missing_cols}")

    # If no major issues
    if not suggestions:
        suggestions.append("No major issues detected. Your dataset and model appear to be fair and accurate.")

    return suggestions
# backend/utils/fairness_metrics.py
from fairlearn.metrics import (
    MetricFrame,
    demographic_parity_difference,
    equalized_odds_difference,
    false_positive_rate_difference,
    false_negative_rate_difference,
)
from fairlearn.metrics import selection_rate
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import numpy as np
import pandas as pd

def _ensure_binary(y):
    y = np.asarray(y)
    vals = np.unique(y)
    if set(vals) <= {0, 1} or set(vals) <= {-1, 1}:
        return y.astype(int)
    # map max to 1, others to 0
    return (y == vals.max()).astype(int)

def compute_fairness_metrics(df: pd.DataFrame, target_col: str, sensitive_col: str, pred_col: str = None):
    """
    Return {"overall": {...}, "by_group": {...}} or {"error": "..."}
    """
    try:
        if target_col not in df.columns:
            return {"error": f"target column '{target_col}' not found"}
        if sensitive_col not in df.columns:
            return {"error": f"sensitive column '{sensitive_col}' not found"}

        y_true = df[target_col]
        y_pred = df[pred_col] if pred_col and pred_col in df.columns else y_true
        sensitive = df[sensitive_col]

        # encode labels if object dtype
        if y_true.dtype == object or y_pred.dtype == object:
            le = LabelEncoder()
            y_true_enc = le.fit_transform(y_true)
            try:
                y_pred_enc = le.transform(y_pred)
            except Exception:
                y_pred_enc = LabelEncoder().fit_transform(y_pred)
        else:
            y_true_enc = y_true.values.astype(int)
            y_pred_enc = y_pred.values.astype(int)

        y_true_enc = _ensure_binary(y_true_enc)
        y_pred_enc = _ensure_binary(y_pred_enc)

        # sensitive_series = pd.Series(sensitive).fillna("MISSING")

        # Cast to object before fillna to avoid pandas Categorical category errors
        sensitive_series = (
    pd.Series(sensitive, dtype="object")
    .fillna("MISSING")
    .infer_objects(copy=False)
)
        
        # MetricFrame for selection rate, FPR, FNR groupwise
        mf = MetricFrame(
            metrics={
                "Selection Rate": selection_rate,
                "False Positive Rate": lambda y_t, y_p: ((y_p == 1) & (y_t == 0)).sum() / max(((y_t == 0).sum()), 1),
                "False Negative Rate": lambda y_t, y_p: ((y_p == 0) & (y_t == 1)).sum() / max(((y_t == 1).sum()), 1),
            },
            y_true=y_true_enc,
            y_pred=y_pred_enc,
            sensitive_features=sensitive_series,
        )

        overall = {
            "Demographic Parity Difference": round(float(demographic_parity_difference(
                y_true=y_true_enc, y_pred=y_pred_enc, sensitive_features=sensitive_series)), 4),
            "Equalized Odds Difference": round(float(equalized_odds_difference(
                y_true=y_true_enc, y_pred=y_pred_enc, sensitive_features=sensitive_series)), 4),
            "False Positive Rate Difference": round(float(false_positive_rate_difference(
                y_true=y_true_enc, y_pred=y_pred_enc, sensitive_features=sensitive_series)), 4),
            "False Negative Rate Difference": round(float(false_negative_rate_difference(
                y_true=y_true_enc, y_pred=y_pred_enc, sensitive_features=sensitive_series)), 4),
        }

        by_group = {}
        for g in mf.by_group.index:
            sel = mf.by_group["Selection Rate"].get(g, np.nan)
            fpr = mf.by_group["False Positive Rate"].get(g, np.nan)
            fnr = mf.by_group["False Negative Rate"].get(g, np.nan)
            by_group[str(g)] = {
                "Selection Rate": round(float(sel), 4) if not np.isnan(sel) else None,
                "False Positive Rate": round(float(fpr), 4) if not np.isnan(fpr) else None,
                "False Negative Rate": round(float(fnr), 4) if not np.isnan(fnr) else None,
            }

        return {"overall": overall, "by_group": by_group}
    except Exception as e:
        return {"error": str(e)}


def compute_performance_metrics(y_true, y_pred):
    """
    Compute simple performance metrics for binary classification.
    Returns a dict with accuracy, precision, recall, f1.
    """
    try:
        y_true = _ensure_binary(y_true)
        y_pred = _ensure_binary(y_pred)
        return {
            "Accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
            "Precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
            "Recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
            "F1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        }
    except Exception as e:
        return {"error": str(e)}


def analyze_data_quality(df: pd.DataFrame, target_col: str, sensitive_col: str):
    """
    Basic dataset quality diagnostics.
    """
    out = {}
    try:
        out["num_rows"] = int(df.shape[0])
        out["num_columns"] = int(df.shape[1])

        # Missing values
        missing = df.isnull().sum()
        missing_cols = missing[missing > 0]
        out["missing_columns"] = {str(k): int(v) for k, v in missing_cols.items()}

        # Duplicates
        out["duplicate_rows"] = int(df.duplicated().sum())

        # Target balance
        if target_col in df.columns:
            vc = df[target_col].value_counts(dropna=False)
            out["target_distribution"] = {str(k): int(v) for k, v in vc.items()}

        # Sensitive balance
        if sensitive_col in df.columns:
            vc = df[sensitive_col].value_counts(dropna=False)
            out["sensitive_distribution"] = {str(k): int(v) for k, v in vc.items()}

    except Exception as e:
        out["error"] = str(e)
    return out

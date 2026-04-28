"""
Aggregator Service
Combines SHAP (global) and LIME (local) results into a consensus report.

Outputs:
  - agreement_score        : Jaccard similarity of top-10 SHAP vs top-10 LIME features
  - consensus_top_features : features that appear in BOTH top-N lists
  - shap_top_features      : top features by SHAP importance
  - lime_top_features      : top features by absolute LIME contribution
  - per_feature_table      : full merged table sorted by SHAP importance
"""

from __future__ import annotations


def aggregate_results(shap_result: dict, lime_result: dict, top_n: int = 10) -> dict:
    """
    Parameters
    ----------
    shap_result : dict returned by run_shap_analysis()
    lime_result : dict returned by run_lime_analysis()
    top_n       : how many top features to consider for agreement scoring

    Returns
    -------
    dict with keys: agreement_score, consensus_top_features,
                    shap_top_features, lime_top_features, per_feature_table
    """

    # ── SHAP data ──────────────────────────────────────────────────────────
    shap_importance: dict = shap_result.get("feature_importance", {})
    shap_top: list[str]   = list(shap_importance.keys())[:top_n]

    # ── LIME data ──────────────────────────────────────────────────────────
    lime_contributions: dict = lime_result.get("contributions", {})

    # LIME feature strings look like "age > 45" or "0.30 < income <= 0.80".
    # Strip them to the raw feature name for matching against SHAP features.
    def _strip_lime_key(k: str) -> str:
        """Best-effort: return the bare feature name from a LIME condition string."""
        import re
        # Try "feature_name op value" or "value op feature_name op value"
        # Simplest heuristic: take the alphabetic token that appears in shap_importance
        tokens = re.split(r"[\s<>=!]+", k)
        for tok in tokens:
            tok = tok.strip()
            if tok and tok in shap_importance:
                return tok
        # Fallback: return first non-numeric token
        for tok in tokens:
            tok = tok.strip()
            if tok and not _is_numeric(tok):
                return tok
        return k  # give up, return as-is

    def _is_numeric(s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    # Build a clean {bare_feature: contribution} dict for LIME
    lime_clean: dict[str, float] = {}
    for raw_key, val in lime_contributions.items():
        bare = _strip_lime_key(raw_key)
        # If multiple LIME conditions map to the same feature, sum contributions
        lime_clean[bare] = lime_clean.get(bare, 0.0) + float(val)

    # Top LIME features by absolute contribution
    lime_top: list[str] = sorted(
        lime_clean, key=lambda k: abs(lime_clean[k]), reverse=True
    )[:top_n]

    # ── Agreement score (Jaccard) ──────────────────────────────────────────
    shap_set = set(shap_top)
    lime_set  = set(lime_top)
    union     = shap_set | lime_set
    inter     = shap_set & lime_set
    agreement = len(inter) / len(union) if union else 0.0

    # ── Per-feature table ──────────────────────────────────────────────────
    all_features = set(shap_importance.keys()) | set(lime_clean.keys())
    table = []
    for feat in all_features:
        shap_imp  = float(shap_importance.get(feat, 0.0))
        lime_cont = float(lime_clean.get(feat, 0.0))
        in_shap   = feat in shap_set
        in_lime   = feat in lime_set
        table.append({
            "feature":          feat,
            "shap_importance":  shap_imp,
            "lime_contribution": lime_cont,
            "in_shap_top":      in_shap,
            "in_lime_top":      in_lime,
            "consensus":        in_shap and in_lime,
        })

    # Sort by SHAP importance descending
    table.sort(key=lambda r: r["shap_importance"], reverse=True)

    return {
        "agreement_score":        round(agreement, 4),
        "consensus_top_features": sorted(inter),
        "shap_top_features":      shap_top,
        "lime_top_features":      lime_top,
        "per_feature_table":      table,
    }
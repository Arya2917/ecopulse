# backend/utils/trust_score.py
# ═══════════════════════════════════════════════════════════════════════════════
# AI Trust Score Engine
#
# Combines results from all 4 audit modules into a single weighted score (0–100)
# with a risk level: Safe (≥75), Medium Risk (50–74), High Risk (<50).
#
# Weights (tunable):
#   fairness        30%
#   explainability  25%
#   compliance      25%
#   energy          20%
#
# Each sub-score is computed on a 0–100 scale and then combined.
# Missing modules are excluded and weights are redistributed proportionally.
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations
import math

# ── Weight table (must sum to 1.0) ────────────────────────────────────────────
BASE_WEIGHTS = {
    "fairness":       0.30,
    "explainability": 0.25,
    "compliance":     0.25,
    "energy":         0.20,
}


def _fairness_score(data: dict) -> float:
    """
    Score based on four fairness metric differences.
    Lower difference → higher score.
    Each metric is penalised linearly: diff=0 → 100, diff≥0.5 → 0.
    """
    if not data or data.get("error"):
        return None

    overall = data.get("overall", {})
    metrics = [
        overall.get("Demographic Parity Difference",    0),
        overall.get("Equalized Odds Difference",        0),
        overall.get("False Positive Rate Difference",   0),
        overall.get("False Negative Rate Difference",   0),
    ]

    sub_scores = []
    for val in metrics:
        val = abs(val) if val is not None else 0
        # Clamp: diff ≥ 0.5 → fully penalised
        s = max(0.0, 1.0 - (val / 0.5)) * 100
        sub_scores.append(s)

    base = sum(sub_scores) / len(sub_scores)

    # Bonus: good model performance pushes score up slightly
    perf = data.get("performance", {})
    acc  = perf.get("Accuracy", 0) if perf else 0
    f1   = perf.get("F1",       0) if perf else 0
    perf_bonus = min(5.0, ((acc + f1) / 2) * 5)  # up to +5 pts

    return min(100.0, round(base + perf_bonus, 1))


def _explainability_score(data: dict) -> float:
    """
    Score based on SHAP/LIME agreement and whether both ran successfully.
    """
    if not data or data.get("error"):
        return None

    score = 50.0  # base for having explainability data at all

    shap = data.get("shap", {})
    lime = data.get("lime", {})
    agg  = data.get("aggregated", {})

    # Both methods ran
    if shap and not shap.get("error"):
        score += 20
    if lime and not lime.get("error"):
        score += 15

    # SHAP–LIME agreement
    agreement = agg.get("agreement_score") if agg else None
    if agreement is not None:
        # agreement is 0–1 (Jaccard); contribute up to +15 pts
        score += agreement * 15

    return min(100.0, round(score, 1))


def _compliance_score(data: dict) -> float:
    """
    Score based on overall compliance status and severity of PII findings.
    compliant with no findings → 100
    each critical/high finding → -15/-8 pts
    """
    if not data or data.get("error"):
        return None

    status = data.get("overall_status", "non_compliant")
    stats  = data.get("stats", {})

    if status == "compliant":
        base = 100.0
    else:
        base = 40.0  # non-compliant starts lower

    severity = stats.get("severity_counts", {}) if stats else {}
    critical = int(severity.get("critical", 0))
    high     = int(severity.get("high",     0))
    medium   = int(severity.get("medium",   0))

    penalty = critical * 15 + high * 8 + medium * 3
    score   = max(0.0, base - penalty)

    # Bonus if passing all regulations
    summary = data.get("summary", {})
    if summary:
        passing = sum(1 for v in summary.values() if v is True)
        total   = len(summary)
        if total > 0:
            reg_bonus = (passing / total) * 20
            if status == "compliant":
                score = min(100.0, score + reg_bonus * 0.1)  # small nudge when already compliant

    return round(score, 1)


def _energy_score(data: dict) -> float:
    """
    Score based on energy per epoch and carbon footprint.
    Very low energy → 100; high energy → lower score.
    Thresholds are pragmatic for typical small-to-medium ML training.
    """
    if not data or data.get("error"):
        return None

    energy_kwh = data.get("energy_kwh", 0) or 0
    carbon_kg  = data.get("carbon_kg",  0) or 0

    # Energy thresholds (kWh): ≤0.001 → 100, ≥1.0 → 0
    if energy_kwh <= 0.001:
        energy_score = 100.0
    elif energy_kwh >= 1.0:
        energy_score = 0.0
    else:
        # log-scale between 0.001 and 1.0
        log_val  = math.log10(energy_kwh)
        log_min  = math.log10(0.001)  # -3
        log_max  = math.log10(1.0)    # 0
        energy_score = max(0.0, 100.0 * (1 - (log_val - log_min) / (log_max - log_min)))

    # Carbon penalty: ≥ 0.1 kg CO₂ → additional -10 pts
    carbon_penalty = min(10.0, carbon_kg * 100)

    score = max(0.0, energy_score - carbon_penalty)

    # Bonus: system had recommendations followed (heuristic — if low energy, trust the score)
    recs = data.get("recommendations", [])
    if len(recs) > 0 and energy_kwh < 0.01:
        score = min(100.0, score + 3)  # proactive monitoring bonus

    return round(score, 1)


# ── Score calculators per module ──────────────────────────────────────────────
_SCORE_FNS = {
    "fairness":       _fairness_score,
    "explainability": _explainability_score,
    "compliance":     _compliance_score,
    "energy":         _energy_score,
}


def _risk_level(score: float) -> str:
    if score >= 75:
        return "Safe"
    if score >= 50:
        return "Medium Risk"
    return "High Risk"


def _risk_color(score: float) -> str:
    if score >= 75:
        return "green"
    if score >= 50:
        return "amber"
    return "red"


def compute_trust_score(module_results: dict) -> dict:
    """
    Compute the AI Trust Score from all available module results.

    Parameters
    ----------
    module_results : dict
        Keys are module names ("fairness", "explainability", "compliance", "energy").
        Values are the raw result dicts returned by each module's run_* function.

    Returns
    -------
    dict with keys:
        score          – float 0–100
        risk_level     – "Safe" | "Medium Risk" | "High Risk"
        risk_color     – "green" | "amber" | "red"
        breakdown      – {module: sub_score} for available modules
        weights_used   – {module: effective_weight} after redistribution
        available      – list of modules that contributed
        missing        – list of modules that were absent / errored
        summary        – human-readable one-liner
    """
    sub_scores: dict[str, float] = {}
    missing: list[str] = []

    for module, fn in _SCORE_FNS.items():
        data = module_results.get(module)
        if data is None:
            missing.append(module)
            continue
        val = fn(data)
        if val is None:
            missing.append(module)
        else:
            sub_scores[module] = val

    available = list(sub_scores.keys())

    if not available:
        return {
            "score":       None,
            "risk_level":  "Unknown",
            "risk_color":  "textDim",
            "breakdown":   {},
            "weights_used": {},
            "available":   [],
            "missing":     missing,
            "summary":     "No module results available to compute a trust score.",
        }

    # Redistribute weights for missing modules
    total_base = sum(BASE_WEIGHTS[m] for m in available)
    weights_used = {m: round(BASE_WEIGHTS[m] / total_base, 4) for m in available}

    final_score = sum(sub_scores[m] * weights_used[m] for m in available)
    final_score = round(final_score, 1)

    level = _risk_level(final_score)
    color = _risk_color(final_score)

    # Summary sentence
    if level == "Safe":
        summary = f"This model scores {final_score}/100 — it demonstrates strong responsible AI practices across the audited dimensions."
    elif level == "Medium Risk":
        worst = min(sub_scores, key=sub_scores.__getitem__)
        summary = f"Score {final_score}/100 — generally acceptable, but the {worst} dimension needs attention."
    else:
        worst = min(sub_scores, key=sub_scores.__getitem__)
        summary = f"Score {final_score}/100 — significant issues detected, especially in {worst}. Review the audit findings before deployment."

    return {
        "score":        final_score,
        "risk_level":   level,
        "risk_color":   color,
        "breakdown":    {m: round(sub_scores[m], 1) for m in available},
        "weights_used": weights_used,
        "available":    available,
        "missing":      missing,
        "summary":      summary,
    }

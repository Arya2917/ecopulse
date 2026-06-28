# backend/services/explainability_ai.py
# ═══════════════════════════════════════════════════════════════════════════════
# AI Explainability Narrator
# Reads SHAP + LIME results from the completed audit job and asks
# llama3 to explain them in plain business language.
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations
import logging

from services.ollama_service import generate

logger = logging.getLogger("ecopulse.explainability_ai")


def _build_prompt(explain: dict) -> str:
    shap      = explain.get("shap",       {})
    lime      = explain.get("lime",       {})
    agg       = explain.get("aggregated", {})
    model_info= explain.get("model_info", {})

    # Top SHAP features
    shap_importance = shap.get("feature_importance", {})
    top_shap = sorted(shap_importance.items(), key=lambda x: abs(x[1]), reverse=True)[:8]
    shap_lines = "\n".join(f"  - {f}: {v:.4f}" for f, v in top_shap) or "  - (unavailable)"

    # LIME contributions
    lime_contrib = lime.get("contributions", {})
    top_lime = sorted(lime_contrib.items(), key=lambda x: abs(x[1]), reverse=True)[:8]
    lime_lines = "\n".join(f"  - {f}: {v:.4f}" for f, v in top_lime) or "  - (unavailable)"

    # Agreement
    agreement = agg.get("agreement_score")
    consensus = agg.get("consensus_top_features", [])
    agreement_str = f"{agreement*100:.1f}%" if agreement is not None else "N/A"
    consensus_str = ", ".join(consensus[:5]) if consensus else "N/A"

    # LIME prediction
    lime_pred  = lime.get("prediction")
    lime_proba = lime.get("prediction_proba")
    pred_str   = f"{lime_pred}"
    if lime_proba is not None:
        if isinstance(lime_proba, dict):
            # e.g. {"0": 0.12, "1": 0.88} — one probability per class
            proba_str = ", ".join(f"class {k}: {float(v):.3f}" for k, v in lime_proba.items())
            pred_str += f" (probabilities: {proba_str})"
        elif isinstance(lime_proba, list):
            pred_str += f" (probabilities: {[round(float(p), 3) for p in lime_proba]})"
        elif isinstance(lime_proba, (int, float)):
            pred_str += f" (probability: {lime_proba:.3f})"
        else:
            pred_str += f" (probability: {lime_proba})"

    # Model info
    model_str = (
        f"  - Framework: {model_info.get('framework', 'N/A')}\n"
        f"  - Model class: {model_info.get('model_class', 'N/A')}\n"
        f"  - Task: {model_info.get('task', 'N/A')}\n"
        f"  - Explainer: {model_info.get('explainer_used', 'N/A')}"
    )

    prompt = f"""You are an expert AI Explainability Consultant.
You have been given SHAP and LIME explainability results from a real ML model audit.
Explain these results clearly for both technical teams and business stakeholders.

MODEL INFORMATION:
{model_str}

TOP SHAP FEATURE IMPORTANCES (higher absolute value = more impact on predictions):
{shap_lines}

TOP LIME FEATURE CONTRIBUTIONS (for a single representative sample):
{lime_lines}

SHAP-LIME AGREEMENT SCORE: {agreement_str}
CONSENSUS TOP FEATURES (agreed upon by both SHAP and LIME): {consensus_str}

SAMPLE PREDICTION: {pred_str}

INSTRUCTIONS
============
Based on the above audit data, provide a structured explanation EXACTLY as follows.
Use plain English — no LaTeX, no markdown headers with #, just the numbered sections below,
each starting on its own line with the exact number and title shown (e.g. "1. EXECUTIVE SUMMARY").

1. EXECUTIVE SUMMARY
2-3 sentences summarizing what drives this model's predictions most.

2. MOST IMPORTANT FEATURES
For each top feature, explain what it means in real-world terms and why it likely matters.

3. FEATURE INTERACTIONS
Are there features that likely interact with each other? What patterns do you see?

4. POTENTIAL BIAS INDICATORS
Based on the top features, are there any that could act as proxies for protected attributes (race, gender, age, etc.)? Flag any concerns.

5. CONFIDENCE OF EXPLANATION
Given the SHAP-LIME agreement score of {agreement_str}, how trustworthy is this explanation?

6. BUSINESS INTERPRETATION
In non-technical language: what is this model actually doing when it makes a prediction?

7. RECOMMENDATIONS
What should the data science team investigate, improve, or monitor based on these explanations?"""

    return prompt


def _parse_response(text: str) -> dict:
    result = {
        "summary":                _extract_section(text, "1. EXECUTIVE SUMMARY",       "2."),
        "important_features":     _extract_section(text, "2. MOST IMPORTANT FEATURES", "3."),
        "feature_interactions":   _extract_section(text, "3. FEATURE INTERACTIONS",   "4."),
        "bias_indicators":        _extract_section(text, "4. POTENTIAL BIAS INDICATORS","5."),
        "confidence":             _extract_section(text, "5. CONFIDENCE OF EXPLANATION","6."),
        "business_interpretation":_extract_section(text, "6. BUSINESS INTERPRETATION", "7."),
        "recommendations":        _extract_section(text, "7. RECOMMENDATIONS",         None),
        "raw": text,
    }
    # Safety net: if the model didn't follow the expected header format at all,
    # don't render a totally blank card — fall back to showing the raw response.
    if text and not any(v for k, v in result.items() if k not in ("raw",)):
        result["summary"] = text.strip()
    return result


def _extract_section(text: str, start_marker: str, end_marker: str | None) -> str:
    """
    Case-insensitive, whitespace-tolerant search for a numbered section header.
    LLMs don't always echo headers in the exact case/spacing we ask for, so we
    search on a normalized lowercase copy and map indices back to the original.
    """
    if not text:
        return ""
    lower_text = text.lower()
    start_idx = lower_text.find(start_marker.lower())
    if start_idx == -1:
        return ""
    idx_start = start_idx + len(start_marker)
    if end_marker:
        end_idx = lower_text.find(end_marker.lower(), idx_start)
        if end_idx != -1:
            return text[idx_start:end_idx].strip(" \n:-*")
    return text[idx_start:].strip(" \n:-*")


def analyze_explainability(job_id: str, jobs: dict) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise KeyError(f"Job {job_id} not found")

    explain = job.get("module_results", {}).get("explainability")
    if not explain:
        raise ValueError("Explainability results not available. Run an explainability audit first.")
    if explain.get("error"):
        raise ValueError(f"Explainability module errored: {explain['error']}")

    prompt   = _build_prompt(explain)
    logger.info("Calling Ollama for explainability analysis (job=%s)", job_id)
    raw_text = generate(prompt)
    result   = _parse_response(raw_text)
    result["job_id"] = job_id
    return result
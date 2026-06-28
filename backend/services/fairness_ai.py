# backend/services/fairness_ai.py
# ═══════════════════════════════════════════════════════════════════════════════
# AI Fairness Consultant
# Fetches existing fairness results from JOBS, builds an LLM prompt,
# and returns a structured analysis. No manual input from the user.
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations
import json
import logging

from services.ollama_service import generate

logger = logging.getLogger("ecopulse.fairness_ai")


# ── Prompt builder ─────────────────────────────────────────────────────────────

def _build_prompt(fairness: dict, monitoring_history: list | None = None) -> str:
    """
    Extracts all available fairness data and builds a rich LLM prompt.
    Gracefully handles missing keys — never crashes on partial data.
    """
    overall   = fairness.get("overall",    {})
    by_group  = fairness.get("by_group",   {})
    perf      = fairness.get("performance",{})
    suggests  = fairness.get("suggestions", [])
    dq        = fairness.get("data_quality",{})

    # ── Core metrics section ───────────────────────────────────────────────
    metrics_lines = []
    metric_map = {
        "Demographic Parity Difference": "Demographic Parity Difference",
        "Equalized Odds Difference":     "Equalized Odds Difference",
        "FPR Difference":                "False Positive Rate Difference",
        "FNR Difference":                "False Negative Rate Difference",
    }
    for key, label in metric_map.items():
        val = overall.get(key)
        if val is not None:
            metrics_lines.append(f"  - {label}: {val:.4f}")

    metrics_block = "\n".join(metrics_lines) if metrics_lines else "  - (no overall metrics available)"

    # ── Group breakdown ────────────────────────────────────────────────────
    group_lines = []
    for grp, stats in by_group.items():
        if isinstance(stats, dict):
            sr  = stats.get("Selection Rate", stats.get("selection_rate", "N/A"))
            fpr = stats.get("False Positive Rate", "N/A")
            fnr = stats.get("False Negative Rate", "N/A")
            n   = stats.get("Count", stats.get("count", "N/A"))
            group_lines.append(
                f"  - {grp}: selection_rate={sr}, FPR={fpr}, FNR={fnr}, n={n}"
            )
    groups_block = "\n".join(group_lines) if group_lines else "  - (no group breakdown available)"

    # ── Performance ────────────────────────────────────────────────────────
    perf_lines = []
    for k in ["accuracy", "precision", "recall", "f1", "roc_auc"]:
        v = perf.get(k)
        if v is not None:
            perf_lines.append(f"  - {k.capitalize()}: {v:.4f}")
    perf_block = "\n".join(perf_lines) if perf_lines else "  - (no performance metrics)"

    # ── Suggestions ────────────────────────────────────────────────────────
    if isinstance(suggests, list):
        sugg_block = "\n".join(f"  - {s}" for s in suggests[:6]) or "  - (none)"
    else:
        sugg_block = f"  - {suggests}"

    # ── Monitoring drift history ───────────────────────────────────────────
    drift_block = ""
    if monitoring_history:
        drift_block = "\n\nREAL-TIME MONITORING DRIFT HISTORY:\n"
        for snap in monitoring_history[-5:]:  # last 5 snapshots
            ts      = snap.get("timestamp", "")[:19]
            dp_gap  = snap.get("dp_gap", "N/A")
            alerts  = len(snap.get("alerts", []))
            drift_block += f"  - {ts}  DP gap={dp_gap}  alerts_fired={alerts}\n"
        drift_block += "Trend: analyze whether DP gap is increasing, stable, or decreasing.\n"

    prompt = f"""You are an expert AI Fairness Consultant analyzing a real fairness audit.

AUDIT RESULTS
=============

FAIRNESS METRICS (lower absolute values = fairer):
{metrics_block}

GROUP BREAKDOWN:
{groups_block}

MODEL PERFORMANCE:
{perf_block}

SYSTEM SUGGESTIONS FROM AUDIT ENGINE:
{sugg_block}
{drift_block}

INSTRUCTIONS
============
Based on the above audit data, provide a thorough fairness analysis structured EXACTLY as follows.
Use plain English — no LaTeX, no markdown headers with #, just numbered sections.
Be specific and reference the actual numbers above.

1. EXECUTIVE SUMMARY
A 3-4 sentence overview of the overall fairness health of this model.

2. FAIRNESS RISK LEVEL
State one of: LOW / MEDIUM / HIGH / CRITICAL — and justify with specific metric values.

3. ROOT CAUSE ANALYSIS
What is likely causing the observed fairness gaps? Reference specific groups and metrics.

4. AFFECTED GROUPS
Which demographic groups are most disadvantaged, and by how much?

5. POTENTIAL SOURCES OF BIAS
List 3-5 likely sources (data collection, historical bias, proxy features, etc.)

6. RECOMMENDED MITIGATIONS
List 4-6 concrete, actionable steps to reduce bias (preprocessing, in-processing, post-processing).

7. TRADE-OFFS
What accuracy or business trade-offs should be expected when applying mitigations?

8. MONITORING RECOMMENDATIONS
How should this model be monitored in production? What thresholds and cadence?"""

    return prompt


# ── Response parser ────────────────────────────────────────────────────────────

def _parse_response(text: str) -> dict:
    """
    Extracts numbered sections from the LLM response into a clean dict.
    Falls back gracefully if the model doesn't follow the format exactly.
    """
    sections = {
        "summary":         _extract_section(text, "1. EXECUTIVE SUMMARY",       "2."),
        "risk_level":      _extract_section(text, "2. FAIRNESS RISK LEVEL",     "3."),
        "root_causes":     _extract_section(text, "3. ROOT CAUSE ANALYSIS",     "4."),
        "affected_groups": _extract_section(text, "4. AFFECTED GROUPS",         "5."),
        "recommendations": _extract_section(text, "6. RECOMMENDED MITIGATIONS", "7."),
        "tradeoffs":       _extract_section(text, "7. TRADE-OFFS",              "8."),
        "monitoring":      _extract_section(text, "8. MONITORING RECOMMENDATIONS", None),
        "raw":             text,
    }
    # Safety net: if the model didn't follow the expected header format at all,
    # don't render a totally blank card — fall back to showing the raw response.
    if text and not any(v for k, v in sections.items() if k != "raw"):
        sections["summary"] = text.strip()
    return sections


def _extract_section(text: str, start_marker: str, end_marker: str | None) -> str:
    """
    Case-insensitive, whitespace-tolerant search for a numbered section header.
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


# ── Public entry point ─────────────────────────────────────────────────────────

def analyze_fairness(job_id: str, jobs: dict, monitors: dict | None = None) -> dict:
    """
    Called by the Flask route. Fetches fairness data from JOBS,
    optionally enriches with monitoring history, calls Ollama, returns analysis.
    """
    job = jobs.get(job_id)
    if not job:
        raise KeyError(f"Job {job_id} not found")

    fairness = job.get("module_results", {}).get("fairness")
    if not fairness:
        raise ValueError("Fairness results not available for this job. Run a fairness audit first.")
    if fairness.get("error"):
        raise ValueError(f"Fairness module errored: {fairness['error']}")

    # Pull monitoring history if any monitor references this job's sensitive col
    monitoring_history = None
    if monitors:
        sensitive_col = fairness.get("sensitive", "")
        for mon in monitors.values():
            if mon.get("sensitive_col") == sensitive_col and mon.get("snapshots"):
                monitoring_history = mon["snapshots"]
                break

    prompt   = _build_prompt(fairness, monitoring_history)
    logger.info("Calling Ollama for fairness analysis (job=%s)", job_id)
    raw_text = generate(prompt)
    result   = _parse_response(raw_text)
    result["job_id"] = job_id
    return result
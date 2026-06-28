# backend/services/compliance_ai.py
# ═══════════════════════════════════════════════════════════════════════════════
# AI Compliance Advisor
# Reads compliance scan results (PII/PHI findings, regulation scores)
# from the completed audit and generates a legal + compliance analysis.
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations
import logging

from services.ollama_service import generate

logger = logging.getLogger("ecopulse.compliance_ai")


def _build_prompt(compliance: dict) -> str:
    findings      = compliance.get("findings",       [])
    column_report = compliance.get("column_report",  [])   # list of dicts: {name, pii_entities, severity, regulations, hit_counts}
    summary       = compliance.get("summary",        {})   # {regulation: "compliant" | "non_compliant"}

    # Regulation summary (status-based, not numeric scores)
    reg_lines = []
    for reg in ["GDPR", "HIPAA", "CCPA", "ISO27001", "PCI_DSS"]:
        status = summary.get(reg)
        if status is not None:
            label = "PASS" if status == "compliant" else "FAIL"
            reg_lines.append(f"  - {reg}: {status.upper()} ({label})")
    if not reg_lines:
        reg_lines = ["  - (regulation status not available)"]

    # Severity breakdown (column_report severities are lowercase: critical/high/medium/low)
    high   = [f for f in findings if (f.get("severity") or "").lower() in ("high", "critical")]
    medium = [f for f in findings if (f.get("severity") or "").lower() == "medium"]
    low    = [f for f in findings if (f.get("severity") or "").lower() == "low"]

    # PII columns — column_report is a LIST of dicts, not a dict keyed by column name
    pii_cols = []
    for col_info in column_report:
        name = col_info.get("name", "unknown")
        ents = col_info.get("pii_entities", [])
        sev  = col_info.get("severity", "unknown")
        pii_cols.append(f"  - {name}: {', '.join(ents[:3]) or 'PII detected'}  [{sev}]")

    pii_block = "\n".join(pii_cols[:10]) if pii_cols else "  - (no PII columns detected)"

    # Sample findings detail — findings only exist for non_compliant regulations here,
    # and carry 'affected_columns' (list) + 'rule_description', not a single 'column'/'entity_type'
    violations = [f for f in findings if f.get("status") == "non_compliant"]
    finding_lines = []
    for f in violations[:8]:
        reg   = f.get("regulation", "")
        sev   = f.get("severity", "unknown")
        rule  = f.get("rule_description", "")
        cols  = ", ".join(f.get("affected_columns", [])[:5]) or "unknown"
        finding_lines.append(f"  - [{sev.upper()}] {reg} — {rule} (columns: {cols})")
    findings_block = "\n".join(finding_lines) if finding_lines else "  - (no critical findings)"

    prompt = f"""You are a senior legal and data compliance advisor specializing in AI and data privacy regulations.
You have been given a compliance scan report from an AI system audit.

REGULATION COMPLIANCE STATUS:
{chr(10).join(reg_lines)}

PII/PHI DETECTED COLUMNS:
{pii_block}

FINDINGS SUMMARY:
  - Total findings: {len(findings)}
  - HIGH severity: {len(high)}
  - MEDIUM severity: {len(medium)}
  - LOW severity: {len(low)}

KEY FINDINGS (HIGH and MEDIUM severity):
{findings_block}

INSTRUCTIONS
============
Provide a compliance analysis in plain English. No LaTeX. No markdown # headers.
Reference the actual regulation status and findings above.

1. COMPLIANCE SUMMARY
Overall compliance posture in 3-4 sentences. Which regulations are at risk?

2. RISK LEVEL
State one of: LOW / MEDIUM / HIGH / CRITICAL — justify with specific findings.

3. REGULATORY VIOLATIONS
For each failing regulation, what specific rules are being violated and why?

4. LEGAL IMPLICATIONS
What are the real-world legal consequences of these findings? (fines, enforcement, reputational risk)

5. RECOMMENDED ACTIONS
List 5-6 specific, actionable steps to remediate the findings immediately.

6. COMPLIANCE ROADMAP
A phased 30-60-90 day plan to achieve full compliance across all relevant regulations."""

    return prompt


def _parse_response(text: str) -> dict:
    result = {
        "summary":             _extract_section(text, "1. COMPLIANCE SUMMARY",   "2."),
        "risk":                _extract_section(text, "2. RISK LEVEL",           "3."),
        "violations":          _extract_section(text, "3. REGULATORY VIOLATIONS","4."),
        "legal_implications":  _extract_section(text, "4. LEGAL IMPLICATIONS",  "5."),
        "recommendations":     _extract_section(text, "5. RECOMMENDED ACTIONS", "6."),
        "roadmap":             _extract_section(text, "6. COMPLIANCE ROADMAP",   None),
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


def analyze_compliance(job_id: str, jobs: dict) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise KeyError(f"Job {job_id} not found")

    compliance = job.get("module_results", {}).get("compliance")
    if not compliance:
        raise ValueError("Compliance results not available. Run a compliance audit first.")
    if compliance.get("error"):
        raise ValueError(f"Compliance module errored: {compliance['error']}")

    prompt   = _build_prompt(compliance)
    logger.info("Calling Ollama for compliance analysis (job=%s)", job_id)
    raw_text = generate(prompt)
    result   = _parse_response(raw_text)
    result["job_id"] = job_id
    return result
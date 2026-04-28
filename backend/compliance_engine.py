"""
compliance_engine.py
====================
Pure-Python PII/PHI detection engine using Microsoft Presidio.
No FastAPI / Flask dependency — imported by tasks/compliance.py and
the Flask route handlers in app.py.

Ported from the original FastAPI presidio_wrapper.py + schemas.py.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

logger = logging.getLogger("compliance_engine")

# ── Try Presidio (optional — falls back to regex) ─────────────────────────
try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    _nlp_cfg = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
    }
    _nlp_engine = NlpEngineProvider(_nlp_cfg).create_engine()
    _analyzer   = AnalyzerEngine(nlp_engine=_nlp_engine)
    PRESIDIO_AVAILABLE = True
    logger.info("Microsoft Presidio loaded ✓")
except Exception as _e:
    _analyzer          = None
    PRESIDIO_AVAILABLE = False
    logger.warning("Presidio not available (%s) — regex fallback active.", _e)

# ── Severity / entity constants ────────────────────────────────────────────
_CRITICAL = {"US_SSN", "CREDIT_CARD", "US_PASSPORT", "MEDICAL_LICENSE",
             "US_BANK_NUMBER", "IBAN_CODE", "CRYPTO"}
_HIGH     = {"EMAIL_ADDRESS", "PHONE_NUMBER", "PERSON",
             "US_DRIVER_LICENSE", "UK_NHS", "AU_MEDICARE"}
_MEDIUM   = {"LOCATION", "ADDRESS", "DATE_TIME", "IP_ADDRESS"}

# Only these trigger a PII finding when Presidio is on
_HIGH_RISK_PII = _CRITICAL | _HIGH

_PII_KW  = ["email","phone","ssn","social_security","passport","driver_license",
            "credit_card","card_number","cvv","ccn","dob","date_of_birth"]
_PHI_KW  = ["patient","diagnosis","medical","health","prescription","treatment",
            "doctor","physician","hospital","clinic","mrn","phi","lab",
            "symptom","disease","medication","procedure","surgery","icd","cpt","dob"]

_REGEX   = {
    "EMAIL_ADDRESS": re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    "PHONE_NUMBER":  re.compile(r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "US_SSN":        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD":   re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "IP_ADDRESS":    re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
}


# ── helpers ───────────────────────────────────────────────────────────────

def _severity(entity_type: str) -> str:
    et = entity_type.upper()
    if et in _CRITICAL: return "critical"
    if et in _HIGH:     return "high"
    if et in _MEDIUM:   return "medium"
    return "low"


def _worst_severity(severities: list[str]) -> str:
    order = ["low", "medium", "high", "critical"]
    return max(severities, key=lambda s: order.index(s), default="low")


def _analyze_text(text: str) -> dict[str, int]:
    """Return {entity_type: count} using Presidio or regex fallback."""
    if not text or not text.strip():
        return {}
    hits: dict[str, int] = {}
    if PRESIDIO_AVAILABLE and _analyzer:
        try:
            results = _analyzer.analyze(text=str(text), language="en",
                                        score_threshold=0.7)
            for r in results:
                if r.entity_type in _HIGH_RISK_PII:
                    hits[r.entity_type] = hits.get(r.entity_type, 0) + 1
            return hits
        except Exception as e:
            logger.warning("Presidio analyze error: %s", e)
    # regex fallback
    for entity, pattern in _REGEX.items():
        count = len(pattern.findall(text))
        if count:
            hits[entity] = count
    return hits


def _scan_column(col_name: str, sample_values: list[str]) -> dict[str, int]:
    """Combine column-name keyword check + value scan."""
    hits: dict[str, int] = {}
    name_lower = col_name.lower()

    # keyword check on column name
    if any(kw in name_lower for kw in _PII_KW):
        hits["COLUMN_NAME_PII"] = 1
    if any(kw in name_lower for kw in _PHI_KW):
        hits["COLUMN_NAME_PHI"] = 1

    # value scan (skip pure-numeric columns)
    clean = [str(v) for v in sample_values if v and str(v).strip()]
    text  = " | ".join(clean)
    if text.strip():
        hits.update(_analyze_text(text))
    return hits


# ── CSV → column reports ──────────────────────────────────────────────────

def scan_csv_bytes(
    content: bytes,
    regulations: list[str] | None = None,
    strict_mode: bool = False,
    dataset_name: str = "",
    owner: str = "",
    tags: list[str] | None = None,
    dataset_id: str = "",
) -> dict[str, Any]:
    """
    Parse *content* (raw CSV bytes) and run a full compliance scan.

    Returns a plain dict (JSON-serialisable) with shape:
    {
        scan_id, dataset_id, scanned_at, overall_status,
        findings:       [ { regulation, rule_id, rule_description,
                            status, severity, affected_columns,
                            details, remediation } ],
        summary:        { regulation: status },
        column_report:  [ { name, pii_entities, severity, regulations } ],
        stats:          { total_columns, pii_columns, … },
        engine:         "presidio" | "regex",
    }
    """
    if regulations is None:
        regulations = ["GDPR", "HIPAA", "CCPA", "ISO27001", "PCI_DSS"]
    if tags is None:
        tags = []

    # Parse CSV
    try:
        text = content.decode("utf-8-sig")
        df   = pd.read_csv(io.StringIO(text), nrows=200)
    except Exception as exc:
        return {"error": f"Could not parse CSV: {exc}"}

    if not dataset_id:
        dataset_id = f"csv_{uuid.uuid4().hex[:8]}"

    # ── Per-column scan ────────────────────────────────────────────────
    column_report: list[dict] = []
    all_entities: set[str]    = set()

    for col in df.columns:
        # skip numeric columns
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        sample = df[col].dropna().head(20).astype(str).tolist()
        hits   = _scan_column(col, sample)
        if hits:
            entities = set(hits.keys())
            all_entities |= entities
            worst = _worst_severity([_severity(e) for e in entities])
            regs  = _map_to_regulations(entities)
            column_report.append({
                "name":         col,
                "pii_entities": list(entities),
                "severity":     worst,
                "regulations":  regs,
                "hit_counts":   hits,
            })

    # ── Build findings per regulation ─────────────────────────────────
    findings = _build_findings(all_entities, column_report, regulations, tags, strict_mode)

    # ── Summary ────────────────────────────────────────────────────────
    summary: dict[str, str] = {}
    for reg in regulations:
        reg_findings = [f for f in findings if f["regulation"] == reg]
        if any(f["status"] == "non_compliant" for f in reg_findings):
            summary[reg] = "non_compliant"
        else:
            summary[reg] = "compliant"

    overall = "non_compliant" if "non_compliant" in summary.values() else "compliant"

    sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for c in column_report:
        sev_counts[c["severity"]] = sev_counts.get(c["severity"], 0) + 1

    return {
        "scan_id":       str(uuid.uuid4()),
        "dataset_id":    dataset_id,
        "dataset_name":  dataset_name or dataset_id,
        "scanned_at":    datetime.utcnow().isoformat(),
        "overall_status": overall,
        "findings":      findings,
        "summary":       summary,
        "column_report": column_report,
        "stats": {
            "total_columns":     len(df.columns),
            "pii_columns":       len(column_report),
            "regulations_failed": sum(1 for s in summary.values() if s == "non_compliant"),
            **sev_counts,
        },
        "engine": "presidio" if PRESIDIO_AVAILABLE else "regex",
    }


# ── regulation mapping ────────────────────────────────────────────────────

def _map_to_regulations(entities: set[str]) -> list[str]:
    pii_types = (_HIGH_RISK_PII | {"COLUMN_NAME_PII"})
    phi_types = {"MEDICAL_LICENSE", "COLUMN_NAME_PHI"}
    card_types = {"CREDIT_CARD", "US_BANK_NUMBER", "IBAN_CODE"}

    regs: list[str] = []
    if entities & pii_types:
        regs += ["GDPR", "CCPA", "ISO27001"]
    if entities & phi_types:
        regs.append("HIPAA")
    if entities & card_types:
        regs.append("PCI_DSS")
    return list(dict.fromkeys(regs))   # deduplicate, preserve order


# ── findings builder ──────────────────────────────────────────────────────

_REG_META = {
    "GDPR":    ("GDPR-001",    "Data Minimisation & PII Protection",
                "Anonymise or pseudonymise personal identifiers before training."),
    "HIPAA":   ("HIPAA-001",   "Protected Health Information (PHI) Handling",
                "De-identify all PHI fields per HIPAA Safe Harbor method."),
    "CCPA":    ("CCPA-001",    "Consumer Personal Information Rights",
                "Filter opted-out records and implement deletion support."),
    "ISO27001":("ISO27001-001","Information Security Access Controls",
                "Enforce RBAC and tag dataset with 'access_controlled'."),
    "PCI_DSS": ("PCIDSS-001",  "Cardholder Data Security",
                "Remove/tokenise all card numbers. Never store raw PANs."),
}


def _build_findings(
    all_entities: set[str],
    column_report: list[dict],
    regulations: list[str],
    tags: list[str],
    strict_mode: bool,
) -> list[dict]:
    findings: list[dict] = []

    pii_cols  = [c["name"] for c in column_report]
    phi_cols  = [c["name"] for c in column_report
                 if "COLUMN_NAME_PHI" in c["pii_entities"]]
    card_cols = [c["name"] for c in column_report
                 if "CREDIT_CARD" in c["pii_entities"]
                 or "US_BANK_NUMBER" in c["pii_entities"]]

    pii_present  = bool(all_entities & (_HIGH_RISK_PII | {"COLUMN_NAME_PII"}))
    phi_present  = bool(all_entities & {"MEDICAL_LICENSE", "COLUMN_NAME_PHI"})
    card_present = bool(card_cols)

    for reg in regulations:
        meta = _REG_META.get(reg, (f"{reg}-001", reg, "Remediate manually."))
        violated = False
        affected: list[str] = []
        details  = ""
        sev      = "low"

        if reg == "GDPR" and pii_present:
            violated = True
            affected = pii_cols
            sev      = _worst_severity([_severity(e) for e in all_entities])
            details  = (f"PII detected ({'Presidio' if PRESIDIO_AVAILABLE else 'regex'})."
                        f" Entities: {', '.join(sorted(all_entities)[:6])}.")

        elif reg == "HIPAA" and phi_present:
            violated = True
            affected = phi_cols
            sev      = "critical"
            details  = f"PHI columns detected: {phi_cols}."

        elif reg == "CCPA" and pii_present:
            violated = True
            affected = pii_cols
            sev      = "high"
            details  = "Personal information present without opt-out filtering tag."

        elif reg == "ISO27001" and pii_present:
            ac_tag  = any(t.lower() in ("access_controlled", "rbac_enforced") for t in tags)
            if not ac_tag:
                violated = True
                affected = pii_cols
                sev      = "high"
                details  = "Sensitive data without documented access-control tags."

        elif reg == "PCI_DSS" and card_present:
            violated = True
            affected = card_cols
            sev      = "critical"
            details  = f"Payment card data detected in columns: {card_cols}."

        findings.append({
            "regulation":       reg,
            "rule_id":          meta[0],
            "rule_description": meta[1],
            "status":           "non_compliant" if violated else "compliant",
            "severity":         sev,
            "affected_columns": affected,
            "details":          details if violated else "No violations detected.",
            "remediation":      meta[2] if violated else "",
        })

    return findings


# ── regulations list (for the /compliance/regulations endpoint) ───────────
SUPPORTED_REGULATIONS = [
    {"tag": "GDPR",     "description": "General Data Protection Regulation (EU)"},
    {"tag": "HIPAA",    "description": "Health Insurance Portability and Accountability Act (US)"},
    {"tag": "CCPA",     "description": "California Consumer Privacy Act (US)"},
    {"tag": "ISO27001", "description": "ISO/IEC 27001 Information Security Management"},
    {"tag": "PCI_DSS",  "description": "Payment Card Industry Data Security Standard"},
]

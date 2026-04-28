"""
tasks/compliance.py
===================
Compliance module runner — called by the orchestrator in app.py via
MODULE_RUNNERS["compliance"].

Signature matches all other task runners:
    run_compliance(csv_path, **kwargs) -> dict
"""

from __future__ import annotations

import logging
from typing import Any

from compliance_engine import scan_csv_bytes

logger = logging.getLogger("tasks.compliance")


def run_compliance(csv_path: str, **kwargs) -> dict[str, Any]:
    """
    Read *csv_path*, run a full PII/PHI compliance scan, and return a
    plain dict stored in job["module_results"]["compliance"].

    All extra kwargs (target, sensitive, etc.) are accepted but unused —
    compliance scanning works purely at the column/value level.
    """
    try:
        with open(csv_path, "rb") as fh:
            content = fh.read()

        result = scan_csv_bytes(
            content     = content,
            regulations = ["GDPR", "HIPAA", "CCPA", "ISO27001", "PCI_DSS"],
            strict_mode = False,
            dataset_id  = csv_path,
        )
        return result

    except Exception as exc:
        logger.error("Compliance task failed: %s", exc, exc_info=True)
        return {"error": str(exc)}
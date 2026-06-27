# backend/tasks/monitoring.py
# ═══════════════════════════════════════════════════════════════════════════════
# EcoPulse Real-Time Monitoring — core logic
#
# create_monitor()   – seed a monitor from an existing audit job's fairness results
# ingest_batch()     – push a new prediction batch; compute drift + fire alerts
# _psi()             – Population Stability Index helper
# ═══════════════════════════════════════════════════════════════════════════════

import uuid
import math
from datetime import datetime, timezone

from monitoring_store import MONITORS, persist


# ── PSI helper ─────────────────────────────────────────────────────────────────

def _psi(expected: float, actual: float, eps: float = 1e-6) -> float:
    """
    Simplified single-bin PSI for a binary selection rate.
    PSI = (actual − expected) × ln(actual / expected)
    Thresholds: <0.1 = stable, 0.1–0.25 = slight shift, >0.25 = significant drift
    """
    e = max(expected, eps)
    a = max(actual,   eps)
    return (a - e) * math.log(a / e)


# ── Create a monitor ───────────────────────────────────────────────────────────

def create_monitor(
    name: str,
    sensitive_col: str,
    target_col: str,
    baseline_group_rates: dict,        # { group_label: selection_rate_float }
    dp_threshold: float = 0.1,
    psi_warning: float  = 0.1,
    psi_critical: float = 0.25,
) -> str:
    """
    Create and register a new drift monitor.

    Parameters
    ----------
    name                 : Human-readable label.
    sensitive_col        : Name of the sensitive attribute column.
    target_col           : Name of the target/label column.
    baseline_group_rates : Dict mapping each group value to its baseline
                           positive-prediction selection rate.
    dp_threshold         : Demographic-parity gap that triggers an alert.
    psi_warning          : PSI level that triggers a WARNING alert.
    psi_critical         : PSI level that triggers a CRITICAL alert.

    Returns
    -------
    monitor_id : str
    """
    monitor_id = str(uuid.uuid4())
    MONITORS[monitor_id] = {
        "id":                   monitor_id,
        "name":                 name,
        "sensitive_col":        sensitive_col,
        "target_col":           target_col,
        "baseline_group_rates": baseline_group_rates,
        "thresholds": {
            "dp_threshold":  dp_threshold,
            "psi_warning":   psi_warning,
            "psi_critical":  psi_critical,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status":     "active",
        "snapshots":  [],
        "alerts":     [],
    }
    persist()
    return monitor_id


# ── Ingest a prediction batch ──────────────────────────────────────────────────

def ingest_batch(monitor_id: str, rows: list[dict]) -> dict:
    """
    Push a new batch of prediction rows into the monitor.

    Parameters
    ----------
    monitor_id : str — must exist in MONITORS
    rows       : list of dicts, each must contain at minimum
                 { sensitive_col_value: ..., prediction: 0|1 }
                 Keys: "sensitive", "prediction"

    Returns
    -------
    snapshot dict with drift_scores, alerts fired this batch, etc.
    """
    mon = MONITORS.get(monitor_id)
    if mon is None:
        raise KeyError(f"Monitor {monitor_id} not found")
    if mon["status"] != "active":
        raise ValueError("Monitor is paused")

    sensitive_col = mon["sensitive_col"]
    baseline      = mon["baseline_group_rates"]   # { group: float }
    thresholds    = mon["thresholds"]

    # ── Tally predictions per group ────────────────────────────────────────
    group_counts = {}     # { group: {"pos": int, "total": int} }
    for row in rows:
        group = str(row.get("sensitive", "unknown"))
        pred  = int(row.get("prediction", 0))
        if group not in group_counts:
            group_counts[group] = {"pos": 0, "total": 0}
        group_counts[group]["total"] += 1
        group_counts[group]["pos"]   += pred

    group_rates = {
        g: (v["pos"] / v["total"]) if v["total"] > 0 else 0.0
        for g, v in group_counts.items()
    }

    # ── Compute drift scores ───────────────────────────────────────────────
    drift_scores = {}
    for group, rate in group_rates.items():
        base_rate = baseline.get(group, 0.5)   # default 0.5 if new group
        drift_scores[group] = {
            "baseline_rate":  round(base_rate, 4),
            "current_rate":   round(rate,      4),
            "delta":          round(rate - base_rate, 4),
            "psi":            round(_psi(base_rate, rate), 4),
        }

    # ── Demographic-parity gap in current batch ────────────────────────────
    rates_list = list(group_rates.values())
    dp_gap = (max(rates_list) - min(rates_list)) if len(rates_list) >= 2 else 0.0

    # ── Fire alerts ────────────────────────────────────────────────────────
    batch_alerts = []
    now_ts = datetime.now(timezone.utc).isoformat()

    for group, ds in drift_scores.items():
        psi = ds["psi"]
        if psi >= thresholds["psi_critical"]:
            msg = (f"CRITICAL drift on group '{group}': PSI={psi:.3f} "
                   f"(baseline {ds['baseline_rate']:.2%} → current {ds['current_rate']:.2%})")
            batch_alerts.append({"timestamp": now_ts, "level": "critical", "message": msg, "group": group})
        elif psi >= thresholds["psi_warning"]:
            msg = (f"WARNING drift on group '{group}': PSI={psi:.3f} "
                   f"(baseline {ds['baseline_rate']:.2%} → current {ds['current_rate']:.2%})")
            batch_alerts.append({"timestamp": now_ts, "level": "warning", "message": msg, "group": group})

    if dp_gap > thresholds["dp_threshold"]:
        msg = (f"Demographic-parity gap exceeded threshold: "
               f"gap={dp_gap:.3f} > threshold={thresholds['dp_threshold']:.3f}")
        batch_alerts.append({"timestamp": now_ts, "level": "warning", "message": msg, "group": "all"})

    # ── Build snapshot ──────────────────────────────────────────────────────
    snapshot = {
        "timestamp":    now_ts,
        "batch_size":   len(rows),
        "group_rates":  group_rates,
        "drift_scores": drift_scores,
        "dp_gap":       round(dp_gap, 4),
        "alerts":       batch_alerts,
    }

    mon["snapshots"].append(snapshot)
    mon["alerts"].extend(batch_alerts)

    # Keep rolling window: last 200 snapshots only
    if len(mon["snapshots"]) > 200:
        mon["snapshots"] = mon["snapshots"][-200:]

    persist()
    return snapshot
# backend/monitoring_store.py
# ═══════════════════════════════════════════════════════════════════════════════
# In-memory store for monitoring sessions + simple JSON file persistence.
# Kept separate from app.py to avoid bloating the orchestrator.
# ═══════════════════════════════════════════════════════════════════════════════

import json
import os
from datetime import datetime

MONITORS_FILE = os.path.join(os.path.dirname(__file__), "monitors.json")

# monitor_id → {
#   id, name, sensitive_col, target_col, baseline_rates, thresholds,
#   created_at, status ("active" | "paused"),
#   snapshots: [ { timestamp, batch_size, group_rates, drift_scores, alerts } ],
#   alerts: [ { timestamp, level, message } ]
# }
MONITORS: dict = {}


def _serialize(obj):
    """JSON-serialise datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def persist():
    """Write MONITORS to disk (best-effort — never raises)."""
    try:
        with open(MONITORS_FILE, "w") as fh:
            json.dump(MONITORS, fh, default=_serialize, indent=2)
    except Exception:
        pass


def load_from_disk():
    """Load MONITORS from disk on startup."""
    global MONITORS
    if os.path.exists(MONITORS_FILE):
        try:
            with open(MONITORS_FILE) as fh:
                MONITORS = json.load(fh)
        except Exception:
            MONITORS = {}


# Load on import
load_from_disk()
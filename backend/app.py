# backend/app.py
# ═══════════════════════════════════════════════════════════════════════════════
# EcoPulse Orchestrator — Sequential Audit Engine
#
# Workflow:
#   1. POST /audit/start  → saves files, creates job, spawns sequential worker
#   2. Worker runs modules one at a time: fairness → explainability → compliance → energy
#   3. After each module finishes, worker PAUSES and sets job["gate"] = "open"
#   4. Frontend polls /audit/status, sees current module is "done", shows popup
#   5. User clicks OK → frontend POSTs /audit/ack/<job_id> → worker resumes
#   6. After last module: job["status"] = "done"
#   7. GET /audit/report/<job_id> → downloads unified HTML report
#
# Mitigation (separate flow):
#   POST /mitigate_async or /mitigate_user_model_async
#   GET  /progress/<job_id>  →  GET /result/<job_id>
#   GET  /download_model/<model_id>
# ═══════════════════════════════════════════════════════════════════════════════

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os, uuid, json, time
from datetime import datetime
from threading import Thread, Event

from tasks.fairness       import run_fairness
from tasks.explainability import run_explainability
from tasks.compliance     import run_compliance
from tasks.energy         import run_energy
from report.generator     import generate_unified_report
from utils.trust_score    import compute_trust_score

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")

# ── In-memory job store ────────────────────────────────────────────────────────
# job_id → {
#   modules, status, module_status, module_results,
#   current_module, gate_event (threading.Event),
#   params, created_at
# }
JOBS = {}

app = Flask(__name__)
CORS(app)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs("saved_models_fairness", exist_ok=True)
os.makedirs("reports", exist_ok=True)

# Fixed execution order — regardless of which subset the user picks,
# the ones selected always run in this order.
MODULE_ORDER = ["fairness", "explainability", "compliance", "energy"]

MODULE_RUNNERS = {
    "fairness":       run_fairness,
    "explainability": run_explainability,
    "compliance":     run_compliance,
    "energy":         run_energy,
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _save_upload(file_obj, suffix=""):
    fname = f"{uuid.uuid4()}{suffix}"
    path  = os.path.join(UPLOAD_DIR, fname)
    file_obj.save(path)
    return path


# ── Sequential worker ──────────────────────────────────────────────────────────

def _sequential_worker(job_id: str):
    """
    Runs each selected module in order.
    After every module completes it waits for an ACK from the frontend
    (via POST /audit/ack/<job_id>) before proceeding to the next one.
    """
    job = JOBS[job_id]
    ordered = [m for m in MODULE_ORDER if m in job["modules"]]

    for i, module_name in enumerate(ordered):
        job["current_module"]              = module_name
        job["module_status"][module_name]  = "running"

        # ── Run the module ──────────────────────────────────────────────────
        try:
            result = MODULE_RUNNERS[module_name](**job["params"])
            job["module_results"][module_name] = result
            job["module_status"][module_name]  = "done"
        except Exception as exc:
            job["module_results"][module_name] = {"error": str(exc)}
            job["module_status"][module_name]  = "error"

        # ── Pause and wait for frontend ACK (unless this is the last module) ─
        is_last = (i == len(ordered) - 1)
        if not is_last:
            job["awaiting_ack"] = True
            job["gate_event"].clear()          # close the gate
            job["gate_event"].wait(timeout=300)  # wait up to 5 min for user
            job["awaiting_ack"] = False

    # All modules finished — compute AI Trust Score
    job["status"]         = "done"
    job["current_module"] = None
    job["trust_score"]    = compute_trust_score(job["module_results"])


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.route("/audit/start", methods=["POST"])
def audit_start():
    """
    POST multipart/form-data
      file            – CSV dataset (required)
      modules         – comma-separated: fairness,explainability,compliance,energy
      target          – target column name
      sensitive       – sensitive attribute column  (fairness)
      pred_col        – optional prediction column
      train_baseline  – "1" / "0"
      user_model      – optional .pkl model file
      wrap_model      – "1" / "0"
      dp_threshold    – float, default 0.1
      eo_threshold    – float, default 0.1
      fpr_threshold   – float, default 0.1
      fnr_threshold   – float, default 0.1
      epochs          – int, default 1  (energy module)
    """
    if "file" not in request.files:
        return jsonify({"error": "No CSV file uploaded"}), 400

    modules_raw      = request.form.get("modules", "fairness")
    selected_modules = [m.strip() for m in modules_raw.split(",")
                        if m.strip() in MODULE_RUNNERS]
    if not selected_modules:
        return jsonify({"error": "No valid modules selected"}), 400

    # Save uploaded files
    csv_path   = _save_upload(request.files["file"], ".csv")
    model_path = None
    if "user_model" in request.files:
        mf         = request.files["user_model"]
        ext        = os.path.splitext(mf.filename)[1] or ".pkl"
        model_path = _save_upload(mf, ext)

    params = {
        "csv_path":       csv_path,
        "target":         request.form.get("target", ""),
        "sensitive":      request.form.get("sensitive", ""),
        "pred_col":       request.form.get("pred_col") or None,
        "train_baseline": request.form.get("train_baseline", "1") in ("1", "true", "yes"),
        "model_path":     model_path,
        "wrap_model":     request.form.get("wrap_model", "0") in ("1", "true", "yes"),
        "dp_threshold":   float(request.form.get("dp_threshold",  0.1)),
        "eo_threshold":   float(request.form.get("eo_threshold",  0.1)),
        "fpr_threshold":  float(request.form.get("fpr_threshold", 0.1)),
        "fnr_threshold":  float(request.form.get("fnr_threshold", 0.1)),
        "epochs":         int(request.form.get("epochs", 1)),
    }

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "modules":        selected_modules,
        "status":         "running",
        "module_status":  {m: "queued" for m in selected_modules},
        "module_results": {},
        "current_module": None,
        "awaiting_ack":   False,
        "gate_event":     Event(),
        "params":         params,
        "created_at":     datetime.now().isoformat(),
    }
    # Open the gate initially so first module starts immediately
    JOBS[job_id]["gate_event"].set()

    Thread(target=_sequential_worker, args=(job_id,), daemon=True).start()
    return jsonify({"job_id": job_id, "modules": selected_modules})


@app.route("/audit/ack/<job_id>", methods=["POST"])
def audit_ack(job_id):
    """
    Frontend calls this when user clicks OK on the inter-module popup.
    Opens the gate so the sequential worker proceeds to the next module.
    """
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    job["gate_event"].set()   # release the worker
    return jsonify({"ok": True})


@app.route("/audit/status/<job_id>", methods=["GET"])
def audit_status(job_id):
    """Per-module progress + which module is currently active."""
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "job_id":         job_id,
        "status":         job["status"],
        "module_status":  job["module_status"],
        "current_module": job["current_module"],
        "awaiting_ack":   job["awaiting_ack"],
    })


@app.route("/audit/result/<job_id>", methods=["GET"])
def audit_result(job_id):
    """Full results — available incrementally (per module) and after completion."""
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "job_id":         job_id,
        "status":         job["status"],
        "module_status":  job["module_status"],
        "module_results": job["module_results"],
        "modules":        job["modules"],
        "trust_score":    job.get("trust_score"),   # None until job is done
    })


@app.route("/audit/report/<job_id>", methods=["GET"])
def audit_report(job_id):
    """Generate and download the unified HTML report."""
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] != "done":
        return jsonify({"error": "Job not finished yet"}), 202

    report_path = generate_unified_report(
        job_id, job["module_results"], job["modules"],
        trust_score=job.get("trust_score")
    )
    return send_file(
        report_path, as_attachment=True,
        download_name=f"ecopulse_report_{job_id[:8]}.html"
    )


# ── Mitigation endpoints (separate flow, unchanged) ───────────────────────────

from utils.fairness_metrics import (
    compute_fairness_metrics, generate_user_specific_suggestions,
    compute_performance_metrics, analyze_data_quality,
)
from utils.mitigation import (
    mitigate_with_exponentiated_gradient, mitigate_user_model,
    train_baseline_only, build_transformer,
    MitigatedBaselineWrapper, MitigatedUserModelWrapper,
)
from utils.model_loader import load_model
import pandas as pd, joblib

PROGRESS = {}
RESULTS  = {}


@app.route("/mitigate_async", methods=["POST"])
def mitigate_async():
    """Kick off baseline mitigation in background."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        file      = request.files["file"]
        target    = request.form.get("target")
        sensitive = request.form.get("sensitive")
        constraint = request.form.get("constraint", "demographic_parity")
        if not target or not sensitive:
            return jsonify({"error": "target and sensitive are required"}), 400

        df     = pd.read_csv(file)
        job_id = str(uuid.uuid4())
        PROGRESS[job_id] = {"status": "running", "percent": 0, "message": "queued"}

        def worker(df, target, sensitive, constraint, job_id):
            try:
                PROGRESS[job_id].update({"percent": 10, "message": "starting mitigation"})
                res        = mitigate_with_exponentiated_gradient(df, target, sensitive, constraint=constraint)
                mitigator  = res.pop("mitigator")
                transformer = res.pop("transformer")
                label_encoder = res.pop("label_encoder")
                model_id   = str(uuid.uuid4())
                model_path = os.path.join("saved_models_fairness", f"{model_id}.joblib")
                wrapper    = MitigatedBaselineWrapper(
                    mitigator=mitigator, target_col=target, sensitive_col=sensitive,
                    metadata={"transformer": transformer, "label_encoder": label_encoder,
                              "constraint": constraint, "timestamp": datetime.now().isoformat()})
                joblib.dump(wrapper, model_path)
                res["model_id"]            = model_id
                res["model_download_url"]  = f"{BASE_URL}/download_model/{model_id}"
                PROGRESS[job_id].update({"percent": 100, "message": "done", "status": "done"})
                RESULTS[job_id] = res
            except Exception as exc:
                PROGRESS[job_id].update({"status": "failed", "message": str(exc)})
                RESULTS[job_id] = {"error": str(exc)}

        Thread(target=worker, args=(df, target, sensitive, constraint, job_id), daemon=True).start()
        return jsonify({"job_id": job_id})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/mitigate_user_model_async", methods=["POST"])
def mitigate_user_model_async():
    """Kick off user-model mitigation in background."""
    try:
        if "file" not in request.files or "user_model" not in request.files:
            return jsonify({"error": "file and user_model required"}), 400
        df         = pd.read_csv(request.files["file"])
        target     = request.form.get("target")
        sensitive  = request.form.get("sensitive")
        constraint = request.form.get("constraint", "demographic_parity")
        model_file = request.files["user_model"]
        model, _   = load_model(model_file, model_file.filename)
        job_id     = str(uuid.uuid4())
        PROGRESS[job_id] = {"status": "running", "percent": 0, "message": "queued"}

        def worker(df, model, target, sensitive, constraint, job_id):
            try:
                PROGRESS[job_id].update({"percent": 10, "message": "mitigating user model"})
                res              = mitigate_user_model(df, model, target, sensitive, constraint=constraint)
                final_model      = res.pop("final_model", None)
                transformer_u    = res.pop("transformer", None)
                group_thresholds = res.pop("group_thresholds", {})
                model_id         = str(uuid.uuid4())
                model_path       = os.path.join("saved_models_fairness", f"{model_id}.joblib")
                wrapper          = MitigatedUserModelWrapper(
                    final_model=final_model, transformer=transformer_u,
                    group_thresholds=group_thresholds, sensitive_col=sensitive,
                    target_col=target, constraint=constraint,
                    metadata={"timestamp": datetime.now().isoformat()})
                joblib.dump(wrapper, model_path)
                res["model_id"]           = model_id
                res["model_download_url"] = f"{BASE_URL}/download_model/{model_id}"
                PROGRESS[job_id].update({"percent": 100, "message": "done", "status": "done"})
                RESULTS[job_id] = res
            except Exception as exc:
                PROGRESS[job_id].update({"status": "failed", "message": str(exc)})
                RESULTS[job_id] = {"error": str(exc)}

        Thread(target=worker, args=(df, model, target, sensitive, constraint, job_id), daemon=True).start()
        return jsonify({"job_id": job_id})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/progress/<job_id>", methods=["GET"])
def progress(job_id):
    return jsonify(PROGRESS.get(job_id, {"status": "not_found"}))


@app.route("/result/<job_id>", methods=["GET"])
def result(job_id):
    return jsonify(RESULTS.get(job_id, {"error": "not found"}))


@app.route("/download_model/<model_id>", methods=["GET"])
def download_model(model_id):
    path = os.path.join("saved_models_fairness", f"{model_id}.joblib")
    if not os.path.exists(path):
        return jsonify({"error": "Model not found"}), 404
    return send_file(path, as_attachment=True,
                     download_name=f"mitigated_model_{model_id[:8]}.joblib")


@app.route("/mask_csv", methods=["POST"])
def mask_csv():
    """
    POST multipart/form-data
      file         – CSV dataset (required)
      columns      – comma-separated list of column names to mask (required)
      strategy     – "redact" (default) | "hash" | "remove"

    Applies the chosen masking strategy to the specified columns and
    returns the masked CSV as a downloadable file.

    Strategies:
      redact  – replaces every value with [REDACTED]
      hash    – replaces with a sha256 hex digest (preserves linkability, removes PII)
      remove  – drops the columns entirely
    """
    import hashlib

    if "file" not in request.files:
        return jsonify({"error": "No CSV file uploaded"}), 400

    columns_raw = request.form.get("columns", "")
    if not columns_raw.strip():
        return jsonify({"error": "No columns specified for masking"}), 400

    strategy = request.form.get("strategy", "redact").lower()
    if strategy not in ("redact", "hash", "remove"):
        return jsonify({"error": "strategy must be one of: redact, hash, remove"}), 400

    try:
        df = pd.read_csv(request.files["file"])
    except Exception as exc:
        return jsonify({"error": f"Could not parse CSV: {exc}"}), 400

    columns_to_mask = [c.strip() for c in columns_raw.split(",") if c.strip()]
    missing_cols    = [c for c in columns_to_mask if c not in df.columns]

    if missing_cols:
        return jsonify({"error": f"Columns not found in CSV: {missing_cols}"}), 400

    # Apply masking
    df_masked = df.copy()
    if strategy == "redact":
        for col in columns_to_mask:
            df_masked[col] = "[REDACTED]"
    elif strategy == "hash":
        for col in columns_to_mask:
            df_masked[col] = df_masked[col].astype(str).apply(
                lambda v: hashlib.sha256(v.encode()).hexdigest()[:16]
            )
    elif strategy == "remove":
        df_masked.drop(columns=columns_to_mask, inplace=True)

    # Save to temp file and serve
    masked_id   = str(uuid.uuid4())[:8]
    out_path    = os.path.join(UPLOAD_DIR, f"masked_{masked_id}.csv")
    df_masked.to_csv(out_path, index=False)

    return send_file(
        out_path,
        as_attachment=True,
        download_name=f"ecopulse_masked_{masked_id}.csv",
        mimetype="text/csv",
    )


@app.route("/whatif/<job_id>", methods=["POST"])
def whatif(job_id):
    """
    POST JSON { feature_values: { col: value, ... } }
    Returns { prediction: 0|1, probability: float } using the job's saved model
    or a freshly trained baseline on the original CSV.

    The endpoint:
      1. Loads the job's CSV path + target from params.
      2. Builds a feature row from the supplied values (fills missing cols with
         column medians/modes from the training data).
      3. Uses the job's saved fairness model (if present) or trains a quick
         RandomForest baseline to get a prediction.
    """
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    body = request.get_json(silent=True) or {}
    feature_values = body.get("feature_values", {})

    params = job.get("params", {})
    csv_path = params.get("csv_path")
    target   = params.get("target", "")

    if not csv_path or not os.path.exists(csv_path):
        return jsonify({"error": "Original CSV not available"}), 400
    if not target:
        return jsonify({"error": "No target column known for this job"}), 400

    try:
        df = pd.read_csv(csv_path)
        feat_cols = [c for c in df.columns if c != target]

        # Build input row — fill missing values with median/mode
        row = {}
        for col in feat_cols:
            if col in feature_values:
                try:
                    row[col] = float(feature_values[col]) if pd.api.types.is_numeric_dtype(df[col]) else feature_values[col]
                except (ValueError, TypeError):
                    row[col] = feature_values[col]
            else:
                if pd.api.types.is_numeric_dtype(df[col]):
                    row[col] = float(df[col].median())
                else:
                    row[col] = df[col].mode().iloc[0] if not df[col].mode().empty else ""

        X_input = pd.DataFrame([row])[feat_cols]

        # Try to use the fairness module's trained model if available
        model = None
        fairness_result = job.get("module_results", {}).get("fairness", {})

        # Try job's uploaded model
        model_path = params.get("model_path")
        if model_path and os.path.exists(model_path):
            try:
                ext = os.path.splitext(model_path)[1].lower()
                if ext in (".pkl", ".joblib"):
                    model = joblib.load(model_path)
            except Exception:
                model = None

        # Fall back: train a quick baseline
        if model is None:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.preprocessing import OrdinalEncoder
            from sklearn.pipeline import Pipeline
            from sklearn.compose import ColumnTransformer

            X_train = df[feat_cols].copy()
            y_train = df[target]

            cat_cols = X_train.select_dtypes(include=["object", "category"]).columns.tolist()
            num_cols = X_train.select_dtypes(exclude=["object", "category"]).columns.tolist()

            transformers = []
            if cat_cols:
                transformers.append(("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), cat_cols))
            if num_cols:
                transformers.append(("num", "passthrough", num_cols))

            ct = ColumnTransformer(transformers, remainder="drop")
            model = Pipeline([("pre", ct), ("clf", RandomForestClassifier(n_estimators=50, random_state=42))])
            model.fit(X_train, y_train)

        # Align columns if model has feature_names_in_
        if hasattr(model, "feature_names_in_"):
            trained_feats = list(model.feature_names_in_)
            for c in trained_feats:
                if c not in X_input.columns:
                    X_input[c] = 0
            X_input = X_input[trained_feats]

        prediction = int(model.predict(X_input)[0])
        probability = None
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X_input)[0]
            # probability of positive class (last class)
            probability = float(proba[-1])

        return jsonify({
            "prediction": prediction,
            "probability": probability,
            "feature_values": row,
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Real-Time Monitoring endpoints ────────────────────────────────────────────
# POST  /monitor/create           – seed a monitor from an audit job or manual baseline
# POST  /monitor/ingest/<id>      – push a prediction batch
# GET   /monitor/status/<id>      – current state, snapshots, alerts
# GET   /monitor/list             – all monitors (summary)
# POST  /monitor/pause/<id>       – pause monitoring
# POST  /monitor/resume/<id>      – resume monitoring
# DELETE /monitor/delete/<id>     – remove monitor

from monitoring_store import MONITORS, persist as _persist_monitors
from tasks.monitoring import create_monitor, ingest_batch


@app.route("/monitor/create", methods=["POST"])
def monitor_create():
    """
    POST JSON:
    {
      "name":                 "My Loan Model",         // required
      "sensitive_col":        "gender",                // required
      "target_col":           "approved",              // required
      "baseline_group_rates": { "M": 0.72, "F": 0.65 }, // required
      "dp_threshold":         0.1,                     // optional
      "psi_warning":          0.1,                     // optional
      "psi_critical":         0.25,                    // optional
      "audit_job_id":         "<uuid>"                 // optional — auto-extract baseline
    }

    If audit_job_id is provided AND the audit job has fairness results,
    the baseline_group_rates are extracted automatically.
    """
    body = request.get_json(silent=True) or {}

    name          = body.get("name", "Unnamed Monitor")
    sensitive_col = body.get("sensitive_col", "")
    target_col    = body.get("target_col", "")

    if not sensitive_col or not target_col:
        return jsonify({"error": "sensitive_col and target_col are required"}), 400

    # Auto-extract baseline — audit_job_id takes priority over manual JSON
    baseline      = None
    audit_job_id  = (body.get("audit_job_id") or "").strip()
    manual_rates  = body.get("baseline_group_rates")

    if audit_job_id:
        job = JOBS.get(audit_job_id)
        if not job:
            return jsonify({
                "error": (
                    f"Audit job not found in memory. "
                    "Flask restarts clear in-memory jobs — please re-run your audit "
                    "in this session, then paste the new job ID."
                )
            }), 400
        if job.get("status") != "done":
            return jsonify({"error": "Audit job is not finished yet."}), 400
        fairness_res = job.get("module_results", {}).get("fairness", {})
        gm = fairness_res.get("by_group", {})
        if not gm:
            return jsonify({"error": "Audit job has no fairness results. Include Fairness module in the audit."}), 400
        baseline = {}
        for g, v in gm.items():
            rate = v.get("Selection Rate", v.get("selection_rate", 0.5))
            baseline[str(g)] = float(rate)
    elif manual_rates:
        if not isinstance(manual_rates, dict) or len(manual_rates) == 0:
          return jsonify({
    "error": 'baseline_group_rates must be a non-empty JSON object e.g. {"M": 0.72, "F": 0.65}'
}), 400
        baseline = {str(k): float(v) for k, v in manual_rates.items()}
    else:
        return jsonify({"error": "Provide either baseline_group_rates JSON or a completed audit_job_id."}), 400

    monitor_id = create_monitor(
        name=name,
        sensitive_col=sensitive_col,
        target_col=target_col,
        baseline_group_rates=baseline,
        dp_threshold=float(body.get("dp_threshold",  0.10)),
        psi_warning= float(body.get("psi_warning",   0.10)),
        psi_critical=float(body.get("psi_critical",  0.25)),
    )
    return jsonify({"monitor_id": monitor_id, "name": name})


@app.route("/monitor/ingest/<monitor_id>", methods=["POST"])
def monitor_ingest(monitor_id):
    """
    POST JSON:
    {
      "rows": [
        { "sensitive": "M", "prediction": 1 },
        { "sensitive": "F", "prediction": 0 },
        ...
      ]
    }
    Returns the snapshot produced by this batch.
    """
    body = request.get_json(silent=True) or {}
    rows = body.get("rows", [])
    if not rows:
        return jsonify({"error": "rows array is required and must not be empty"}), 400
    try:
        snapshot = ingest_batch(monitor_id, rows)
        return jsonify(snapshot)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/monitor/status/<monitor_id>", methods=["GET"])
def monitor_status(monitor_id):
    """
    Returns full monitor state: metadata, last 50 snapshots, last 50 alerts.
    Query param ?snapshots=N to control how many snapshots to return (max 200).
    """
    mon = MONITORS.get(monitor_id)
    if not mon:
        return jsonify({"error": "Monitor not found"}), 404

    n = min(int(request.args.get("snapshots", 50)), 200)
    return jsonify({
        "id":                   mon["id"],
        "name":                 mon["name"],
        "sensitive_col":        mon["sensitive_col"],
        "target_col":           mon["target_col"],
        "baseline_group_rates": mon["baseline_group_rates"],
        "thresholds":           mon["thresholds"],
        "created_at":           mon["created_at"],
        "status":               mon["status"],
        "total_snapshots":      len(mon["snapshots"]),
        "total_alerts":         len(mon["alerts"]),
        "snapshots":            mon["snapshots"][-n:],
        "alerts":               mon["alerts"][-50:],
    })


@app.route("/monitor/list", methods=["GET"])
def monitor_list():
    """Returns summary of all monitors (no snapshots, just metadata + counts)."""
    summaries = []
    for mon in MONITORS.values():
        last_snap = mon["snapshots"][-1] if mon["snapshots"] else None
        summaries.append({
            "id":              mon["id"],
            "name":            mon["name"],
            "sensitive_col":   mon["sensitive_col"],
            "target_col":      mon["target_col"],
            "status":          mon["status"],
            "created_at":      mon["created_at"],
            "total_snapshots": len(mon["snapshots"]),
            "total_alerts":    len(mon["alerts"]),
            "last_dp_gap":     last_snap["dp_gap"] if last_snap else None,
            "last_snapshot_at": last_snap["timestamp"] if last_snap else None,
        })
    summaries.sort(key=lambda x: x["created_at"], reverse=True)
    return jsonify(summaries)


@app.route("/monitor/pause/<monitor_id>", methods=["POST"])
def monitor_pause(monitor_id):
    mon = MONITORS.get(monitor_id)
    if not mon:
        return jsonify({"error": "Monitor not found"}), 404
    mon["status"] = "paused"
    _persist_monitors()
    return jsonify({"ok": True, "status": "paused"})


@app.route("/monitor/resume/<monitor_id>", methods=["POST"])
def monitor_resume(monitor_id):
    mon = MONITORS.get(monitor_id)
    if not mon:
        return jsonify({"error": "Monitor not found"}), 404
    mon["status"] = "active"
    _persist_monitors()
    return jsonify({"ok": True, "status": "active"})


@app.route("/monitor/delete/<monitor_id>", methods=["DELETE"])
def monitor_delete(monitor_id):
    if monitor_id not in MONITORS:
        return jsonify({"error": "Monitor not found"}), 404
    del MONITORS[monitor_id]
    _persist_monitors()
    return jsonify({"ok": True})


# ── AI Governance Copilot endpoints ───────────────────────────────────────────
# POST /ai/fairness/<job_id>      — AI Fairness Consultant
# POST /ai/explainability/<job_id> — AI Explainability Narrator
# POST /ai/compliance/<job_id>    — AI Compliance Advisor
# GET  /ai/health                 — Ollama availability check

from services.fairness_ai      import analyze_fairness
from services.explainability_ai import analyze_explainability
from services.compliance_ai    import analyze_compliance
from services.ollama_service   import is_available as ollama_is_available
from monitoring_store          import MONITORS


@app.route("/ai/health", methods=["GET"])
def ai_health():
    """Check if Ollama is reachable and llama3 is available."""
    ok = ollama_is_available()
    return jsonify({"ollama_available": ok,
                    "model": "llama3",
                    "status": "ready" if ok else "unavailable"})


@app.route("/ai/fairness/<job_id>", methods=["POST"])
def ai_fairness(job_id):
    """
    AI Fairness Consultant.
    Reads fairness results from JOBS[job_id] automatically — no body required.
    Optionally enriches with monitoring drift history.
    """
    try:
        result = analyze_fairness(job_id, JOBS, MONITORS)
        return jsonify(result)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e), "hint": "Is Ollama running? Run: ollama serve"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ai/explainability/<job_id>", methods=["POST"])
def ai_explainability(job_id):
    """
    AI Explainability Narrator.
    Reads SHAP + LIME results from JOBS[job_id] automatically.
    """
    try:
        result = analyze_explainability(job_id, JOBS)
        return jsonify(result)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e), "hint": "Is Ollama running? Run: ollama serve"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ai/compliance/<job_id>", methods=["POST"])
def ai_compliance(job_id):
    """
    AI Compliance Advisor.
    Reads compliance scan results from JOBS[job_id] automatically.
    """
    try:
        result = analyze_compliance(job_id, JOBS)
        return jsonify(result)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e), "hint": "Is Ollama running? Run: ollama serve"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
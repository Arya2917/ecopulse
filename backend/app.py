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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
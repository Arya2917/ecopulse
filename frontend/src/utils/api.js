// frontend/src/utils/api.js
// ═══════════════════════════════════════════════════════════════════════════════
// EcoPulse API client
// All audit traffic goes through the unified /audit/* endpoints.
// Mitigation uses its own /mitigate_async and /mitigate_user_model_async.
// ═══════════════════════════════════════════════════════════════════════════════

const BASE = "http://127.0.0.1:5000";

// ── Audit API ──────────────────────────────────────────────────────────────────

/**
 * Start a sequential audit job.
 * @param {File}     csvFile
 * @param {string[]} modules   e.g. ["fairness","explainability","compliance","energy"]
 * @param {object}   params    { target, sensitive, pred_col, train_baseline,
 *                               model_file, wrap_model, dp_threshold, eo_threshold,
 *                               fpr_threshold, fnr_threshold, epochs }
 * @returns {Promise<{ job_id: string, modules: string[] }>}
 */
export const startAudit = async (csvFile, modules, params = {}) => {
  const fd = new FormData();
  fd.append("file",           csvFile);
  fd.append("modules",        modules.join(","));
  if (params.target)      fd.append("target",          params.target);
  if (params.sensitive)   fd.append("sensitive",        params.sensitive);
  if (params.pred_col)    fd.append("pred_col",         params.pred_col);
  if (params.model_file)  fd.append("user_model",       params.model_file);
  fd.append("train_baseline", params.train_baseline ? "1" : "0");
  fd.append("wrap_model",     params.wrap_model     ? "1" : "0");
  fd.append("dp_threshold",   params.dp_threshold  ?? 0.1);
  fd.append("eo_threshold",   params.eo_threshold  ?? 0.1);
  fd.append("fpr_threshold",  params.fpr_threshold ?? 0.1);
  fd.append("fnr_threshold",  params.fnr_threshold ?? 0.1);
  fd.append("epochs",         params.epochs        ?? 1);

  const res = await fetch(`${BASE}/audit/start`, { method: "POST", body: fd });
  return res.json();
};

/**
 * Poll status — returns current_module and awaiting_ack flag.
 * @returns {Promise<{
 *   job_id, status, module_status, current_module, awaiting_ack
 * }>}
 */
export const getAuditStatus = async (jobId) => {
  const res = await fetch(`${BASE}/audit/status/${jobId}`);
  return res.json();
};

/**
 * Fetch full results (incremental — available per module as they complete).
 * @returns {Promise<{ job_id, status, module_status, module_results, modules }>}
 */
export const getAuditResult = async (jobId) => {
  const res = await fetch(`${BASE}/audit/result/${jobId}`);
  return res.json();
};

/**
 * Acknowledge a completed module — tells the backend to proceed to the next one.
 * Call this when the user clicks OK on the inter-module popup.
 */
export const ackModule = async (jobId) => {
  const res = await fetch(`${BASE}/audit/ack/${jobId}`, { method: "POST" });
  return res.json();
};

/** Returns the URL to download the full HTML report. */
export const getReportUrl = (jobId) => `${BASE}/audit/report/${jobId}`;

/**
 * Mask PII columns in a CSV and return a Blob for download.
 * @param {File}     csvFile
 * @param {string[]} columns   Column names to mask
 * @param {string}   strategy  "redact" | "hash" | "remove"
 */
export const maskCsv = async (csvFile, columns, strategy = "redact") => {
  const fd = new FormData();
  fd.append("file",     csvFile);
  fd.append("columns",  columns.join(","));
  fd.append("strategy", strategy);
  const res = await fetch(`${BASE}/mask_csv`, { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || "Masking failed");
  }
  return res.blob();
};


// ── Mitigation API ─────────────────────────────────────────────────────────────

/**
 * Start baseline mitigation (no user model).
 */
export const mitigateDatasetAsync = async (file, target, sensitive, constraint = "demographic_parity") => {
  const fd = new FormData();
  fd.append("file",       file);
  fd.append("target",     target);
  fd.append("sensitive",  sensitive);
  fd.append("constraint", constraint);
  const res = await fetch(`${BASE}/mitigate_async`, { method: "POST", body: fd });
  return res.json();
};

/**
 * Start user-model mitigation.
 */
export const mitigateUserModelAsync = async (dataFile, modelFile, target, sensitive, constraint = "demographic_parity") => {
  const fd = new FormData();
  fd.append("file",       dataFile);
  fd.append("user_model", modelFile);
  fd.append("target",     target);
  fd.append("sensitive",  sensitive);
  fd.append("constraint", constraint);
  const res = await fetch(`${BASE}/mitigate_user_model_async`, { method: "POST", body: fd });
  return res.json();
};

/** Poll mitigation job progress. */
export const getProgress = async (jobId) => {
  const res = await fetch(`${BASE}/progress/${jobId}`);
  return res.json();
};

/** Fetch mitigation result. */
export const getResult = async (jobId) => {
  const res = await fetch(`${BASE}/result/${jobId}`);
  return res.json();
};
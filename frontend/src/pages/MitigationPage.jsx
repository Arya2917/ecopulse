// frontend/src/pages/MitigationPage.jsx
// ═══════════════════════════════════════════════════════════════════════════════
// Fairness Mitigation overlay.
//
// Rendered as a full-screen modal on top of AuditPage.
// User uploads CSV + optional model, chooses a constraint, runs mitigation,
// then downloads the mitigated model.
//
// Props:
//   prefillTarget    – string (from audit results, optional)
//   prefillSensitive – string (from audit results, optional)
//   onClose          – () => void
// ═══════════════════════════════════════════════════════════════════════════════

import React, { useState, useRef } from "react";
import { useTheme } from "../theme";
import {
  mitigateDatasetAsync, mitigateUserModelAsync,
  getProgress, getResult,
} from "../utils/api";

const CONSTRAINTS = [
  { value: "demographic_parity",  label: "Demographic Parity"  },
  { value: "equalized_odds",      label: "Equalized Odds"       },
  { value: "true_positive_rate",  label: "True Positive Rate Parity" },
];

// ── Tiny primitives ────────────────────────────────────────────────────────────

function Label({ children, T }) {
  return (
    <div style={{ color: T.textDim, fontSize: 11, fontWeight: 700,
      textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
      {children}
    </div>
  );
}

function FileBtn({ label, file, onFile, accept, T }) {
  const ref = useRef();
  return (
    <div>
      <input ref={ref} type="file" accept={accept} style={{ display: "none" }}
        onChange={e => onFile(e.target.files[0] || null)} />
      <button
        onClick={() => ref.current.click()}
        style={{
          width: "100%", padding: "9px 14px", borderRadius: 7, cursor: "pointer",
          background: file ? T.greenDim : T.surfaceHi,
          border: `1px solid ${file ? T.green : T.border}`,
          color: file ? T.green : T.textDim, fontSize: 13, textAlign: "left",
          fontFamily: "inherit",
        }}
      >
        {file ? `✓ ${file.name}` : label}
      </button>
    </div>
  );
}

function ProgressBar({ percent, color, T }) {
  return (
    <div style={{ height: 6, background: T.border, borderRadius: 3, overflow: "hidden" }}>
      <div style={{
        height: "100%", borderRadius: 3, background: color,
        width: `${percent}%`, transition: "width .5s",
      }} />
    </div>
  );
}

// ── Result display ─────────────────────────────────────────────────────────────

function MitigationResult({ result, T }) {
  if (!result) return null;
  if (result.error) return (
    <div style={{ color: T.red, padding: "10px 14px", background: T.redDim,
      borderRadius: 8, fontSize: 13 }}>Error: {result.error}</div>
  );

  const before = result.before_mitigation || {};
  const after  = result.after_mitigation  || {};
  const metrics = Object.keys({ ...before, ...after });

  return (
    <div style={{ marginTop: 16 }}>
      {/* Before / After table */}
      {metrics.length > 0 && (
        <div style={{ background: T.surfaceHi, border: `1px solid ${T.border}`,
          borderRadius: 8, padding: "14px 16px", marginBottom: 14 }}>
          <div style={{ color: T.textDim, fontSize: 11, fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>
            Before vs After Mitigation
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, fontSize: 12 }}>
            <div style={{ color: T.textDim, fontWeight: 700 }}>Metric</div>
            <div style={{ color: T.red,   fontWeight: 700 }}>Before</div>
            <div style={{ color: T.green, fontWeight: 700 }}>After</div>
            {metrics.map(k => (
              <React.Fragment key={k}>
                <div style={{ color: T.text }}>{k}</div>
                <div style={{ color: T.red,   fontFamily: "monospace" }}>
                  {typeof before[k] === "number" ? before[k].toFixed(4) : before[k] ?? "—"}
                </div>
                <div style={{ color: T.green, fontFamily: "monospace" }}>
                  {typeof after[k]  === "number" ? after[k].toFixed(4)  : after[k]  ?? "—"}
                </div>
              </React.Fragment>
            ))}
          </div>
        </div>
      )}

      {/* Download mitigated model */}
      {result.model_download_url && (
        <a
          href={result.model_download_url}
          download
          style={{
            display: "block", textAlign: "center", padding: "11px 0",
            borderRadius: 8, background: `linear-gradient(135deg, ${T.amber}, #e07b00)`,
            color: "#000", fontWeight: 800, fontSize: 14, textDecoration: "none",
          }}
        >
          ↓ Download Mitigated Model
        </a>
      )}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

const MitigationPage = ({ prefillTarget = "", prefillSensitive = "", onClose }) => {
  const { T } = useTheme();

  const [csvFile,     setCsvFile]     = useState(null);
  const [modelFile,   setModelFile]   = useState(null);
  const [target,      setTarget]      = useState(prefillTarget);
  const [sensitive,   setSensitive]   = useState(prefillSensitive);
  const [constraint,  setConstraint]  = useState("demographic_parity");
  const [phase,       setPhase]       = useState("idle"); // idle | running | done | error
  const [progress,    setProgress]    = useState({ percent: 0, message: "" });
  const [result,      setResult]      = useState(null);
  const [errorMsg,    setErrorMsg]    = useState("");

  const pollRef = useRef(null);

  const validate = () => {
    if (!csvFile)   return "Please upload a CSV dataset.";
    if (!target)    return "Target column is required.";
    if (!sensitive) return "Sensitive attribute column is required.";
    return "";
  };

  const handleRun = async () => {
    const err = validate();
    if (err) { setErrorMsg(err); return; }
    setErrorMsg("");
    setPhase("running");
    setProgress({ percent: 5, message: "Submitting…" });

    try {
      let res;
      if (modelFile) {
        res = await mitigateUserModelAsync(csvFile, modelFile, target, sensitive, constraint);
      } else {
        res = await mitigateDatasetAsync(csvFile, target, sensitive, constraint);
      }

      if (res.error) { setErrorMsg(res.error); setPhase("error"); return; }

      const jobId = res.job_id;
      pollRef.current = setInterval(async () => {
        try {
          const prog = await getProgress(jobId);
          setProgress({ percent: prog.percent || 0, message: prog.message || "" });

          if (prog.status === "done") {
            clearInterval(pollRef.current);
            const out = await getResult(jobId);
            setResult(out);
            setPhase("done");
          } else if (prog.status === "failed") {
            clearInterval(pollRef.current);
            setErrorMsg(prog.message || "Mitigation failed.");
            setPhase("error");
          }
        } catch (e) {
          clearInterval(pollRef.current);
          setErrorMsg(String(e));
          setPhase("error");
        }
      }, 1200);
    } catch (e) {
      setErrorMsg(String(e));
      setPhase("error");
    }
  };

  // ── Styles ─────────────────────────────────────────────────────────────────
  const inputStyle = {
    width: "100%", padding: "9px 10px", boxSizing: "border-box",
    background: T.surfaceHi, border: `1px solid ${T.border}`,
    borderRadius: 7, color: T.text, fontSize: 13, fontFamily: "inherit",
  };

  return (
    /* Full-screen backdrop */
    <div style={{
      position: "fixed", inset: 0, background: "#00000099",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 9000, fontFamily: T.font, overflowY: "auto", padding: 24,
    }}>
      <div style={{
        background: T.bg, border: `1px solid ${T.border}`,
        borderRadius: 16, padding: "30px 32px", width: 560, maxWidth: "96vw",
        boxShadow: "0 24px 80px #00000077",
        animation: "mit-pop .22s cubic-bezier(.16,1,.3,1)",
      }}>
        <style>{`
          @keyframes mit-pop {
            from { opacity: 0; transform: scale(.95) translateY(12px); }
            to   { opacity: 1; transform: scale(1) translateY(0); }
          }
        `}</style>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 22 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              width: 38, height: 38, borderRadius: 9, fontSize: 18,
              background: T.amberDim, border: `1px solid ${T.amber}44`,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>⚖</div>
            <div>
              <div style={{ color: "#fff", fontWeight: 800, fontSize: 17 }}>Fairness Mitigation</div>
              <div style={{ color: T.textDim, fontSize: 12 }}>Reduce bias using Exponentiated Gradient</div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: T.surfaceHi, border: `1px solid ${T.border}`,
              borderRadius: 6, color: T.textDim, width: 30, height: 30,
              cursor: "pointer", fontSize: 16, display: "flex",
              alignItems: "center", justifyContent: "center",
            }}
          >✕</button>
        </div>

        {/* Form */}
        {phase !== "done" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

            {/* CSV upload */}
            <div>
              <Label T={T}>CSV Dataset *</Label>
              <FileBtn label="Upload CSV dataset" file={csvFile} onFile={setCsvFile} accept=".csv" T={T} />
            </div>

            {/* Model upload (optional) */}
            <div>
              <Label T={T}>Model File (optional)</Label>
              <FileBtn label="Upload .pkl model (optional)" file={modelFile}
                onFile={setModelFile} accept=".pkl,.joblib" T={T} />
            </div>

            {/* Target + Sensitive */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <Label T={T}>Target Column *</Label>
                <input
                  style={inputStyle} value={target}
                  onChange={e => setTarget(e.target.value)}
                  placeholder="e.g. income"
                />
              </div>
              <div>
                <Label T={T}>Sensitive Attribute *</Label>
                <input
                  style={inputStyle} value={sensitive}
                  onChange={e => setSensitive(e.target.value)}
                  placeholder="e.g. gender"
                />
              </div>
            </div>

            {/* Constraint */}
            <div>
              <Label T={T}>Fairness Constraint</Label>
              <select
                value={constraint}
                onChange={e => setConstraint(e.target.value)}
                style={{ ...inputStyle, cursor: "pointer" }}
              >
                {CONSTRAINTS.map(c => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>

            {/* Error */}
            {errorMsg && (
              <div style={{ color: T.red, fontSize: 13, padding: "8px 12px",
                background: T.redDim, borderRadius: 7 }}>
                ⚠ {errorMsg}
              </div>
            )}

            {/* Progress */}
            {phase === "running" && (
              <div>
                <ProgressBar percent={progress.percent} color={T.amber} T={T} />
                <div style={{ color: T.textDim, fontSize: 11, marginTop: 6 }}>
                  {progress.message}  {progress.percent}%
                </div>
              </div>
            )}

            {/* Run button */}
            <button
              onClick={handleRun}
              disabled={phase === "running"}
              style={{
                padding: "12px 0", borderRadius: 9, border: "none",
                background: phase === "running"
                  ? T.surfaceHi
                  : `linear-gradient(135deg, ${T.amber}, #e07b00)`,
                color: phase === "running" ? T.textDim : "#000",
                fontSize: 14, fontWeight: 800, cursor: phase === "running" ? "not-allowed" : "pointer",
                fontFamily: T.font,
              }}
            >
              {phase === "running" ? "Mitigating…" : "▶  Run Mitigation"}
            </button>
          </div>
        )}

        {/* Results */}
        {phase === "done" && (
          <div>
            <div style={{ color: T.green, fontWeight: 700, fontSize: 15, marginBottom: 14 }}>
              ✓ Mitigation complete
            </div>
            <MitigationResult result={result} T={T} />
            <button
              onClick={onClose}
              style={{
                marginTop: 18, width: "100%", padding: "11px 0", borderRadius: 9, border: "none",
                background: T.surfaceHi, border: `1px solid ${T.border}`,
                color: T.textDim, fontSize: 13, cursor: "pointer", fontFamily: T.font,
              }}
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default MitigationPage;
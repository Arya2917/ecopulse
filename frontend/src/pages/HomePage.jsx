// frontend/src/pages/HomePage.jsx
// ═══════════════════════════════════════════════════════════════════════════════
// Unified launch dashboard.
//
// NEW in this version:
//   • CSV Preview Panel — after upload, shows row count, column stats,
//     missing values, data types, and a 5-row sample table.
//   • Audit History — completed audits saved to localStorage, shown in a
//     collapsible "Past Audits" section on the home page with trust score
//     and module badges. Clicking a past audit re-populates the form.
// ═══════════════════════════════════════════════════════════════════════════════

import React, { useState, useRef, useEffect } from "react";
import { useTheme } from "../theme";

// ── LocalStorage helpers ───────────────────────────────────────────────────────

const HISTORY_KEY = "ecopulse_audit_history";

export function saveAuditToHistory(entry) {
  // entry: { id, timestamp, modules, trustScore, riskLevel, riskColor, csvName, moduleStatuses }
  try {
    const existing = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    const updated  = [entry, ...existing].slice(0, 20); // keep last 20
    localStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
  } catch { /* localStorage might be unavailable */ }
}

export function loadAuditHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch { return []; }
}

export function clearAuditHistory() {
  try { localStorage.removeItem(HISTORY_KEY); } catch { }
}

// ── CSV parser helpers ─────────────────────────────────────────────────────────

function readCSVHeaders(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const first = e.target.result.split(/\r?\n/)[0];
      resolve(first.split(",").map(h => h.trim().replace(/^["']|["']$/g, "")));
    };
    reader.onerror = reject;
    reader.readAsText(file);
  });
}

function parseCSVPreview(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const lines = e.target.result.split(/\r?\n/).filter(l => l.trim());
      if (lines.length < 2) { resolve(null); return; }

      const headers = lines[0].split(",").map(h => h.trim().replace(/^["']|["']$/g, ""));
      const rows    = lines.slice(1, 6).map(line => {  // first 5 data rows
        const vals = line.split(",").map(v => v.trim().replace(/^["']|["']$/g, ""));
        const obj  = {};
        headers.forEach((h, i) => { obj[h] = vals[i] ?? ""; });
        return obj;
      });

      // Stats per column from all rows (up to 500 for speed)
      const allRows = lines.slice(1, 501).map(line =>
        line.split(",").map(v => v.trim().replace(/^["']|["']$/g, ""))
      );

      const colStats = headers.map((h, ci) => {
        const vals    = allRows.map(r => r[ci] ?? "").filter(v => v !== "");
        const missing = allRows.length - vals.length;
        const nums    = vals.map(Number).filter(v => !isNaN(v));
        const isNum   = nums.length > vals.length * 0.8;
        let   dtype   = isNum ? "numeric" : "categorical";
        let   info    = "";
        if (isNum && nums.length > 0) {
          const mn  = Math.min(...nums);
          const mx  = Math.max(...nums);
          const avg = nums.reduce((a, b) => a + b, 0) / nums.length;
          info = `min ${mn.toFixed(2)}, max ${mx.toFixed(2)}, mean ${avg.toFixed(2)}`;
        } else {
          const uniq = new Set(vals).size;
          info = `${uniq} unique value${uniq !== 1 ? "s" : ""}`;
        }
        return { name: h, dtype, missing, info };
      });

      resolve({
        numRows:   lines.length - 1,
        numCols:   headers.length,
        headers,
        sampleRows: rows,
        colStats,
      });
    };
    reader.onerror = reject;
    reader.readAsText(file);
  });
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function ModuleCard({ module, selected, onToggle, T }) {
  return (
    <div
      onClick={() => onToggle(module.id)}
      style={{
        background:   selected ? module.dim : T.surface,
        border:       `1.5px solid ${selected ? module.color : T.border}`,
        borderRadius: 12, padding: "16px 18px",
        cursor: "pointer", transition: "all .18s", position: "relative", userSelect: "none",
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.borderColor = module.color + "88"; }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.borderColor = T.border; }}
    >
      <div style={{
        position: "absolute", top: 14, left: 14,
        width: 16, height: 16, borderRadius: 4,
        background: selected ? module.color : "transparent",
        border: `2px solid ${selected ? module.color : T.textDim}`,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        {selected && <span style={{ color: "#000", fontSize: 10, fontWeight: 900 }}>✓</span>}
      </div>
      <div style={{ marginLeft: 26 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 6 }}>
          <span style={{ fontSize: 18 }}>{module.icon}</span>
          <span style={{ color: "#fff", fontWeight: 700, fontSize: 14 }}>{module.label}</span>
        </div>
        <p style={{ color: T.textDim, fontSize: 12, margin: "0 0 8px", lineHeight: 1.5 }}>
          {module.desc}
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
          {module.tags.map(t => (
            <span key={t} style={{
              fontSize: 10, padding: "2px 7px", borderRadius: 8,
              background: module.dim, color: module.color,
              border: `1px solid ${module.color}33`, fontWeight: 600,
            }}>{t}</span>
          ))}
        </div>
        <div style={{ marginTop: 8 }}>
          {module.requires.map(r => (
            <span key={r} style={{ fontSize: 10, color: T.textDim, marginRight: 10 }}>
              · {r}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function DropZone({ label, accept, file, onFile, hint, T }) {
  const ref = useRef();
  const [drag, setDrag] = useState(false);
  const handle = (f) => { if (f) onFile(f); };
  return (
    <div
      onClick={() => ref.current.click()}
      onDragOver={e => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={e => { e.preventDefault(); setDrag(false); handle(e.dataTransfer.files[0]); }}
      style={{
        border: `2px dashed ${drag ? T.amber : file ? T.green : T.border}`,
        borderRadius: 10, padding: "20px 16px", textAlign: "center",
        cursor: "pointer", transition: "all .18s",
        background: drag ? T.amberDim : file ? T.greenDim : T.surface,
      }}
    >
      <input ref={ref} type="file" accept={accept} style={{ display: "none" }}
        onChange={e => handle(e.target.files[0])} />
      <div style={{ fontSize: 22, marginBottom: 6 }}>{file ? "✅" : "📂"}</div>
      <div style={{ color: file ? T.green : T.text, fontSize: 13, fontWeight: 600 }}>
        {file ? file.name : label}
      </div>
      {!file && hint && (
        <div style={{ color: T.textDim, fontSize: 11, marginTop: 4 }}>{hint}</div>
      )}
      {file && (
        <button
          onClick={e => { e.stopPropagation(); onFile(null); }}
          style={{
            marginTop: 8, padding: "3px 10px", borderRadius: 5, fontSize: 11,
            background: T.surfaceHi, border: `1px solid ${T.border}`,
            color: T.textDim, cursor: "pointer",
          }}
        >Remove</button>
      )}
    </div>
  );
}

function ColSelect({ label, value, onChange, columns, placeholder, T }) {
  return (
    <div>
      <div style={{ color: T.textDim, fontSize: 11, fontWeight: 700,
        textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
        {label}
      </div>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          width: "100%", padding: "9px 10px",
          background: T.surfaceHi, border: `1px solid ${T.border}`,
          borderRadius: 7, color: value ? T.text : T.textDim,
          fontSize: 13, fontFamily: "inherit", cursor: "pointer",
        }}
      >
        <option value="">{placeholder}</option>
        {columns.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
    </div>
  );
}

// ── CSV Preview Panel ──────────────────────────────────────────────────────────

function CSVPreviewPanel({ preview, T }) {
  const [showSample, setShowSample] = useState(false);
  if (!preview) return null;

  const totalMissing = preview.colStats.reduce((s, c) => s + c.missing, 0);

  return (
    <div style={{
      background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 12, padding: "18px 20px", marginTop: 14,
    }}>
      {/* Top stats row */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
        {[
          { label: "Rows",    value: preview.numRows.toLocaleString(), color: T.sky   },
          { label: "Columns", value: preview.numCols,                  color: T.violet },
          { label: "Missing", value: totalMissing > 0 ? totalMissing : "None",
            color: totalMissing > 0 ? T.amber : T.green },
          { label: "Numeric cols",
            value: preview.colStats.filter(c => c.dtype === "numeric").length,
            color: T.sky },
          { label: "Categorical cols",
            value: preview.colStats.filter(c => c.dtype === "categorical").length,
            color: T.violet },
        ].map(s => (
          <div key={s.label} style={{
            background: T.surfaceHi, border: `1px solid ${T.border}`,
            borderRadius: 8, padding: "8px 14px", flex: 1, minWidth: 90,
          }}>
            <div style={{ color: T.textDim, fontSize: 10, fontWeight: 700,
              textTransform: "uppercase", letterSpacing: "0.05em" }}>{s.label}</div>
            <div style={{ color: s.color, fontSize: 18, fontWeight: 900, marginTop: 2 }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Column stats */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ color: T.textDim, fontSize: 10, fontWeight: 700,
          textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
          Column Overview
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          {preview.colStats.map(col => (
            <div key={col.name} style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "6px 10px", borderRadius: 6, background: T.surfaceHi,
            }}>
              <span style={{
                fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                background: col.dtype === "numeric" ? T.skyDim : T.violetDim,
                color: col.dtype === "numeric" ? T.sky : T.violet,
                flexShrink: 0, width: 68, textAlign: "center",
              }}>
                {col.dtype}
              </span>
              <span style={{ color: "#fff", fontSize: 12, fontWeight: 600, minWidth: 100, flexShrink: 0 }}>
                {col.name}
              </span>
              <span style={{ color: T.textDim, fontSize: 11, flex: 1 }}>{col.info}</span>
              {col.missing > 0 && (
                <span style={{ fontSize: 10, color: T.amber, fontWeight: 700, flexShrink: 0 }}>
                  {col.missing} missing
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Sample rows toggle */}
      <button
        onClick={() => setShowSample(v => !v)}
        style={{
          background: "none", border: `1px solid ${T.border}`, borderRadius: 6,
          color: T.textDim, fontSize: 11, padding: "5px 12px", cursor: "pointer",
          fontFamily: "inherit",
        }}
      >
        {showSample ? "▲ Hide" : "▼ Show"} sample rows (first 5)
      </button>

      {showSample && (
        <div style={{ marginTop: 12, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
            <thead>
              <tr>
                {preview.headers.map(h => (
                  <th key={h} style={{
                    padding: "6px 10px", borderBottom: `1px solid ${T.border}`,
                    color: T.textDim, fontWeight: 700, textAlign: "left",
                    textTransform: "uppercase", letterSpacing: "0.04em", whiteSpace: "nowrap",
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.sampleRows.map((row, i) => (
                <tr key={i} style={{ background: i % 2 === 0 ? T.surfaceHi : "transparent" }}>
                  {preview.headers.map(h => (
                    <td key={h} style={{
                      padding: "5px 10px", color: T.text, fontSize: 11,
                      fontFamily: "monospace", whiteSpace: "nowrap",
                      borderBottom: `1px solid ${T.border}`,
                    }}>
                      {row[h] ?? ""}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Audit History Panel ────────────────────────────────────────────────────────

const MODULE_COLORS = {
  fairness:       "#f59e0b",
  explainability: "#a78bfa",
  compliance:     "#22c55e",
  energy:         "#38bdf8",
};

const MODULE_ICONS = {
  fairness: "⚖", explainability: "🔍", compliance: "🛡", energy: "⚡",
};

function AuditHistoryPanel({ T, onRerun }) {
  const [history,    setHistory]    = useState([]);
  const [collapsed,  setCollapsed]  = useState(false);

  useEffect(() => {
    setHistory(loadAuditHistory());
    // Refresh when localStorage changes from another tab / audit completion
    const handler = () => setHistory(loadAuditHistory());
    window.addEventListener("ecopulse_history_updated", handler);
    return () => window.removeEventListener("ecopulse_history_updated", handler);
  }, []);

  if (history.length === 0) return null;

  const riskColor = (rc) =>
    ({ green: T.green, amber: T.amber, red: T.red }[rc] || T.textDim);

  const handleClear = () => {
    clearAuditHistory();
    setHistory([]);
  };

  return (
    <div style={{
      background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 12, padding: "18px 20px", marginBottom: 20,
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: collapsed ? 0 : 14 }}>
        <button
          onClick={() => setCollapsed(v => !v)}
          style={{
            background: "none", border: "none", cursor: "pointer", padding: 0,
            color: T.textDim, fontSize: 11, fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.06em",
            display: "flex", alignItems: "center", gap: 8, fontFamily: T.font,
          }}
        >
          <span style={{
            transform: collapsed ? "none" : "rotate(90deg)",
            transition: "transform .2s", display: "inline-block",
          }}>▶</span>
          Past Audits ({history.length})
        </button>
        {!collapsed && (
          <button
            onClick={handleClear}
            style={{
              background: "none", border: `1px solid ${T.border}`,
              borderRadius: 5, color: T.textDim, fontSize: 11,
              padding: "3px 10px", cursor: "pointer", fontFamily: T.font,
            }}
          >Clear all</button>
        )}
      </div>

      {!collapsed && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {history.map((entry) => {
            const rc = riskColor(entry.riskColor);
            return (
              <div key={entry.id} style={{
                background: T.surfaceHi, border: `1px solid ${T.border}`,
                borderRadius: 9, padding: "12px 14px",
                display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap",
              }}>
                {/* Trust score ring (tiny) */}
                {entry.trustScore != null && (
                  <div style={{
                    width: 44, height: 44, borderRadius: "50%", flexShrink: 0,
                    background: rc + "22", border: `2px solid ${rc}`,
                    display: "flex", flexDirection: "column",
                    alignItems: "center", justifyContent: "center",
                  }}>
                    <span style={{ color: rc, fontSize: 12, fontWeight: 900, lineHeight: 1 }}>
                      {entry.trustScore.toFixed(0)}
                    </span>
                    <span style={{ color: T.textDim, fontSize: 8 }}>/ 100</span>
                  </div>
                )}

                {/* Info */}
                <div style={{ flex: 1, minWidth: 160 }}>
                  <div style={{ color: "#fff", fontSize: 12, fontWeight: 700 }}>
                    {entry.csvName || "audit"}
                  </div>
                  <div style={{ color: T.textDim, fontSize: 10, marginTop: 2 }}>
                    {new Date(entry.timestamp).toLocaleString()}
                  </div>
                  {/* Module badges */}
                  <div style={{ display: "flex", gap: 5, marginTop: 6, flexWrap: "wrap" }}>
                    {(entry.modules || []).map(m => (
                      <span key={m} style={{
                        fontSize: 9, padding: "2px 7px", borderRadius: 6, fontWeight: 700,
                        background: (MODULE_COLORS[m] || "#6b7280") + "22",
                        color: MODULE_COLORS[m] || "#6b7280",
                        border: `1px solid ${(MODULE_COLORS[m] || "#6b7280")}44`,
                      }}>
                        {MODULE_ICONS[m]} {m}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Risk badge */}
                {entry.riskLevel && (
                  <span style={{
                    fontSize: 10, fontWeight: 800, padding: "3px 10px",
                    borderRadius: 12, background: rc + "22",
                    color: rc, border: `1px solid ${rc}44`, flexShrink: 0,
                  }}>
                    {entry.riskLevel}
                  </span>
                )}

                {/* Re-run button */}
                {onRerun && (
                  <button
                    onClick={() => onRerun(entry)}
                    style={{
                      padding: "6px 12px", borderRadius: 7, border: `1px solid ${T.border}`,
                      background: T.surface, color: T.textDim, fontSize: 11,
                      cursor: "pointer", fontFamily: T.font, flexShrink: 0,
                    }}
                  >
                    ↺ Re-run
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

const HomePage = ({ onStartAudit }) => {
  const { T } = useTheme();

  const MODULES = [
    {
      id: "fairness", label: "Fairness", icon: "⚖", color: T.amber, dim: T.amberDim,
      desc: "Audit demographic parity, equalized odds, and group-level fairness metrics using Fairlearn.",
      tags: ["Fairlearn", "Demographic Parity", "Equalized Odds"],
      requires: ["CSV dataset", "Target column", "Sensitive attribute"],
    },
    {
      id: "explainability", label: "Explainability", icon: "🔍", color: T.violet, dim: T.violetDim,
      desc: "Generate SHAP values and LIME explanations to understand which features drive model predictions.",
      tags: ["SHAP", "LIME", "Feature Importance"],
      requires: ["CSV dataset", "Target column", "Model file (optional)"],
    },
    {
      id: "compliance", label: "Compliance", icon: "🛡", color: T.green, dim: T.greenDim,
      desc: "Scan your dataset for PII/PHI using Microsoft Presidio across GDPR, HIPAA, CCPA, and more.",
      tags: ["Presidio", "PII Detection", "GDPR"],
      requires: ["CSV dataset"],
    },
    {
      id: "energy", label: "Energy Efficiency", icon: "⚡", color: T.sky, dim: T.skyDim,
      desc: "Measure CO₂ emissions and energy consumption during model training/inference using CodeCarbon.",
      tags: ["CodeCarbon", "CO₂", "Sustainability"],
      requires: ["CSV dataset or .pkl model", "Epochs (optional)"],
    },
  ];

  const [selected,    setSelected]    = useState(["fairness", "explainability", "compliance", "energy"]);
  const [csvFile,     setCsvFile]     = useState(null);
  const [modelFile,   setModelFile]   = useState(null);
  const [csvHeaders,  setCsvHeaders]  = useState([]);
  const [csvPreview,  setCsvPreview]  = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [target,      setTarget]      = useState("");
  const [sensitive,   setSensitive]   = useState("");
  const [epochs,      setEpochs]      = useState(1);
  const [showAdv,     setShowAdv]     = useState(false);
  const [dpThr,       setDpThr]       = useState(0.1);
  const [eoThr,       setEoThr]       = useState(0.1);
  const [fprThr,      setFprThr]      = useState(0.1);
  const [fnrThr,      setFnrThr]      = useState(0.1);
  const [trainBase,   setTrainBase]   = useState(true);
  const [error,       setError]       = useState("");

  const needsTarget    = selected.includes("fairness") || selected.includes("explainability");
  const needsSensitive = selected.includes("fairness");
  const needsEpochs    = selected.includes("energy");

  const toggleModule = (id) =>
    setSelected(prev => prev.includes(id) ? prev.filter(m => m !== id) : [...prev, id]);

  const handleCsvFile = async (file) => {
    setCsvFile(file);
    setCsvPreview(null);
    setTarget("");
    setSensitive("");
    if (file) {
      try {
        const headers = await readCSVHeaders(file);
        setCsvHeaders(headers);
      } catch {
        setCsvHeaders([]);
      }
      // Parse preview stats
      setPreviewLoading(true);
      try {
        const preview = await parseCSVPreview(file);
        setCsvPreview(preview);
      } catch {
        setCsvPreview(null);
      } finally {
        setPreviewLoading(false);
      }
    } else {
      setCsvHeaders([]);
    }
  };

  // Handle re-run from history (just pre-select modules; can't restore file)
  const handleRerun = (entry) => {
    if (entry.modules) setSelected(entry.modules);
  };

  const validate = () => {
    if (!csvFile)               return "Please upload a CSV dataset.";
    if (selected.length === 0)  return "Select at least one audit module.";
    if (needsTarget && !target) return "Please select a Target column (required for Fairness / Explainability).";
    if (needsSensitive && !sensitive) return "Please select a Sensitive attribute column (required for Fairness).";
    return "";
  };

  const handleRun = () => {
    const err = validate();
    if (err) { setError(err); return; }
    setError("");
    onStartAudit({
      csvFile,
      modules:        selected,
      target,
      sensitive,
      model_file:     modelFile,
      train_baseline: trainBase,
      epochs,
      dp_threshold:   dpThr,
      eo_threshold:   eoThr,
      fpr_threshold:  fprThr,
      fnr_threshold:  fnrThr,
    });
  };

  const sectionHead = {
    color: T.textDim, fontSize: 11, fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "0.08em",
    marginBottom: 12,
  };

  const card = {
    background: T.surface, border: `1px solid ${T.border}`,
    borderRadius: 12, padding: "22px 24px", marginBottom: 20,
  };

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: "36px 24px", fontFamily: T.font }}>

      {/* Hero */}
      <div style={{ textAlign: "center", marginBottom: 36 }}>
        <div style={{ fontSize: 36, marginBottom: 10 }}>⚖</div>
        <h1 style={{ color: "#fff", fontSize: 28, fontWeight: 900, margin: "0 0 8px",
          letterSpacing: "-0.02em" }}>
          EcoPulse <span style={{ color: T.amber }}>AI Audit Suite</span>
        </h1>
        <p style={{ color: T.textDim, fontSize: 14, maxWidth: 500, margin: "0 auto" }}>
          Upload your dataset, configure your audit, and let EcoPulse run
          a full sequential analysis — fairness, explainability, compliance, and energy.
        </p>
      </div>

      {/* ── Past Audits ────────────────────────────────────────────────────── */}
      <AuditHistoryPanel T={T} onRerun={handleRerun} />

      {/* ── Step 1: Select Modules ─────────────────────────────────────────── */}
      <div style={card}>
        <div style={sectionHead}>Step 1 — Select Audit Modules</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {MODULES.map(m => (
            <ModuleCard
              key={m.id} module={m}
              selected={selected.includes(m.id)}
              onToggle={toggleModule}
              T={T}
            />
          ))}
        </div>
        {selected.length === 0 && (
          <div style={{ color: T.amber, fontSize: 12, marginTop: 10 }}>
            ⚠ Select at least one module.
          </div>
        )}
      </div>

      {/* ── Step 2: Upload Files ───────────────────────────────────────────── */}
      <div style={card}>
        <div style={sectionHead}>Step 2 — Upload Files</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <div style={{ color: T.text, fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
              CSV Dataset <span style={{ color: T.red }}>*</span>
            </div>
            <DropZone
              label="Drop CSV or click to browse"
              accept=".csv"
              file={csvFile}
              onFile={handleCsvFile}
              hint="Required for all modules"
              T={T}
            />
            {previewLoading && (
              <div style={{ color: T.textDim, fontSize: 11, marginTop: 8 }}>
                ⏳ Parsing dataset…
              </div>
            )}
          </div>
          <div>
            <div style={{ color: T.text, fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
              Model File <span style={{ color: T.textDim }}>(optional)</span>
            </div>
            <DropZone
              label="Drop .pkl model or click to browse"
              accept=".pkl,.joblib"
              file={modelFile}
              onFile={setModelFile}
              hint="Fairness · Explainability · Energy"
              T={T}
            />
          </div>
        </div>

        {/* CSV Preview Panel */}
        <CSVPreviewPanel preview={csvPreview} T={T} />
      </div>

      {/* ── Step 3: Column Configuration ──────────────────────────────────── */}
      {(needsTarget || needsSensitive || needsEpochs) && (
        <div style={card}>
          <div style={sectionHead}>Step 3 — Column Configuration</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px,1fr))", gap: 16 }}>
            {needsTarget && (
              <ColSelect
                label="Target Column *"
                value={target}
                onChange={setTarget}
                columns={csvHeaders}
                placeholder={csvFile ? "— select target —" : "Upload CSV first"}
                T={T}
              />
            )}
            {needsSensitive && (
              <ColSelect
                label="Sensitive Attribute *"
                value={sensitive}
                onChange={setSensitive}
                columns={csvHeaders}
                placeholder={csvFile ? "— select attribute —" : "Upload CSV first"}
                T={T}
              />
            )}
            {needsEpochs && (
              <div>
                <div style={{ color: T.textDim, fontSize: 11, fontWeight: 700,
                  textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
                  Energy Epochs
                </div>
                <input
                  type="number" min={1} max={20} value={epochs}
                  onChange={e => setEpochs(Math.max(1, parseInt(e.target.value) || 1))}
                  style={{
                    width: "100%", padding: "9px 10px", boxSizing: "border-box",
                    background: T.surfaceHi, border: `1px solid ${T.border}`,
                    borderRadius: 7, color: T.text, fontSize: 13, fontFamily: "inherit",
                  }}
                />
              </div>
            )}
          </div>

          {!modelFile && needsTarget && (
            <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 10 }}>
              <input
                id="trainBase"
                type="checkbox"
                checked={trainBase}
                onChange={e => setTrainBase(e.target.checked)}
                style={{ accentColor: T.amber, width: 15, height: 15, cursor: "pointer" }}
              />
              <label htmlFor="trainBase" style={{ color: T.textDim, fontSize: 12, cursor: "pointer" }}>
                Train a Random Forest baseline automatically (no model file provided)
              </label>
            </div>
          )}
        </div>
      )}

      {/* ── Advanced Options ───────────────────────────────────────────────── */}
      <div style={card}>
        <button
          onClick={() => setShowAdv(v => !v)}
          style={{
            background: "none", border: "none", cursor: "pointer",
            color: T.textDim, fontSize: 12, fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.06em",
            display: "flex", alignItems: "center", gap: 8, padding: 0,
            fontFamily: T.font,
          }}
        >
          <span style={{ transform: showAdv ? "rotate(90deg)" : "none", transition: "transform .2s", display: "inline-block" }}>▶</span>
          Advanced Thresholds
        </button>

        {showAdv && (
          <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            {[
              ["DP Threshold",  dpThr,  setDpThr ],
              ["EO Threshold",  eoThr,  setEoThr ],
              ["FPR Threshold", fprThr, setFprThr],
              ["FNR Threshold", fnrThr, setFnrThr],
            ].map(([label, val, set]) => (
              <div key={label}>
                <div style={{ color: T.textDim, fontSize: 11, fontWeight: 600, marginBottom: 5 }}>{label}</div>
                <input
                  type="number" min={0} max={1} step={0.01} value={val}
                  onChange={e => set(parseFloat(e.target.value) || 0)}
                  style={{
                    width: "100%", padding: "7px 8px", boxSizing: "border-box",
                    background: T.surfaceHi, border: `1px solid ${T.border}`,
                    borderRadius: 6, color: T.text, fontSize: 13, fontFamily: "inherit",
                  }}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Error + Run Button ─────────────────────────────────────────────── */}
      {error && (
        <div style={{
          background: T.redDim, border: `1px solid ${T.red}44`,
          borderRadius: 8, padding: "12px 16px",
          color: T.red, fontSize: 13, marginBottom: 16,
        }}>
          ⚠ {error}
        </div>
      )}

      <button
        onClick={handleRun}
        disabled={selected.length === 0 || !csvFile}
        style={{
          width: "100%", padding: "14px 0", borderRadius: 10, border: "none",
          background: selected.length > 0 && csvFile
            ? `linear-gradient(135deg, ${T.amber}, #e07b00)`
            : T.surfaceHi,
          color: selected.length > 0 && csvFile ? "#000" : T.textDim,
          fontSize: 15, fontWeight: 900, cursor: selected.length > 0 && csvFile ? "pointer" : "not-allowed",
          fontFamily: T.font, letterSpacing: "0.01em", transition: "all .2s",
        }}
      >
        {selected.length === 0
          ? "Select at least one module"
          : !csvFile
          ? "Upload a CSV to continue"
          : `▶  Run Audit  (${selected.length} module${selected.length > 1 ? "s" : ""})`}
      </button>

      <p style={{ color: T.textDim, fontSize: 11, textAlign: "center", marginTop: 12 }}>
        Modules run sequentially: {["fairness","explainability","compliance","energy"]
          .filter(m => selected.includes(m)).join(" → ")}
      </p>
    </div>
  );
};

export default HomePage;

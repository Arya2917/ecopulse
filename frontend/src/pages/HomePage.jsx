// frontend/src/pages/HomePage.jsx
// ═══════════════════════════════════════════════════════════════════════════════
// Unified launch dashboard.
//
// Layout:
//   1. Module selector cards (fairness / explainability / compliance / energy)
//   2. File upload zone  (CSV required, model .pkl optional)
//   3. Column config     (target + sensitive — appear when fairness or explainability selected)
//   4. Advanced options  (thresholds — collapsible)
//   5. "Run Audit" button
// ═══════════════════════════════════════════════════════════════════════════════

import React, { useState, useRef } from "react";
import { useTheme } from "../theme";

// ── Helpers ────────────────────────────────────────────────────────────────────

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
      {/* Checkbox */}
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
    setTarget("");
    setSensitive("");
    if (file) {
      try {
        const headers = await readCSVHeaders(file);
        setCsvHeaders(headers);
      } catch {
        setCsvHeaders([]);
      }
    } else {
      setCsvHeaders([]);
    }
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

  // ── Styles ────────────────────────────────────────────────────────────────
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

          {/* Prediction source option (when no model) */}
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

      {/* ── Advanced Options (collapsible) ────────────────────────────────── */}
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
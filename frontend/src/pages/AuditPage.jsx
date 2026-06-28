// frontend/src/pages/AuditPage.jsx
// ═══════════════════════════════════════════════════════════════════════════════
// Sequential audit runner — updated with Trust Score + PII Masking panels.
// ═══════════════════════════════════════════════════════════════════════════════

import React, { useEffect, useRef, useState, useCallback } from "react";
import { useTheme } from "../theme";
import { startAudit, getAuditStatus, getAuditResult, ackModule, getReportUrl, maskCsv } from "../utils/api";
import AIInsightCard from "../components/AIInsightCard";
import { saveAuditToHistory } from "./HomePage";

const MODULE_META = {
  fairness:       { label: "Fairness",        icon: "⚖",  colorKey: "amber"  },
  explainability: { label: "Explainability",   icon: "🔍", colorKey: "violet" },
  compliance:     { label: "Compliance",       icon: "🛡",  colorKey: "green"  },
  energy:         { label: "Energy",           icon: "⚡", colorKey: "sky"    },
};
const MODULE_ORDER = ["fairness", "explainability", "compliance", "energy"];

// ── Primitives ─────────────────────────────────────────────────────────────────

function Spinner({ color, size = 16 }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%",
      border: `2px solid ${color}44`, borderTop: `2px solid ${color}`,
      animation: "ep-spin .7s linear infinite", flexShrink: 0,
    }} />
  );
}

function KV({ label, value, color, T }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0",
      borderBottom: `1px solid ${T.border}` }}>
      <span style={{ color: T.text, fontSize: 13 }}>{label}</span>
      <span style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700,
        color: color || T.sky }}>{value}</span>
    </div>
  );
}

// ── Module summaries (popup) ───────────────────────────────────────────────────

function FairnessSummary({ data, T }) {
  const overall = data?.overall || {};
  const perf    = data?.performance || {};
  return (
    <div>
      <div style={{ color: T.textDim, fontSize: 11, fontWeight: 700,
        textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Fairness Metrics</div>
      {Object.entries(overall).slice(0, 4).map(([k, v]) => (
        <KV key={k} label={k.replace(" Difference", " Δ")}
          value={typeof v === "number" ? v.toFixed(4) : String(v)}
          color={Math.abs(v) < 0.1 ? T.green : Math.abs(v) < 0.2 ? T.amber : T.red} T={T} />
      ))}
      {perf.accuracy != null && <KV label="Accuracy" value={perf.accuracy.toFixed(4)} color={T.sky} T={T} />}
    </div>
  );
}

function ExplainSummary({ data, T }) {
  const shap = data?.shap || {};
  const agg  = data?.aggregated || {};
  return (
    <div>
      <div style={{ color: T.textDim, fontSize: 11, fontWeight: 700,
        textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Top SHAP Features</div>
      {Object.entries(shap.feature_importance || {}).slice(0, 4).map(([feat, val]) => (
        <KV key={feat} label={feat} value={val.toFixed(4)} color={T.violet} T={T} />
      ))}
      {agg.agreement_score != null && (
        <KV label="SHAP–LIME Agreement" value={`${(agg.agreement_score * 100).toFixed(0)}%`} color={T.violet} T={T} />
      )}
    </div>
  );
}

function ComplianceSummary({ data, T }) {
  const findings = data?.findings || [];
  const high = findings.filter(f => f.severity === "HIGH").length;
  return (
    <div>
      <div style={{ color: T.textDim, fontSize: 11, fontWeight: 700,
        textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Compliance Scan</div>
      <KV label="Total Findings" value={findings.length} color={T.green} T={T} />
      <KV label="High Severity"  value={high} color={high > 0 ? T.red : T.green} T={T} />
    </div>
  );
}

function EnergySummary({ data, T }) {
  return (
    <div>
      <div style={{ color: T.textDim, fontSize: 11, fontWeight: 700,
        textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Energy Metrics</div>
      <KV label="Total Energy" value={data?.energy_kwh != null ? `${(data.energy_kwh * 1000).toFixed(4)} Wh` : "—"} color={T.sky} T={T} />
      <KV label="Carbon Emitted" value={data?.carbon_kg != null ? `${(data.carbon_kg * 1000).toFixed(4)} g CO₂` : "—"} color={T.green} T={T} />
      <KV label="Epochs" value={data?.epochs ?? "—"} color={T.amber} T={T} />
    </div>
  );
}

function ModuleSummary({ moduleId, data, T }) {
  if (!data) return <div style={{ color: T.textDim, fontSize: 13 }}>No data available.</div>;
  if (data.error) return <div style={{ color: T.red, fontSize: 13, padding: "8px 10px", background: T.redDim, borderRadius: 6 }}>Error: {data.error}</div>;
  switch (moduleId) {
    case "fairness":       return <FairnessSummary  data={data} T={T} />;
    case "explainability": return <ExplainSummary   data={data} T={T} />;
    case "compliance":     return <ComplianceSummary data={data} T={T} />;
    case "energy":         return <EnergySummary    data={data} T={T} />;
    default: return <div style={{ color: T.textDim, fontSize: 13 }}>Results ready.</div>;
  }
}

// ── Trust Score Ring ───────────────────────────────────────────────────────────

function TrustScoreRing({ score, color, size = 96 }) {
  const r    = (size - 10) / 2;
  const circ = 2 * Math.PI * r;
  const fill = score != null ? circ * (score / 100) : 0;
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color + "22"} strokeWidth={8} />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={8}
        strokeDasharray={`${fill} ${circ}`} strokeLinecap="round"
        style={{ transition: "stroke-dasharray 1s ease" }} />
    </svg>
  );
}

// ── Trust Score Panel ──────────────────────────────────────────────────────────

function TrustScorePanel({ trustScore, T }) {
  if (!trustScore || trustScore.score == null) return null;
  const { score, risk_level, risk_color, breakdown, summary, weights_used } = trustScore;
  const colorMap = { green: T.green, amber: T.amber, red: T.red, textDim: T.textDim };
  const color    = colorMap[risk_color] || T.textDim;
  const bgMap    = { green: T.greenDim, amber: T.amberDim, red: T.redDim, textDim: T.surfaceHi };
  const badgeBg  = bgMap[risk_color] || T.surfaceHi;

  return (
    <div style={{
      background: T.surface, border: `1.5px solid ${color}44`,
      borderRadius: 14, padding: "22px 24px", marginBottom: 16,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
        <div>
          <div style={{ color: "#fff", fontWeight: 800, fontSize: 15 }}>🛡 AI Trust Score</div>
          <div style={{ color: T.textDim, fontSize: 12, marginTop: 2 }}>
            Weighted composite across all audited dimensions
          </div>
        </div>
        <span style={{
          background: badgeBg, color, border: `1px solid ${color}55`,
          borderRadius: 20, padding: "4px 14px", fontSize: 12, fontWeight: 800,
        }}>
          {risk_level}
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 24, marginBottom: 18, flexWrap: "wrap" }}>
        <div style={{ position: "relative", width: 96, height: 96, flexShrink: 0 }}>
          <TrustScoreRing score={score} color={color} size={96} />
          <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontSize: 22, fontWeight: 900, color, lineHeight: 1 }}>{score.toFixed(1)}</span>
            <span style={{ fontSize: 10, color: T.textDim }}>/ 100</span>
          </div>
        </div>
        <div style={{ flex: 1, minWidth: 180 }}>
          <div style={{ height: 8, background: T.surfaceHi, borderRadius: 4, overflow: "hidden", marginBottom: 10 }}>
            <div style={{
              height: "100%", width: `${Math.min(score, 100)}%`,
              background: `linear-gradient(90deg, ${color}99, ${color})`,
              borderRadius: 4, transition: "width 1s ease",
            }} />
          </div>
          <p style={{ color: T.text, fontSize: 13, lineHeight: 1.5 }}>{summary}</p>
        </div>
      </div>

      {Object.keys(breakdown || {}).length > 0 && (
        <div>
          <div style={{ color: T.textDim, fontSize: 11, fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
            Score Breakdown
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {Object.entries(breakdown).map(([mod, val]) => {
              const bc = val >= 75 ? T.green : val >= 50 ? T.amber : T.red;
              const wt = weights_used?.[mod];
              return (
                <div key={mod} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ width: 96, fontSize: 12, color: T.text, textTransform: "capitalize", flexShrink: 0 }}>
                    {mod}
                    {wt != null && <span style={{ color: T.textDim, fontSize: 10, marginLeft: 4 }}>({(wt*100).toFixed(0)}%)</span>}
                  </div>
                  <div style={{ flex: 1, height: 6, background: T.surfaceHi, borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${val}%`, background: bc, borderRadius: 3, transition: "width 1s ease" }} />
                  </div>
                  <div style={{ width: 48, textAlign: "right", fontSize: 12, fontWeight: 700, color: bc, flexShrink: 0 }}>
                    {val.toFixed(1)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── PII Masking Panel ──────────────────────────────────────────────────────────

function DataMaskingPanel({ complianceData, csvFile, T }) {
  const [selectedCols, setSelectedCols] = useState([]);
  const [strategy, setStrategy]         = useState("redact");
  const [masking, setMasking]           = useState(false);
  const [maskError, setMaskError]       = useState("");
  const [masked, setMasked]             = useState(false);

  const colReport = complianceData?.column_report || {};
  const piiCols   = Object.entries(colReport)
    .filter(([, info]) => info?.pii_detected || (info?.entities && info.entities.length > 0))
    .map(([col]) => col);

  if (piiCols.length === 0) return null;

  const toggle = (col) =>
    setSelectedCols(prev => prev.includes(col) ? prev.filter(c => c !== col) : [...prev, col]);

  const handleMask = async () => {
    if (!csvFile) { setMaskError("Original CSV not available. Re-upload the file."); return; }
    if (selectedCols.length === 0) { setMaskError("Select at least one column to mask."); return; }
    setMaskError(""); setMasking(true);
    try {
      const blob = await maskCsv(csvFile, selectedCols, strategy);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = "ecopulse_masked_dataset.csv"; a.click();
      URL.revokeObjectURL(url);
      setMasked(true);
    } catch (e) {
      setMaskError(String(e));
    } finally {
      setMasking(false);
    }
  };

  const sevColor = (sev) => {
    const s = (sev || "").toLowerCase();
    return s === "critical" ? T.red : s === "high" ? "#f97316" : s === "medium" ? T.amber : T.textDim;
  };

  return (
    <div style={{
      background: T.surface, border: `1.5px solid ${T.green}44`,
      borderRadius: 14, padding: "22px 24px", marginBottom: 16,
    }}>
      <div style={{ marginBottom: 14 }}>
        <div style={{ color: "#fff", fontWeight: 800, fontSize: 15 }}>🔒 PII Data Masking</div>
        <div style={{ color: T.textDim, fontSize: 12, marginTop: 2 }}>
          {piiCols.length} PII column{piiCols.length !== 1 ? "s" : ""} detected — select columns, choose a strategy, and download a clean CSV
        </div>
      </div>

      {/* Column list */}
      <div style={{ display: "flex", flexDirection: "column", gap: 7, marginBottom: 16 }}>
        {piiCols.map(col => {
          const info    = colReport[col] || {};
          const sev     = info.severity || info.max_severity || "";
          const ents    = (info.entities || []).map(e => e.entity_type || e).join(", ");
          const checked = selectedCols.includes(col);
          return (
            <div key={col} onClick={() => toggle(col)} style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "9px 12px", borderRadius: 8, cursor: "pointer",
              background: checked ? T.greenDim : T.surfaceHi,
              border: `1px solid ${checked ? T.green + "66" : T.border}`,
              transition: "all .15s",
            }}>
              <div style={{
                width: 16, height: 16, borderRadius: 4, flexShrink: 0,
                background: checked ? T.green : "transparent",
                border: `2px solid ${checked ? T.green : T.textDim}`,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                {checked && <span style={{ color: "#000", fontSize: 10, fontWeight: 900 }}>✓</span>}
              </div>
              <div style={{ flex: 1 }}>
                <span style={{ color: "#fff", fontSize: 13, fontWeight: 600 }}>{col}</span>
                {ents && <span style={{ color: T.textDim, fontSize: 11, marginLeft: 8 }}>{ents}</span>}
              </div>
              {sev && (
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 6,
                  background: sevColor(sev) + "22", color: sevColor(sev),
                  border: `1px solid ${sevColor(sev)}44`,
                }}>
                  {sev.toUpperCase()}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Strategy */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ color: T.textDim, fontSize: 11, fontWeight: 700,
          textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
          Masking Strategy
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {[
            { id: "redact", label: "Redact",  desc: "Replace with [REDACTED]" },
            { id: "hash",   label: "Hash",    desc: "SHA-256 (linkable)" },
            { id: "remove", label: "Remove",  desc: "Drop columns entirely" },
          ].map(opt => (
            <div key={opt.id} onClick={() => setStrategy(opt.id)} style={{
              padding: "8px 14px", borderRadius: 8, cursor: "pointer", flex: 1, minWidth: 100,
              background: strategy === opt.id ? T.greenDim : T.surfaceHi,
              border: `1px solid ${strategy === opt.id ? T.green + "66" : T.border}`,
              transition: "all .15s",
            }}>
              <div style={{ color: strategy === opt.id ? T.green : "#fff", fontWeight: 700, fontSize: 13 }}>{opt.label}</div>
              <div style={{ color: T.textDim, fontSize: 11 }}>{opt.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {maskError && (
        <div style={{ background: T.redDim, border: `1px solid ${T.red}44`, borderRadius: 7,
          padding: "9px 12px", color: T.red, fontSize: 12, marginBottom: 12 }}>
          {maskError}
        </div>
      )}
      {masked && (
        <div style={{ background: T.greenDim, border: `1px solid ${T.green}44`, borderRadius: 7,
          padding: "9px 12px", color: T.green, fontSize: 12, marginBottom: 12 }}>
          ✓ Masked CSV downloaded successfully.
        </div>
      )}

      <button onClick={handleMask} disabled={masking || selectedCols.length === 0} style={{
        width: "100%", padding: "11px 0", borderRadius: 8, border: "none",
        background: selectedCols.length === 0 ? T.surfaceHi : `linear-gradient(135deg, ${T.green}, #15803d)`,
        color: selectedCols.length === 0 ? T.textDim : "#fff",
        fontSize: 14, fontWeight: 800,
        cursor: selectedCols.length === 0 ? "not-allowed" : "pointer",
        fontFamily: "inherit", opacity: masking ? 0.7 : 1,
      }}>
        {masking ? "⏳ Masking…"
          : selectedCols.length === 0 ? "Select columns to mask"
          : `↓ Download Masked CSV (${selectedCols.length} col${selectedCols.length !== 1 ? "s" : ""})`}
      </button>
    </div>
  );
}

// ── Inter-module popup ─────────────────────────────────────────────────────────

function ResultPopup({ moduleId, data, nextModuleId, isLast, onContinue, jobId, T, accentColor }) {
  const meta     = MODULE_META[moduleId] || { label: moduleId, icon: "●" };
  const nextMeta = nextModuleId ? MODULE_META[nextModuleId] : null;
  return (
    <div style={{
      position: "fixed", inset: 0, background: "#00000088",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 9999, fontFamily: "inherit",
    }}>
      <div style={{
        background: T.surface, border: `1px solid ${T.border}`,
        borderRadius: 16, padding: "28px 30px", width: 460, maxWidth: "92vw",
        boxShadow: "0 24px 80px #00000066",
        animation: "ep-pop .22s cubic-bezier(.16,1,.3,1)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 10, fontSize: 20,
            background: accentColor + "22", border: `1px solid ${accentColor}44`,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            {meta.icon}
          </div>
          <div>
            <div style={{ color: "#fff", fontWeight: 800, fontSize: 16 }}>{meta.label} Audit Complete</div>
            <div style={{ color: T.green, fontSize: 12, fontWeight: 600 }}>✓ Analysis finished successfully</div>
          </div>
        </div>
        <div style={{
          background: T.surfaceHi, border: `1px solid ${T.border}`,
          borderRadius: 10, padding: "14px 16px", marginBottom: 20,
        }}>
          <ModuleSummary moduleId={moduleId} data={data} T={T} />
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          {!isLast && nextMeta && (
            <button onClick={onContinue} style={{
              flex: 1, padding: "11px 0", borderRadius: 8, border: "none",
              background: `linear-gradient(135deg, ${accentColor}, ${accentColor}cc)`,
              color: "#000", fontSize: 14, fontWeight: 800, cursor: "pointer", fontFamily: "inherit",
            }}>
              {nextMeta.icon} Continue to {nextMeta.label} →
            </button>
          )}
          {isLast && (
            <a href={getReportUrl(jobId)} target="_blank" rel="noreferrer" onClick={onContinue}
              style={{
                flex: 1, padding: "11px 0", borderRadius: 8, textDecoration: "none", textAlign: "center",
                background: `linear-gradient(135deg, ${T.amber}, #e07b00)`,
                color: "#000", fontSize: 14, fontWeight: 800, display: "block",
              }}>
              ↓ Download Full Report
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

// ── All-done panel ─────────────────────────────────────────────────────────────

function AllDonePanel({ jobId, modules, results, trustScore, csvFile, onOpenMitigation, onBack, T }) {
  const hasFairness   = modules.includes("fairness")   && results?.fairness   && !results.fairness.error;
  const hasCompliance = modules.includes("compliance") && results?.compliance && !results.compliance.error;

  return (
    <div>
      {/* Completion banner */}
      <div style={{
        background: T.greenDim, border: `1px solid ${T.green}44`,
        borderRadius: 12, padding: "20px 24px", textAlign: "center", marginBottom: 16,
      }}>
        <div style={{ fontSize: 36, marginBottom: 8 }}>🎉</div>
        <h2 style={{ color: T.green, fontWeight: 800, margin: "0 0 6px", fontSize: 19 }}>
          Full Audit Complete
        </h2>
        <p style={{ color: T.textDim, fontSize: 13, margin: "0 0 18px" }}>
          All {modules.length} module{modules.length > 1 ? "s" : ""} ran successfully.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 9, alignItems: "center" }}>
          <a href={getReportUrl(jobId)} target="_blank" rel="noreferrer" style={{
            padding: "12px 32px", borderRadius: 9,
            background: `linear-gradient(135deg, ${T.amber}, #e07b00)`,
            color: "#000", fontSize: 14, fontWeight: 800,
            textDecoration: "none", display: "inline-block",
          }}>
            ↓ Download Full HTML Report
          </a>
          {hasFairness && (
            <button onClick={() => onOpenMitigation({ csvFile: null, target: results.fairness?.target || "", sensitive: results.fairness?.sensitive || "" })}
              style={{
                padding: "11px 28px", borderRadius: 9,
                background: T.amberDim, border: `1px solid ${T.amber}55`,
                color: T.amber, fontSize: 13, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
              }}>
              ⚖ Run Fairness Mitigation
            </button>
          )}
          <button onClick={onBack} style={{
            padding: "9px 22px", borderRadius: 9,
            background: T.surfaceHi, border: `1px solid ${T.border}`,
            color: T.textDim, fontSize: 13, cursor: "pointer", fontFamily: "inherit",
          }}>
            ← Start New Audit
          </button>
        </div>
      </div>

      {/* Trust Score */}
      <TrustScorePanel trustScore={trustScore} T={T} />

      {/* PII Masking */}
      {hasCompliance && (
        <DataMaskingPanel complianceData={results.compliance} csvFile={csvFile} T={T} />
      )}

      {/* AI Governance Copilot */}
      {(hasFairness || hasCompliance || modules.includes("explainability")) && (
        <div style={{
          background: T.surface, border: `1px solid ${T.border}`,
          borderRadius: 14, padding: "22px 24px", marginTop: 8,
        }}>
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <div style={{
                width: 32, height: 32, borderRadius: 8, fontSize: 16,
                background: "linear-gradient(135deg, #38bdf8, #a78bfa)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>🤖</div>
              <div>
                <div style={{ color: "#fff", fontWeight: 800, fontSize: 15 }}>AI Governance Copilot</div>
                <div style={{ color: T.textDim, fontSize: 12 }}>
                  Ask llama3 to explain your audit results in plain language
                </div>
              </div>
            </div>
          </div>

          {hasFairness && (
            <AIInsightCard jobId={jobId} type="fairness" T={T} />
          )}
          {modules.includes("explainability") && results?.explainability && !results.explainability.error && (
            <AIInsightCard jobId={jobId} type="explainability" T={T} />
          )}
          {hasCompliance && (
            <AIInsightCard jobId={jobId} type="compliance" T={T} />
          )}
        </div>
      )}
    </div>
  );
}

// ── Timeline (Animated Pipeline) ───────────────────────────────────────────────

function Timeline({ modules, moduleStatus, currentModule, results, T }) {
  const getColor = (id) =>
    ({ fairness: T.amber, explainability: T.violet, compliance: T.green, energy: T.sky }[id] || T.textDim);

  return (
    <div>
      {/* Horizontal animated pipeline strip */}
      <div style={{
        display: "flex", alignItems: "center",
        marginBottom: 22, overflowX: "auto", paddingBottom: 4,
      }}>
        {modules.map((m, i) => {
          const meta   = MODULE_META[m] || { label: m, icon: "●" };
          const status = moduleStatus[m] || "queued";
          const color  = getColor(m);
          const isLast = i === modules.length - 1;
          return (
            <React.Fragment key={m}>
              <div style={{
                flex: "0 0 auto", minWidth: 88,
                display: "flex", flexDirection: "column", alignItems: "center", gap: 7,
                padding: "10px 6px", borderRadius: 10, transition: "all .3s",
                background: status === "running" ? color + "15"
                  : status === "done" ? color + "0d" : "transparent",
                border: `1.5px solid ${status === "running" ? color + "88"
                  : status === "done" ? color + "55" : T.border}`,
                boxShadow: status === "running" ? `0 0 18px ${color}33` : "none",
                transform: status === "running" ? "translateY(-2px)" : "none",
              }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 9, flexShrink: 0,
                  background: status === "done" ? color + "28" : status === "running" ? color + "22"
                    : status === "error" ? T.red + "22" : T.surfaceHi,
                  border: `2px solid ${status === "done" ? color : status === "running" ? color
                    : status === "error" ? T.red : T.border}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 15, transition: "all .3s",
                }}>
                  {status === "done" ? "✓" : status === "error" ? "✕"
                    : status === "running" ? <Spinner color={color} size={14} /> : meta.icon}
                </div>
                <span style={{ color: status === "queued" ? T.textDim : "#fff",
                  fontSize: 11, fontWeight: 700, textAlign: "center" }}>{meta.label}</span>
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: "1px 6px", borderRadius: 5,
                  background: status === "done" ? color + "22" : status === "running" ? color + "22"
                    : status === "error" ? T.red + "22" : T.surfaceHi,
                  color: status === "done" ? color : status === "running" ? color
                    : status === "error" ? T.red : T.textDim,
                }}>
                  {status === "queued" ? "Queued" : status === "running" ? "Running…"
                    : status === "done" ? "Done" : "Error"}
                </span>
              </div>
              {!isLast && (
                <div style={{
                  flex: "0 0 28px", height: 2, position: "relative", overflow: "hidden",
                  background: moduleStatus[m] === "done"
                    ? `linear-gradient(90deg, ${color}, ${getColor(modules[i + 1])})`
                    : T.border,
                  transition: "background .5s",
                }}>
                  {moduleStatus[m] === "running" && (
                    <div style={{
                      position: "absolute", top: -3, width: 8, height: 8,
                      borderRadius: "50%", background: color,
                      animation: "ep-dot 1.4s ease-in-out infinite",
                      boxShadow: `0 0 8px ${color}`,
                    }} />
                  )}
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Vertical detail list */}
      <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
        {modules.map((m, i) => {
          const meta   = MODULE_META[m] || { label: m, icon: "●" };
          const status = moduleStatus[m] || "queued";
          const color  = getColor(m);
          const isLast = i === modules.length - 1;
          return (
            <div key={m} style={{ display: "flex", gap: 14, paddingBottom: isLast ? 0 : 4 }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 28 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                  background: status === "done" ? color+"33" : status === "running" ? color+"22"
                    : status === "error" ? T.red+"22" : T.surfaceHi,
                  border: `2px solid ${status === "done" ? color : status === "running" ? color
                    : status === "error" ? T.red : T.border}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 13, transition: "all .3s",
                }}>
                  {status === "done" ? "✓" : status === "error" ? "✕"
                    : status === "running" ? <Spinner color={color} size={12} /> : meta.icon}
                </div>
                {!isLast && <div style={{ flex: 1, width: 2, minHeight: 28,
                  background: status === "done" ? color+"55" : T.border, transition: "background .5s" }} />}
              </div>
              <div style={{ flex: 1, paddingBottom: isLast ? 0 : 18, paddingTop: 4 }}>
                <div style={{ color: status === "queued" ? T.textDim : "#fff", fontWeight: 700, fontSize: 14 }}>
                  {meta.label}
                </div>
                {status === "running" && (
                  <div style={{ height: 3, background: T.border, borderRadius: 3, overflow: "hidden", marginTop: 8 }}>
                    <div style={{ height: "100%", borderRadius: 3, background: color, animation: "ep-bar 1.4s ease-in-out infinite" }} />
                  </div>
                )}
                {status === "done" && results?.[m] && !results[m].error && (
                  <div style={{ color: color, fontSize: 11, marginTop: 4 }}>Results captured ✓</div>
                )}
                {status === "error" && (
                  <div style={{ color: T.red, fontSize: 11, marginTop: 4 }}>
                    {results?.[m]?.error?.slice(0, 60) || "Module failed"}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main AuditPage ─────────────────────────────────────────────────────────────

const AuditPage = ({ auditParams, onBack, onOpenMitigation }) => {
  const { T } = useTheme();
  const getAccent = (id) => ({ fairness: T.amber, explainability: T.violet, compliance: T.green, energy: T.sky }[id] || T.textDim);

  const [phase,        setPhase]        = useState("starting");
  const [jobId,        setJobId]        = useState(null);
  const [moduleStatus, setModuleStatus] = useState({});
  const [results,      setResults]      = useState({});
  const [trustScore,   setTrustScore]   = useState(null);
  const [currentMod,   setCurrentMod]   = useState(null);
  const [justDoneMod,  setJustDoneMod]  = useState(null);
  const [errorMsg,     setErrorMsg]     = useState("");
  const pollRef = useRef(null);

  const modules = (auditParams?.modules || [])
    .filter(m => MODULE_ORDER.includes(m))
    .sort((a, b) => MODULE_ORDER.indexOf(a) - MODULE_ORDER.indexOf(b));

  const nextModuleAfter = (id) => {
    const idx = modules.indexOf(id);
    return idx >= 0 && idx < modules.length - 1 ? modules[idx + 1] : null;
  };

  useEffect(() => {
    if (!auditParams) return;
    (async () => {
      try {
        const res = await startAudit(auditParams.csvFile, auditParams.modules, auditParams);
        if (res.error) { setErrorMsg(res.error); setPhase("error"); return; }
        setJobId(res.job_id);
        const init = {};
        res.modules.forEach(m => { init[m] = "queued"; });
        setModuleStatus(init);
        setPhase("module_running");
      } catch (e) { setErrorMsg(String(e)); setPhase("error"); }
    })();
  }, [auditParams]);

  useEffect(() => {
    if (!jobId || phase === "all_done" || phase === "error" || phase === "module_done") return;
    pollRef.current = setInterval(async () => {
      try {
        const st = await getAuditStatus(jobId);
        setModuleStatus(st.module_status || {});
        setCurrentMod(st.current_module);
        const res = await getAuditResult(jobId);
        setResults(res.module_results || {});
        if (res.trust_score) setTrustScore(res.trust_score);

        if (st.awaiting_ack) {
          clearInterval(pollRef.current);
          const justDone = modules.find(m =>
            st.module_status[m] === "done" &&
            modules.indexOf(m) < modules.indexOf(st.current_module || modules[modules.length - 1])
          ) || modules.find(m => st.module_status[m] === "done");
          setJustDoneMod(justDone || st.current_module);
          setPhase("module_done");
        } else if (st.status === "done") {
          clearInterval(pollRef.current);
          const lastDone = [...modules].reverse().find(m => st.module_status[m] === "done");
          setJustDoneMod(lastDone);
          setPhase("module_done");
        }
      } catch (e) { clearInterval(pollRef.current); setErrorMsg(String(e)); setPhase("error"); }
    }, 1000);
    return () => clearInterval(pollRef.current);
  }, [jobId, phase]);

  const handleContinue = useCallback(async () => {
    const isLast = !nextModuleAfter(justDoneMod);
    if (isLast) {
      let ts = null;
      try {
        const res = await getAuditResult(jobId);
        if (res.trust_score) {
          setTrustScore(res.trust_score);
          ts = res.trust_score;
        }
      } catch { /* non-fatal */ }
      // Save to audit history
      try {
        saveAuditToHistory({
          id:          jobId,
          timestamp:   new Date().toISOString(),
          modules,
          csvName:     auditParams?.csvFile?.name || "dataset.csv",
          trustScore:  ts?.score ?? null,
          riskLevel:   ts?.risk_level ?? null,
          riskColor:   ts?.risk_color ?? null,
        });
        window.dispatchEvent(new Event("ecopulse_history_updated"));
      } catch { /* non-fatal */ }
      setPhase("all_done");
      return;
    }
    try { await ackModule(jobId); } catch { /* non-fatal */ }
    setJustDoneMod(null);
    setPhase("module_running");
  }, [jobId, justDoneMod, modules, auditParams]);

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "32px 24px", fontFamily: T.font }}>
      <style>{`
        @keyframes ep-spin { to { transform: rotate(360deg); } }
        @keyframes ep-bar  { 0% { width:0%; margin-left:0%; } 50% { width:60%; margin-left:20%; } 100% { width:0%; margin-left:100%; } }
        @keyframes ep-pop  { from { opacity:0; transform:scale(.94) translateY(10px); } to { opacity:1; transform:scale(1) translateY(0); } }
        @keyframes ep-dot  { 0%,100% { left:-8px; opacity:0; } 10% { opacity:1; } 90% { opacity:1; } 95% { left:100%; opacity:0; } }
      `}</style>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 30 }}>
        <button onClick={onBack} style={{
          background: T.surfaceHi, border: `1px solid ${T.border}`,
          borderRadius: 6, color: T.textDim, padding: "6px 12px",
          cursor: "pointer", fontFamily: T.font, fontSize: 13,
        }}>← Back</button>
        <div>
          <h2 style={{ color: "#fff", fontSize: 20, fontWeight: 800, margin: 0 }}>
            {phase === "all_done" ? "Audit Complete" : "Audit in Progress"}
          </h2>
          {jobId && <div style={{ color: T.textDim, fontSize: 11, marginTop: 2 }}>Job: {jobId}</div>}
        </div>
      </div>

      {phase === "error" && (
        <div style={{ background: T.redDim, border: `1px solid ${T.red}44`, borderRadius: 10, padding: 16, color: T.red, marginBottom: 20 }}>
          <strong>Error:</strong> {errorMsg}
        </div>
      )}

      <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 14, padding: "26px 28px", marginBottom: 20 }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 10, marginBottom: 26,
          padding: "12px 16px", borderRadius: 8,
          background: phase === "all_done" ? T.greenDim : T.amberDim,
          border: `1px solid ${phase === "all_done" ? T.green : T.amber}44`,
        }}>
          {phase !== "all_done" && phase !== "error" && <Spinner color={T.amber} />}
          <span style={{ fontWeight: 700, fontSize: 14, color: phase === "all_done" ? T.green : T.amber }}>
            {phase === "starting"       ? "Starting audit…"
             : phase === "module_running" ? `Running ${MODULE_META[currentMod]?.label || ""}…`
             : phase === "module_done"    ? `${MODULE_META[justDoneMod]?.label || ""} complete — review results`
             : phase === "all_done"       ? `✓ All ${modules.length} modules complete`
             : "Error"}
          </span>
          <span style={{ color: T.textDim, fontSize: 12, marginLeft: "auto" }}>
            {Object.values(moduleStatus).filter(s => s === "done" || s === "error").length} / {modules.length} done
          </span>
        </div>
        <Timeline modules={modules} moduleStatus={moduleStatus} currentModule={currentMod} results={results} T={T} />
      </div>

      {phase === "all_done" && (
        <AllDonePanel
          jobId={jobId} modules={modules} results={results}
          trustScore={trustScore} csvFile={auditParams?.csvFile}
          onOpenMitigation={onOpenMitigation} onBack={onBack} T={T}
        />
      )}

      {phase === "module_done" && justDoneMod && (
        <ResultPopup
          moduleId={justDoneMod} data={results[justDoneMod]}
          nextModuleId={nextModuleAfter(justDoneMod)}
          isLast={!nextModuleAfter(justDoneMod)}
          onContinue={handleContinue} jobId={jobId}
          T={T} accentColor={getAccent(justDoneMod)}
        />
      )}
    </div>
  );
};

export default AuditPage;
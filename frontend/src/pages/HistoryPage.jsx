// frontend/src/pages/HistoryPage.jsx
// ═══════════════════════════════════════════════════════════════════════════════
// Audit History Page — shows all past audits from localStorage.
// Features:
//   • Trust score SVG rings per audit
//   • Module badges (coloured per module type)
//   • Side-by-side comparison of any two audits
//   • Clear-all + per-entry delete
// ═══════════════════════════════════════════════════════════════════════════════

import React, { useEffect, useState } from "react";
import { useTheme } from "../theme";
import { loadAuditHistory, clearAuditHistory } from "./HomePage";

// ── Constants ──────────────────────────────────────────────────────────────────

const MODULE_META = {
  fairness:       { label: "Fairness",       icon: "⚖",  colorKey: "amber"  },
  explainability: { label: "Explainability", icon: "🔍", colorKey: "violet" },
  compliance:     { label: "Compliance",     icon: "🛡",  colorKey: "green"  },
  energy:         { label: "Energy",         icon: "⚡", colorKey: "sky"    },
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function moduleColor(mod, T) {
  const key = MODULE_META[mod]?.colorKey;
  return key ? T[key] : T.textDim;
}

function riskColorFromEntry(entry, T) {
  const map = { green: T.green, amber: T.amber, red: T.red };
  return map[entry.riskColor] || T.textDim;
}

function fmtDate(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ── Trust Score Ring ───────────────────────────────────────────────────────────

function TrustRing({ score, riskColor, size = 72 }) {
  const r   = (size - 10) / 2;
  const circ = 2 * Math.PI * r;
  const pct  = Math.max(0, Math.min(100, score ?? 0));
  const dash = (pct / 100) * circ;

  return (
    <svg width={size} height={size} style={{ flexShrink: 0 }}>
      <circle cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke={riskColor + "22"} strokeWidth={8} />
      <circle cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke={riskColor} strokeWidth={8}
        strokeDasharray={`${dash} ${circ - dash}`}
        strokeDashoffset={circ / 4}
        strokeLinecap="round"
        style={{ transition: "stroke-dasharray .6s ease" }}
      />
      <text x={size / 2} y={size / 2 - 4}
        textAnchor="middle" dominantBaseline="middle"
        fill={riskColor} fontSize={size < 56 ? 11 : 14} fontWeight={900}
        fontFamily="'Geist', system-ui, sans-serif">
        {score != null ? score.toFixed(0) : "—"}
      </text>
      <text x={size / 2} y={size / 2 + 10}
        textAnchor="middle" dominantBaseline="middle"
        fill={riskColor + "99"} fontSize={8}
        fontFamily="'Geist', system-ui, sans-serif">
        / 100
      </text>
    </svg>
  );
}

// ── Module Badges ──────────────────────────────────────────────────────────────

function ModuleBadge({ mod, T }) {
  const meta  = MODULE_META[mod] || { label: mod, icon: "●" };
  const color = moduleColor(mod, T);
  return (
    <span style={{
      fontSize: 10, padding: "3px 8px", borderRadius: 6, fontWeight: 700,
      background: color + "22", color, border: `1px solid ${color}44`,
      display: "inline-flex", alignItems: "center", gap: 4,
    }}>
      {meta.icon} {meta.label}
    </span>
  );
}

// ── Audit Card ─────────────────────────────────────────────────────────────────

function AuditCard({ entry, T, selected, onSelect, onDelete, selectable }) {
  const rc = riskColorFromEntry(entry, T);
  const isSelected = selected;

  return (
    <div style={{
      background: isSelected ? T.surfaceHi : T.surface,
      border: `1.5px solid ${isSelected ? rc : T.border}`,
      borderRadius: 12, padding: "16px 18px",
      display: "flex", gap: 16, alignItems: "flex-start",
      transition: "all .15s", cursor: selectable ? "pointer" : "default",
      boxShadow: isSelected ? `0 0 0 2px ${rc}33` : "none",
    }}
      onClick={selectable ? onSelect : undefined}
    >
      {/* Ring */}
      <div style={{ paddingTop: 2 }}>
        {entry.trustScore != null
          ? <TrustRing score={entry.trustScore} riskColor={rc} size={64} />
          : (
            <div style={{
              width: 64, height: 64, borderRadius: "50%",
              background: T.surfaceHi, border: `2px dashed ${T.border}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              color: T.textDim, fontSize: 11,
            }}>N/A</div>
          )
        }
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
          <div style={{ color: "#fff", fontWeight: 700, fontSize: 14, wordBreak: "break-all" }}>
            {entry.csvName || "audit"}
          </div>
          {entry.riskLevel && (
            <span style={{
              fontSize: 10, fontWeight: 800, padding: "3px 10px", borderRadius: 10,
              background: rc + "22", color: rc, border: `1px solid ${rc}44`, flexShrink: 0,
            }}>
              {entry.riskLevel}
            </span>
          )}
        </div>

        <div style={{ color: T.textDim, fontSize: 11, marginTop: 3 }}>{fmtDate(entry.timestamp)}</div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
          {(entry.modules || []).map(m => (
            <ModuleBadge key={m} mod={m} T={T} />
          ))}
        </div>

        <div style={{ color: T.textDim, fontSize: 10, marginTop: 6, fontFamily: "monospace" }}>
          ID: {entry.id?.slice(0, 18)}…
        </div>
      </div>

      {/* Delete */}
      {onDelete && (
        <button
          onClick={e => { e.stopPropagation(); onDelete(entry.id); }}
          title="Delete"
          style={{
            background: "none", border: `1px solid ${T.border}`,
            borderRadius: 5, color: T.textDim, fontSize: 12,
            padding: "3px 7px", cursor: "pointer", flexShrink: 0,
            fontFamily: T.font, lineHeight: 1,
          }}
        >✕</button>
      )}
    </div>
  );
}

// ── Comparison View ────────────────────────────────────────────────────────────

function CompareRow({ label, valA, valB, T, higherIsBetter = true }) {
  const numA = typeof valA === "number" ? valA : parseFloat(valA);
  const numB = typeof valB === "number" ? valB : parseFloat(valB);
  const hasNum = !isNaN(numA) && !isNaN(numB);

  let colorA = T.textDim, colorB = T.textDim;
  if (hasNum && numA !== numB) {
    const aIsBetter = higherIsBetter ? numA > numB : numA < numB;
    colorA = aIsBetter ? T.green : T.red;
    colorB = aIsBetter ? T.red : T.green;
  }

  const fmt = (v) => {
    if (v == null) return "—";
    if (typeof v === "number") return v.toFixed(1);
    return String(v);
  };

  return (
    <div style={{
      display: "grid", gridTemplateColumns: "1fr 1fr 1fr",
      padding: "7px 0", borderBottom: `1px solid ${T.border}`,
      alignItems: "center",
    }}>
      <span style={{ color: T.textDim, fontSize: 12 }}>{label}</span>
      <span style={{ color: colorA, fontWeight: 700, fontSize: 13, textAlign: "center" }}>{fmt(valA)}</span>
      <span style={{ color: colorB, fontWeight: 700, fontSize: 13, textAlign: "center" }}>{fmt(valB)}</span>
    </div>
  );
}

function ComparePanel({ a, b, T }) {
  const rcA = riskColorFromEntry(a, T);
  const rcB = riskColorFromEntry(b, T);

  // Module union
  const allMods = [...new Set([...(a.modules || []), ...(b.modules || [])])];

  return (
    <div style={{
      background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 14, padding: "22px 24px", marginTop: 24,
    }}>
      <div style={{
        color: T.textDim, fontSize: 11, fontWeight: 700,
        textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 18,
      }}>
        Side-by-Side Comparison
      </div>

      {/* Header row */}
      <div style={{
        display: "grid", gridTemplateColumns: "1fr 1fr 1fr",
        marginBottom: 12, gap: 8,
      }}>
        <div />
        {[a, b].map((entry, i) => {
          const rc = i === 0 ? rcA : rcB;
          return (
            <div key={i} style={{ textAlign: "center" }}>
              <TrustRing score={entry.trustScore} riskColor={rc} size={56} />
              <div style={{ color: "#fff", fontSize: 12, fontWeight: 700, marginTop: 6, wordBreak: "break-all" }}>
                {entry.csvName || "audit"}
              </div>
              <div style={{ color: T.textDim, fontSize: 10 }}>{fmtDate(entry.timestamp)}</div>
            </div>
          );
        })}
      </div>

      {/* Metrics */}
      <CompareRow label="Trust Score"  valA={a.trustScore}  valB={b.trustScore}  T={T} higherIsBetter />
      <CompareRow label="Risk Level"   valA={a.riskLevel}   valB={b.riskLevel}   T={T} higherIsBetter={false} />
      <CompareRow label="Modules Run"  valA={(a.modules||[]).length} valB={(b.modules||[]).length} T={T} higherIsBetter />

      {/* Module presence */}
      <div style={{ marginTop: 14 }}>
        <div style={{ color: T.textDim, fontSize: 10, fontWeight: 700, textTransform: "uppercase", marginBottom: 8 }}>
          Modules
        </div>
        {allMods.map(mod => {
          const color = moduleColor(mod, T);
          const meta  = MODULE_META[mod] || { label: mod, icon: "●" };
          const hasA  = (a.modules || []).includes(mod);
          const hasB  = (b.modules || []).includes(mod);
          return (
            <div key={mod} style={{
              display: "grid", gridTemplateColumns: "1fr 1fr 1fr",
              padding: "5px 0", borderBottom: `1px solid ${T.border}`, alignItems: "center",
            }}>
              <span style={{ color, fontSize: 12 }}>{meta.icon} {meta.label}</span>
              <span style={{ textAlign: "center", color: hasA ? color : T.border, fontSize: 16 }}>
                {hasA ? "✓" : "–"}
              </span>
              <span style={{ textAlign: "center", color: hasB ? color : T.border, fontSize: 16 }}>
                {hasB ? "✓" : "–"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main HistoryPage ───────────────────────────────────────────────────────────

const HistoryPage = () => {
  const { T } = useTheme();
  const [history,   setHistory]   = useState([]);
  const [compareA,  setCompareA]  = useState(null);
  const [compareB,  setCompareB]  = useState(null);
  const [comparing, setComparing] = useState(false);

  const reload = () => setHistory(loadAuditHistory());

  useEffect(() => {
    reload();
    const handler = () => reload();
    window.addEventListener("ecopulse_history_updated", handler);
    return () => window.removeEventListener("ecopulse_history_updated", handler);
  }, []);

  const handleDelete = (id) => {
    try {
      const updated = history.filter(e => e.id !== id);
      localStorage.setItem("ecopulse_audit_history", JSON.stringify(updated));
      setHistory(updated);
      if (compareA?.id === id) setCompareA(null);
      if (compareB?.id === id) setCompareB(null);
    } catch { /* non-fatal */ }
  };

  const handleClearAll = () => {
    clearAuditHistory();
    setHistory([]);
    setCompareA(null);
    setCompareB(null);
    setComparing(false);
  };

  const handleSelect = (entry) => {
    if (!comparing) return;
    if (!compareA) { setCompareA(entry); return; }
    if (compareA.id === entry.id) { setCompareA(null); return; }
    if (!compareB) { setCompareB(entry); return; }
    if (compareB.id === entry.id) { setCompareB(null); return; }
    // swap oldest selection
    setCompareB(entry);
  };

  const isSelected = (entry) =>
    compareA?.id === entry.id || compareB?.id === entry.id;

  const canCompare = compareA && compareB;

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: "32px 24px", fontFamily: T.font }}>
      {/* Page header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 28, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ color: "#fff", fontSize: 22, fontWeight: 900, margin: 0 }}>
            📋 Audit History
          </h1>
          <p style={{ color: T.textDim, fontSize: 13, margin: "4px 0 0" }}>
            {history.length} audit{history.length !== 1 ? "s" : ""} saved locally
          </p>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {history.length >= 2 && (
            <button
              onClick={() => {
                setComparing(v => !v);
                if (comparing) { setCompareA(null); setCompareB(null); }
              }}
              style={{
                padding: "8px 16px", borderRadius: 8, cursor: "pointer",
                background: comparing ? T.violetDim : T.surfaceHi,
                border: `1px solid ${comparing ? T.violet : T.border}`,
                color: comparing ? T.violet : T.textDim,
                fontSize: 12, fontWeight: 700, fontFamily: T.font,
              }}
            >
              {comparing ? "✕ Cancel Compare" : "⇄ Compare Two"}
            </button>
          )}
          {history.length > 0 && (
            <button
              onClick={handleClearAll}
              style={{
                padding: "8px 16px", borderRadius: 8, cursor: "pointer",
                background: T.surfaceHi, border: `1px solid ${T.border}`,
                color: T.textDim, fontSize: 12, fontWeight: 700, fontFamily: T.font,
              }}
            >
              🗑 Clear All
            </button>
          )}
        </div>
      </div>

      {/* Compare hint */}
      {comparing && (
        <div style={{
          background: T.violetDim, border: `1px solid ${T.violet}44`,
          borderRadius: 10, padding: "10px 16px", marginBottom: 20,
          color: T.violet, fontSize: 13, fontWeight: 600,
        }}>
          {!compareA && !compareB && "Select two audits to compare them side by side."}
          {compareA && !compareB && `✓ Selected "${compareA.csvName}". Now pick a second audit.`}
          {compareA && compareB && `Comparing "${compareA.csvName}" vs "${compareB.csvName}"`}
        </div>
      )}

      {/* Empty state */}
      {history.length === 0 && (
        <div style={{
          background: T.surface, border: `1px dashed ${T.border}`,
          borderRadius: 14, padding: "48px 24px", textAlign: "center",
        }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📭</div>
          <div style={{ color: "#fff", fontWeight: 700, fontSize: 16, marginBottom: 6 }}>No audits yet</div>
          <div style={{ color: T.textDim, fontSize: 13 }}>
            Run an audit from the Home page — results will appear here automatically.
          </div>
        </div>
      )}

      {/* Audit cards grid */}
      {history.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {history.map(entry => (
            <AuditCard
              key={entry.id}
              entry={entry}
              T={T}
              selected={isSelected(entry)}
              onSelect={() => handleSelect(entry)}
              onDelete={handleDelete}
              selectable={comparing}
            />
          ))}
        </div>
      )}

      {/* Comparison panel */}
      {comparing && canCompare && (
        <ComparePanel a={compareA} b={compareB} T={T} />
      )}
    </div>
  );
};

export default HistoryPage;
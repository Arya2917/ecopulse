// frontend/src/components/AIInsightCard.jsx
// ═══════════════════════════════════════════════════════════════════════════════
// Reusable AI Governance Copilot card.
// Handles: loading skeleton, Ollama call, structured result display,
//          retry button, copy-to-clipboard, error state.
//
// Usage:
//   <AIInsightCard
//     jobId={jobId}
//     type="fairness"          // "fairness" | "explainability" | "compliance"
//     T={T}                    // theme object
//   />
// ═══════════════════════════════════════════════════════════════════════════════

import React, { useState, useCallback } from "react";
import {
  getAIFairnessInsight,
  getAIExplainabilityInsight,
  getAIComplianceInsight,
  getAIEnergyInsight,
} from "../utils/api";

// ── Config per type ────────────────────────────────────────────────────────────

const TYPE_CONFIG = {
  fairness: {
    label:       "AI Fairness Consultant",
    buttonLabel: "🤖 Explain This Fairness Result",
    icon:        "⚖️",
    colorKey:    "amber",
    fetcher:     getAIFairnessInsight,
    sections: [
      { key: "summary",         title: "Executive Summary"         },
      { key: "risk_level",      title: "Fairness Risk Level"       },
      { key: "root_causes",     title: "Root Cause Analysis"       },
      { key: "affected_groups", title: "Affected Groups"           },
      { key: "recommendations", title: "Recommended Mitigations"   },
      { key: "tradeoffs",       title: "Trade-offs"                },
      { key: "monitoring",      title: "Monitoring Recommendations" },
    ],
  },
  explainability: {
    label:       "AI Explainability Narrator",
    buttonLabel: "🤖 Explain This Model Behavior",
    icon:        "🔍",
    colorKey:    "violet",
    fetcher:     getAIExplainabilityInsight,
    sections: [
      { key: "summary",                 title: "Executive Summary"        },
      { key: "important_features",      title: "Most Important Features"  },
      { key: "feature_interactions",    title: "Feature Interactions"     },
      { key: "bias_indicators",         title: "Potential Bias Indicators"},
      { key: "confidence",              title: "Confidence of Explanation"},
      { key: "business_interpretation", title: "Business Interpretation"  },
      { key: "recommendations",         title: "Recommendations"          },
    ],
  },
  compliance: {
    label:       "AI Compliance Advisor",
    buttonLabel: "🤖 Explain This Compliance Report",
    icon:        "🛡️",
    colorKey:    "green",
    fetcher:     getAIComplianceInsight,
    sections: [
      { key: "summary",            title: "Compliance Summary"    },
      { key: "risk",               title: "Risk Level"            },
      { key: "violations",         title: "Regulatory Violations" },
      { key: "legal_implications", title: "Legal Implications"    },
      { key: "recommendations",    title: "Recommended Actions"   },
      { key: "roadmap",            title: "Compliance Roadmap"    },
    ],
  },
  energy: {
    label:       "AI Sustainability Advisor",
    buttonLabel: "🤖 Explain This Energy Report",
    icon:        "🌱",
    colorKey:    "green",
    fetcher:     getAIEnergyInsight,

    sections: [
      { key: "summary",         title: "Executive Summary" },
      { key: "rating",          title: "Sustainability Rating" },
      { key: "environment",     title: "Environmental Impact" },
      { key: "findings",        title: "Key Findings" },
      { key: "recommendations", title: "Recommendations" },
    ],
  },
};

// ── Loading Skeleton ───────────────────────────────────────────────────────────

function Skeleton({ T }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "4px 0" }}>
      {[100, 85, 92, 70, 88].map((w, i) => (
        <div key={i} style={{
          height: 13, borderRadius: 6,
          width: `${w}%`,
          background: `linear-gradient(90deg, ${T.surfaceHi} 25%, ${T.border} 50%, ${T.surfaceHi} 75%)`,
          backgroundSize: "200% 100%",
          animation: "ai-shimmer 1.5s infinite",
        }} />
      ))}
    </div>
  );
}

// ── Simple markdown-ish renderer ───────────────────────────────────────────────
// Converts bullet lines and bold to styled spans — no external deps needed.

function SimpleMarkdown({ text, T }) {
  if (!text) return null;
  const lines = text.split("\n");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={i} style={{ height: 6 }} />;

        // Bullet lines
        const isBullet = trimmed.startsWith("- ") || trimmed.startsWith("• ");
        const content  = isBullet ? trimmed.slice(2) : trimmed;

        // Bold: **text**
        const parts = content.split(/\*\*(.*?)\*\*/g);
        const rendered = parts.map((part, j) =>
          j % 2 === 1
            ? <strong key={j} style={{ color: T.text, fontWeight: 700 }}>{part}</strong>
            : <span key={j}>{part}</span>
        );

        return (
          <div key={i} style={{
            display: "flex", gap: 8, alignItems: "flex-start",
            paddingLeft: isBullet ? 4 : 0,
          }}>
            {isBullet && (
              <span style={{ color: T.textDim, flexShrink: 0, marginTop: 2, fontSize: 11 }}>▸</span>
            )}
            <span style={{ color: T.text, fontSize: 13, lineHeight: 1.6 }}>{rendered}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Section block ──────────────────────────────────────────────────────────────

function SectionBlock({ title, content, accentColor, T }) {
  const [expanded, setExpanded] = useState(true);
  if (!content) return null;
  return (
    <div style={{
      background: T.surfaceHi, borderRadius: 10,
      border: `1px solid ${T.border}`, overflow: "hidden",
      marginBottom: 8,
    }}>
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "10px 14px", cursor: "pointer",
          borderBottom: expanded ? `1px solid ${T.border}` : "none",
        }}
      >
        <span style={{
          fontSize: 12, fontWeight: 700, color: accentColor,
          textTransform: "uppercase", letterSpacing: "0.05em",
        }}>{title}</span>
        <span style={{ color: T.textDim, fontSize: 12 }}>{expanded ? "▲" : "▼"}</span>
      </div>
      {expanded && (
        <div style={{ padding: "12px 14px" }}>
          <SimpleMarkdown text={content} T={T} />
        </div>
      )}
    </div>
  );
}

// ── Main AIInsightCard ─────────────────────────────────────────────────────────

export default function AIInsightCard({ jobId, type, T }) {
  const config = TYPE_CONFIG[type];

  // All hooks must be called unconditionally — early return comes AFTER hooks
  const accentColor = config ? (T[config.colorKey] || T.sky) : T.sky;

  const [state,   setState]   = useState("idle");   // idle | loading | done | error
  const [result,  setResult]  = useState(null);
  const [errMsg,  setErrMsg]  = useState("");
  const [copied,  setCopied]  = useState(false);

  const handleFetch = useCallback(async () => {
    setState("loading");
    setErrMsg("");
    setResult(null);
    try {
      const data = await config.fetcher(jobId);
      if (data.error) {
        setErrMsg(data.error + (data.hint ? `\n\nHint: ${data.hint}` : ""));
        setState("error");
      } else {
        setResult(data);
        setState("done");
      }
    } catch (e) {
      setErrMsg(String(e));
      setState("error");
    }
  }, [jobId, config]);

  const handleCopy = () => {
    const text = result?.raw || config.sections
      .map(s => `${s.title}\n${result?.[s.key] || ""}`)
      .join("\n\n");
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (!config) return null;

  return (
    <div style={{
      background: T.surface,
      border: `1px solid ${accentColor}33`,
      borderRadius: 12,
      overflow: "hidden",
      marginBottom: 12,
    }}>
      <style>{`
        @keyframes ai-shimmer {
          0%   { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        @keyframes ai-spin { to { transform: rotate(360deg); } }
      `}</style>

      {/* Header */}
      <div style={{
        padding: "14px 18px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        borderBottom: state !== "idle" ? `1px solid ${T.border}` : "none",
        background: accentColor + "0d",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 20 }}>{config.icon}</span>
          <div>
            <div style={{ fontWeight: 700, color: T.text, fontSize: 14 }}>{config.label}</div>
            <div style={{ fontSize: 11, color: T.textDim, marginTop: 1 }}>
              Powered by llama3 · local execution
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {state === "done" && (
            <button
              onClick={handleCopy}
              style={{
                background: T.surfaceHi, border: `1px solid ${T.border}`,
                borderRadius: 6, padding: "5px 12px", cursor: "pointer",
                color: copied ? T.green : T.textDim, fontSize: 12, fontFamily: T.font,
              }}
            >
              {copied ? "✓ Copied" : "📋 Copy"}
            </button>
          )}

          {(state === "idle" || state === "error" || state === "done") && (
            <button
              onClick={handleFetch}
              style={{
                background: state === "done"
                  ? T.surfaceHi
                  : `linear-gradient(135deg, ${accentColor}, ${accentColor}cc)`,
                border: state === "done" ? `1px solid ${T.border}` : "none",
                borderRadius: 7, padding: "7px 16px",
                color: state === "done" ? T.textDim : "#000",
                fontWeight: 700, fontSize: 13, cursor: "pointer", fontFamily: T.font,
              }}
            >
              {state === "done"   ? "🔄 Re-run"
               : state === "error" ? "🔄 Retry"
               : config.buttonLabel}
            </button>
          )}

          {state === "loading" && (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{
                width: 16, height: 16, borderRadius: "50%",
                border: `2px solid ${accentColor}44`,
                borderTop: `2px solid ${accentColor}`,
                animation: "ai-spin .7s linear infinite",
              }} />
              <span style={{ color: T.textDim, fontSize: 13 }}>
                Asking llama3…
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Loading skeleton */}
      {state === "loading" && (
        <div style={{ padding: "16px 18px" }}>
          <div style={{ color: T.textDim, fontSize: 12, marginBottom: 12 }}>
            ⏳ Generating AI analysis — this takes 15–60 seconds…
          </div>
          <Skeleton T={T} />
        </div>
      )}

      {/* Error state */}
      {state === "error" && (
        <div style={{
          padding: "14px 18px",
          background: T.redDim,
          borderTop: `1px solid ${T.red}33`,
        }}>
          <div style={{ color: T.red, fontWeight: 700, fontSize: 13, marginBottom: 4 }}>
            ⚠ Failed to get AI analysis
          </div>
          <div style={{ color: T.red, fontSize: 12, whiteSpace: "pre-wrap" }}>{errMsg}</div>
        </div>
      )}

      {/* Results */}
      {state === "done" && result && (
        <div style={{ padding: "16px 18px" }}>
          {config.sections.map(s => (
            <SectionBlock
              key={s.key}
              title={s.title}
              content={result[s.key]}
              accentColor={accentColor}
              T={T}
            />
          ))}
        </div>
      )}
    </div>
  );
}
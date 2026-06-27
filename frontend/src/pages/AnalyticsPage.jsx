// frontend/src/pages/AnalyticsPage.jsx
// ─────────────────────────────────────────────────────────────────────────────
// Interactive Analytics Dashboard — Recharts-powered, hover insights, drill-down
// ─────────────────────────────────────────────────────────────────────────────

import React, { useState, useEffect } from "react";
import { useTheme } from "../theme";
import { loadAuditHistory } from "./HomePage";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, AreaChart, Area, Cell, Legend,
} from "recharts";

// ── Custom Tooltip ─────────────────────────────────────────────────────────────

function CustomTooltip({ active, payload, label, T, unit = "" }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 10, padding: "12px 16px",
      boxShadow: "0 8px 32px #00000066", fontFamily: T.font,
    }}>
      <p style={{ color: T.textDim, fontSize: 11, margin: "0 0 8px", fontWeight: 700,
        textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</p>
      {payload.map((p, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: p.color, flexShrink: 0 }} />
          <span style={{ color: "#fff", fontSize: 13, fontWeight: 700 }}>
            {typeof p.value === "number" ? p.value.toFixed(2) : p.value}{unit}
          </span>
          <span style={{ color: T.textDim, fontSize: 11 }}>{p.name}</span>
        </div>
      ))}
    </div>
  );
}

// ── Score Gauge ────────────────────────────────────────────────────────────────

function ScoreGauge({ score, label, color, size = 100 }) {
  const r = (size - 12) / 2;
  const circ = 2 * Math.PI * r;
  const clamp = Math.min(Math.max(score ?? 0, 0), 100);
  const dash = circ * (clamp / 100);
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color + "22"} strokeWidth={10} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={10}
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
          style={{ transition: "stroke-dasharray 1.2s cubic-bezier(.4,0,.2,1)" }} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center" }}>
        <span style={{ color, fontSize: size * 0.2, fontWeight: 900, lineHeight: 1 }}>
          {clamp.toFixed(0)}
        </span>
        <span style={{ color: "#6b7280", fontSize: size * 0.1, marginTop: 2, textAlign: "center",
          maxWidth: size * 0.7, lineHeight: 1.2 }}>{label}</span>
      </div>
    </div>
  );
}

// ── Animated Pipeline ─────────────────────────────────────────────────────────

const PIPELINE_STAGES = [
  { id: "fairness",       label: "Fairness",       icon: "⚖",  color: "#f59e0b", desc: "Demographic parity & bias analysis" },
  { id: "explainability", label: "Explainability",  icon: "🔍", color: "#a78bfa", desc: "SHAP values & feature importance"    },
  { id: "compliance",     label: "Compliance",      icon: "🛡",  color: "#22c55e", desc: "PII detection & regulatory scan"    },
  { id: "energy",         label: "Energy",          icon: "⚡", color: "#38bdf8", desc: "CO₂ footprint & power metrics"      },
];

function AuditPipeline({ T }) {
  const [active, setActive] = useState(null);
  const [flowing, setFlowing] = useState(true);
  const [pulseIdx, setPulseIdx] = useState(0);

  useEffect(() => {
    if (!flowing) return;
    const t = setInterval(() => setPulseIdx(i => (i + 1) % PIPELINE_STAGES.length), 900);
    return () => clearInterval(t);
  }, [flowing]);

  return (
    <div style={{
      background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 14, padding: "28px 24px", marginBottom: 20,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 22 }}>
        <div>
          <h3 style={{ color: "#fff", fontSize: 15, fontWeight: 800, margin: 0 }}>
            ⚡ Audit Pipeline
          </h3>
          <p style={{ color: T.textDim, fontSize: 12, margin: "4px 0 0" }}>
            Hover a stage to inspect · Click to drill down
          </p>
        </div>
        <button onClick={() => setFlowing(f => !f)} style={{
          padding: "5px 12px", borderRadius: 6, fontSize: 11, fontWeight: 700,
          background: T.surfaceHi, border: `1px solid ${T.border}`,
          color: T.textDim, cursor: "pointer", fontFamily: T.font,
        }}>
          {flowing ? "⏸ Pause" : "▶ Play"}
        </button>
      </div>

      {/* Pipeline row */}
      <div style={{ display: "flex", alignItems: "center", gap: 0, overflowX: "auto", paddingBottom: 4 }}>
        {PIPELINE_STAGES.map((stage, i) => {
          const isPulse  = flowing && pulseIdx === i;
          const isActive = active === stage.id;
          return (
            <React.Fragment key={stage.id}>
              {/* Stage node */}
              <div
                onClick={() => setActive(a => a === stage.id ? null : stage.id)}
                onMouseEnter={() => !flowing && setActive(stage.id)}
                style={{
                  flex: "0 0 auto", minWidth: 110, cursor: "pointer",
                  display: "flex", flexDirection: "column", alignItems: "center", gap: 10,
                  padding: "14px 10px", borderRadius: 12, transition: "all .25s",
                  background: isActive ? stage.color + "18" : isPulse ? stage.color + "12" : "transparent",
                  border: `1.5px solid ${isActive || isPulse ? stage.color + "88" : T.border}`,
                  transform: isPulse ? "translateY(-3px)" : "none",
                  boxShadow: isPulse ? `0 8px 24px ${stage.color}33` : "none",
                }}
              >
                <div style={{
                  width: 48, height: 48, borderRadius: 14,
                  background: isActive || isPulse ? stage.color + "28" : T.surfaceHi,
                  border: `2px solid ${isActive || isPulse ? stage.color : T.border}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 22, transition: "all .25s",
                  boxShadow: isPulse ? `0 0 16px ${stage.color}66` : "none",
                }}>
                  {stage.icon}
                </div>
                <span style={{
                  color: isActive || isPulse ? "#fff" : T.textDim,
                  fontSize: 12, fontWeight: 700, textAlign: "center",
                  transition: "color .25s",
                }}>{stage.label}</span>
                <span style={{
                  color: isActive || isPulse ? stage.color : T.textDim,
                  fontSize: 10, textAlign: "center", lineHeight: 1.3,
                  maxWidth: 90, transition: "all .25s",
                }}>{stage.desc}</span>
              </div>

              {/* Connector */}
              {i < PIPELINE_STAGES.length - 1 && (
                <div style={{ flex: "0 0 auto", width: 48, display: "flex", alignItems: "center",
                  justifyContent: "center", position: "relative", height: 4 }}>
                  <div style={{
                    width: "100%", height: 2,
                    background: `linear-gradient(90deg, ${PIPELINE_STAGES[i].color}44, ${PIPELINE_STAGES[i+1].color}44)`,
                    borderRadius: 2,
                    position: "relative", overflow: "hidden",
                  }}>
                    {/* Flowing dot */}
                    {flowing && (
                      <div style={{
                        position: "absolute", top: -3, width: 8, height: 8,
                        borderRadius: "50%",
                        background: PIPELINE_STAGES[i].color,
                        animation: `flow-dot-${i} 3.6s ease-in-out infinite`,
                        animationDelay: `${i * 0.9}s`,
                        boxShadow: `0 0 8px ${PIPELINE_STAGES[i].color}`,
                      }} />
                    )}
                  </div>
                  <span style={{
                    position: "absolute", fontSize: 10, color: T.textDim, top: -16,
                  }}>→</span>
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Drill-down panel */}
      {active && (() => {
        const stage = PIPELINE_STAGES.find(s => s.id === active);
        const drillInfo = {
          fairness: [
            { metric: "Demographic Parity Δ", value: "0.042", status: "pass" },
            { metric: "Equalized Odds Δ",     value: "0.078", status: "pass" },
            { metric: "FPR Difference",        value: "0.031", status: "pass" },
            { metric: "FNR Difference",        value: "0.092", status: "warn" },
          ],
          explainability: [
            { metric: "Top Feature (SHAP)",    value: "income",    status: "info" },
            { metric: "SHAP–LIME Agreement",   value: "87%",       status: "pass" },
            { metric: "Features Explained",    value: "12 / 15",   status: "pass" },
            { metric: "Global Fidelity",       value: "0.93",      status: "pass" },
          ],
          compliance: [
            { metric: "PII Entities Found",    value: "3",         status: "warn" },
            { metric: "High Severity",         value: "1",         status: "fail" },
            { metric: "GDPR Risk",             value: "Medium",    status: "warn" },
            { metric: "HIPAA Risk",            value: "Low",       status: "pass" },
          ],
          energy: [
            { metric: "Energy Consumed",       value: "2.4 Wh",    status: "pass" },
            { metric: "CO₂ Emitted",           value: "1.1 g",     status: "pass" },
            { metric: "Efficiency Score",      value: "91/100",    status: "pass" },
            { metric: "Epochs",                value: "5",         status: "info" },
          ],
        };
        const rows = drillInfo[active] || [];
        const statusColor = { pass: "#22c55e", warn: "#f59e0b", fail: "#ef4444", info: "#38bdf8" };
        return (
          <div style={{
            marginTop: 20, padding: "16px 18px", borderRadius: 10,
            background: stage.color + "0d", border: `1px solid ${stage.color}33`,
            animation: "fadeUp .2s ease",
          }}>
            <div style={{ color: stage.color, fontWeight: 800, fontSize: 13, marginBottom: 12 }}>
              {stage.icon} {stage.label} — Drill-down Metrics
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {rows.map(r => (
                <div key={r.metric} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "8px 12px", borderRadius: 7, background: T.surfaceHi,
                  border: `1px solid ${T.border}`,
                }}>
                  <span style={{ color: T.text, fontSize: 12 }}>{r.metric}</span>
                  <span style={{
                    color: statusColor[r.status] || T.text, fontSize: 12, fontWeight: 700,
                    fontFamily: "monospace",
                  }}>{r.value}</span>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      <style>{`
        @keyframes fadeUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes flow-dot-0 { 0%,100% { left: -8px; opacity: 0; } 10% { opacity: 1; } 90% { opacity: 1; } 95% { left: 100%; opacity: 0; } }
        @keyframes flow-dot-1 { 0%,100% { left: -8px; opacity: 0; } 10% { opacity: 1; } 90% { opacity: 1; } 95% { left: 100%; opacity: 0; } }
        @keyframes flow-dot-2 { 0%,100% { left: -8px; opacity: 0; } 10% { opacity: 1; } 90% { opacity: 1; } 95% { left: 100%; opacity: 0; } }
      `}</style>
    </div>
  );
}

// ── Main Analytics Page ────────────────────────────────────────────────────────

const AnalyticsPage = () => {
  const { T } = useTheme();
  const [history, setHistory] = useState([]);
  const [drillModule, setDrillModule] = useState(null);

  useEffect(() => {
    setHistory(loadAuditHistory());
  }, []);

  // Build chart data from history (or use demo data)
  const hasData = history.length > 0;

  const trustTrend = hasData
    ? history.slice(0, 10).reverse().map((h, i) => ({
        name: `Audit ${i + 1}`, score: h.trustScore ?? 70,
        risk: h.riskLevel,
      }))
    : [
        { name: "Jan", score: 62 }, { name: "Feb", score: 71 },
        { name: "Mar", score: 68 }, { name: "Apr", score: 80 },
        { name: "May", score: 77 }, { name: "Jun", score: 85 },
      ];

  const radarData = [
    { subject: "Fairness",       score: 82, fullMark: 100 },
    { subject: "Explainability", score: 74, fullMark: 100 },
    { subject: "Compliance",     score: 91, fullMark: 100 },
    { subject: "Energy",         score: 67, fullMark: 100 },
  ];

  const moduleBarData = [
    { module: "Fairness",       pass: 14, warn: 3, fail: 1, color: "#f59e0b" },
    { module: "Explainability", pass: 11, warn: 2, fail: 0, color: "#a78bfa" },
    { module: "Compliance",     pass: 9,  warn: 5, fail: 2, color: "#22c55e" },
    { module: "Energy",         pass: 16, warn: 1, fail: 0, color: "#38bdf8" },
  ];

  const energyData = [
    { run: "R1", kwh: 0.0021, co2: 0.0009 },
    { run: "R2", kwh: 0.0034, co2: 0.0014 },
    { run: "R3", kwh: 0.0018, co2: 0.0008 },
    { run: "R4", kwh: 0.0042, co2: 0.0019 },
    { run: "R5", kwh: 0.0025, co2: 0.0011 },
    { run: "R6", kwh: 0.0031, co2: 0.0013 },
  ];

  const card = {
    background: T.surface, border: `1px solid ${T.border}`,
    borderRadius: 14, padding: "22px 24px", marginBottom: 20,
  };

  const sectionHead = {
    color: "#fff", fontWeight: 800, fontSize: 15, margin: "0 0 4px",
  };
  const sectionSub = {
    color: T.textDim, fontSize: 12, margin: "0 0 20px",
  };

  const avgScore = trustTrend.reduce((s, d) => s + d.score, 0) / trustTrend.length;

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "36px 24px", fontFamily: T.font }}>

      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ color: "#fff", fontSize: 26, fontWeight: 900, margin: "0 0 6px",
          letterSpacing: "-0.02em" }}>
          📊 Analytics <span style={{ color: T.amber }}>Dashboard</span>
        </h1>
        <p style={{ color: T.textDim, fontSize: 14, margin: 0 }}>
          Interactive insights across all audit dimensions — hover charts for details
        </p>
      </div>

      {/* Top KPI row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 20 }}>
        {[
          { label: "Avg Trust Score", value: avgScore.toFixed(1), unit: "/100", color: T.amber   },
          { label: "Total Audits",    value: hasData ? history.length : "—", unit: "", color: T.sky    },
          { label: "Compliance Rate", value: "91",                unit: "%",   color: T.green  },
          { label: "Avg CO₂",        value: "1.2",               unit: "g",   color: T.violet },
        ].map(k => (
          <div key={k.label} style={{
            background: T.surface, border: `1px solid ${T.border}`,
            borderRadius: 12, padding: "18px 20px",
          }}>
            <div style={{ color: T.textDim, fontSize: 11, fontWeight: 700,
              textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>{k.label}</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
              <span style={{ color: k.color, fontSize: 26, fontWeight: 900, lineHeight: 1 }}>{k.value}</span>
              <span style={{ color: T.textDim, fontSize: 12 }}>{k.unit}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Animated Pipeline */}
      <AuditPipeline T={T} />

      {/* Two-col charts */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>

        {/* Trust Score Trend */}
        <div style={card}>
          <h3 style={sectionHead}>Trust Score Trend</h3>
          <p style={sectionSub}>Hover for details per audit run</p>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={trustTrend}>
              <defs>
                <linearGradient id="trustGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={T.amber} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={T.amber} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={T.border} />
              <XAxis dataKey="name" stroke={T.textDim} tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} stroke={T.textDim} tick={{ fontSize: 11 }} />
              <Tooltip content={<CustomTooltip T={T} unit="/100" />} />
              <Area type="monotone" dataKey="score" name="Trust Score"
                stroke={T.amber} fill="url(#trustGrad)" strokeWidth={2.5}
                dot={{ fill: T.amber, r: 4 }} activeDot={{ r: 6, fill: T.amber }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Radar — Module Health */}
        <div style={card}>
          <h3 style={sectionHead}>Module Health Radar</h3>
          <p style={sectionSub}>Composite score across all dimensions</p>
          <ResponsiveContainer width="100%" height={200}>
            <RadarChart data={radarData}>
              <PolarGrid stroke={T.border} />
              <PolarAngleAxis dataKey="subject" tick={{ fill: T.textDim, fontSize: 11 }} />
              <PolarRadiusAxis domain={[0, 100]} tick={{ fill: T.textDim, fontSize: 9 }} />
              <Radar name="Score" dataKey="score" stroke={T.violet}
                fill={T.violet} fillOpacity={0.2} dot={{ r: 4, fill: T.violet }} />
              <Tooltip content={<CustomTooltip T={T} unit="/100" />} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Module pass/warn/fail bar */}
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <div>
            <h3 style={sectionHead}>Module Findings Breakdown</h3>
            <p style={sectionSub}>Pass · Warn · Fail per audit module — click a bar for details</p>
          </div>
          <div style={{ display: "flex", gap: 14 }}>
            {[["Pass", T.green], ["Warn", T.amber], ["Fail", T.red]].map(([l, c]) => (
              <div key={l} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <div style={{ width: 10, height: 10, borderRadius: 2, background: c }} />
                <span style={{ color: T.textDim, fontSize: 11 }}>{l}</span>
              </div>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={moduleBarData} barCategoryGap="30%">
            <CartesianGrid strokeDasharray="3 3" stroke={T.border} vertical={false} />
            <XAxis dataKey="module" stroke={T.textDim} tick={{ fontSize: 12 }} />
            <YAxis stroke={T.textDim} tick={{ fontSize: 11 }} />
            <Tooltip content={<CustomTooltip T={T} />} />
            <Bar dataKey="pass" name="Pass" stackId="a" fill={T.green} radius={[0,0,0,0]}
              onClick={(d) => setDrillModule(d.module)} />
            <Bar dataKey="warn" name="Warn" stackId="a" fill={T.amber}
              onClick={(d) => setDrillModule(d.module)} />
            <Bar dataKey="fail" name="Fail" stackId="a" fill={T.red} radius={[4,4,0,0]}
              onClick={(d) => setDrillModule(d.module)} />
          </BarChart>
        </ResponsiveContainer>

        {/* Drill-down detail */}
        {drillModule && (() => {
          const mod = moduleBarData.find(m => m.module === drillModule);
          if (!mod) return null;
          const total = mod.pass + mod.warn + mod.fail;
          return (
            <div style={{
              marginTop: 14, padding: "14px 16px", borderRadius: 10,
              background: T.surfaceHi, border: `1px solid ${T.border}`,
              animation: "fadeUp .2s ease",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <span style={{ color: "#fff", fontWeight: 700, fontSize: 13 }}>
                  {drillModule} — Finding Distribution
                </span>
                <button onClick={() => setDrillModule(null)} style={{
                  background: "none", border: "none", color: T.textDim,
                  cursor: "pointer", fontSize: 14,
                }}>✕</button>
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                {[
                  { label: "Pass", val: mod.pass, color: T.green  },
                  { label: "Warn", val: mod.warn, color: T.amber  },
                  { label: "Fail", val: mod.fail, color: T.red    },
                ].map(b => (
                  <div key={b.label} style={{ flex: 1, textAlign: "center",
                    padding: "12px 8px", borderRadius: 8,
                    background: b.color + "18", border: `1px solid ${b.color}44` }}>
                    <div style={{ color: b.color, fontSize: 22, fontWeight: 900 }}>{b.val}</div>
                    <div style={{ color: T.textDim, fontSize: 11 }}>{b.label}</div>
                    <div style={{ color: b.color, fontSize: 11, marginTop: 4 }}>
                      {((b.val / total) * 100).toFixed(0)}%
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })()}
      </div>

      {/* Energy chart */}
      <div style={card}>
        <h3 style={sectionHead}>Energy & Carbon Footprint</h3>
        <p style={sectionSub}>Per-run kWh and CO₂ emissions — hover for details</p>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={energyData}>
            <CartesianGrid strokeDasharray="3 3" stroke={T.border} />
            <XAxis dataKey="run" stroke={T.textDim} tick={{ fontSize: 11 }} />
            <YAxis yAxisId="left" stroke={T.sky}    tick={{ fontSize: 11 }} />
            <YAxis yAxisId="right" orientation="right" stroke={T.green} tick={{ fontSize: 11 }} />
            <Tooltip content={<CustomTooltip T={T} />} />
            <Legend wrapperStyle={{ color: T.textDim, fontSize: 12 }} />
            <Line yAxisId="left"  type="monotone" dataKey="kwh" name="Energy (kWh)"
              stroke={T.sky}   strokeWidth={2.5} dot={{ r: 4 }} activeDot={{ r: 6 }} />
            <Line yAxisId="right" type="monotone" dataKey="co2" name="CO₂ (kg)"
              stroke={T.green} strokeWidth={2.5} dot={{ r: 4 }} strokeDasharray="5 3" activeDot={{ r: 6 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Fairness score gauges */}
      <div style={card}>
        <h3 style={sectionHead}>Fairness Dimension Scores</h3>
        <p style={sectionSub}>Latest audit — scores out of 100</p>
        <div style={{ display: "flex", justifyContent: "space-around", flexWrap: "wrap", gap: 16 }}>
          {[
            { label: "Demographic\nParity",    score: 88, color: T.amber  },
            { label: "Equalized\nOdds",        score: 74, color: T.violet },
            { label: "FPR\nEquality",          score: 91, color: T.green  },
            { label: "FNR\nEquality",          score: 66, color: T.sky    },
            { label: "Predictive\nParity",     score: 80, color: "#f472b6" },
          ].map(g => (
            <div key={g.label} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
              <ScoreGauge score={g.score} label={g.label} color={g.color} size={90} />
            </div>
          ))}
        </div>
      </div>

      {!hasData && (
        <div style={{
          background: T.amberDim, border: `1px solid ${T.amber}44`,
          borderRadius: 10, padding: "14px 18px",
          color: T.amber, fontSize: 13, textAlign: "center",
        }}>
          📊 Charts above show demo data. Run an audit to populate with real results!
        </div>
      )}

      <style>{`@keyframes fadeUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; } }`}</style>
    </div>
  );
};

export default AnalyticsPage;
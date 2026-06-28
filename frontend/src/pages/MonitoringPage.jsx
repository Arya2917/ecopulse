// frontend/src/pages/MonitoringPage.jsx
// ═══════════════════════════════════════════════════════════════════════════════
// EcoPulse — Real-Time Monitoring Dashboard
//
// Features:
//   • Create monitors (manual baseline or auto-extract from audit job)
//   • Live drift charts (selection rate over time, PSI over time) via recharts
//   • Alert feed with severity badges
//   • Simulate traffic button for demo/testing
//   • Pause / Resume / Delete monitors
// ═══════════════════════════════════════════════════════════════════════════════

import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { useTheme } from "../theme";
import {
  createMonitor, listMonitors, getMonitorStatus,
  ingestBatch, pauseMonitor, resumeMonitor, deleteMonitor,
  listAuditJobs,
} from "../utils/api";

// ── Helpers ────────────────────────────────────────────────────────────────────

const fmtTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
};

const fmtDateTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

const psiLabel = (psi) => {
  if (psi == null) return { text: "—", color: "#6b7280" };
  if (psi >= 0.25)  return { text: "Critical",  color: "#ef4444" };
  if (psi >= 0.10)  return { text: "Warning",   color: "#f59e0b" };
  return               { text: "Stable",    color: "#22c55e" };
};

const GROUP_COLORS = ["#38bdf8", "#a78bfa", "#f59e0b", "#22c55e", "#ef4444", "#fb923c"];

// Seeded pseudo-random for demo simulation (stable across re-renders)
function seededRand(seed) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) & 0xffffffff;
    return (s >>> 0) / 0xffffffff;
  };
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color, T }) {
  return (
    <div style={{
      background: T.surface, border: `1px solid ${T.border}`,
      borderRadius: 10, padding: "16px 20px", flex: 1, minWidth: 130,
    }}>
      <div style={{ fontSize: 11, color: T.textDim, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 26, fontWeight: 800, color: color || T.text, lineHeight: 1 }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 12, color: T.textDim, marginTop: 5 }}>{sub}</div>}
    </div>
  );
}

function AlertBadge({ level, T }) {
  const map = {
    critical: { bg: T.redDim,    color: T.red,    label: "CRITICAL" },
    warning:  { bg: T.amberDim,  color: T.amber,  label: "WARNING"  },
    info:     { bg: T.skyDim,    color: T.sky,     label: "INFO"     },
  };
  const s = map[level] || map.info;
  return (
    <span style={{
      fontSize: 9, fontWeight: 800, padding: "2px 6px", borderRadius: 4,
      background: s.bg, color: s.color, letterSpacing: "0.06em",
    }}>{s.label}</span>
  );
}

// ── Create Monitor Modal ───────────────────────────────────────────────────────

function CreateMonitorModal({ onClose, onCreate, T }) {
  const [form, setForm] = useState({
    name: "Production Loan Model",
    sensitive_col: "gender",
    target_col: "approved",
    baseline_raw: '{"M": 0.72, "F": 0.65}',
    dp_threshold: "0.10",
    psi_warning: "0.10",
    psi_critical: "0.25",
    audit_job_id: "",
  });
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  // ── Completed audit jobs, for the job picker dropdown ──────────────────
  const [jobs, setJobs] = useState([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [selectedJob, setSelectedJob] = useState(null); // full job object, or null = manual entry

  useEffect(() => {
    (async () => {
      const data = await listAuditJobs("done");
      if (Array.isArray(data?.jobs)) setJobs(data.jobs.filter(j => j.has_fairness));
      setJobsLoading(false);
    })();
  }, []);

  const field = (key, value) => setForm(f => ({ ...f, [key]: value }));

  const handleJobPick = (jobId) => {
    if (!jobId) {
      // "Manual entry" selected — clear auto-filled values, keep editable text inputs
      setSelectedJob(null);
      field("audit_job_id", "");
      return;
    }
    const job = jobs.find(j => j.job_id === jobId);
    setSelectedJob(job || null);
    setForm(f => ({
      ...f,
      audit_job_id:  jobId,
      target_col:    job?.target    || f.target_col,
      sensitive_col: job?.sensitive || f.sensitive_col,
    }));
  };

  const handleSubmit = async () => {
    setErr("");
    let baseline;
    try {
      baseline = JSON.parse(form.baseline_raw);
    } catch {
      if (!form.audit_job_id.trim()) {
        setErr("baseline_group_rates must be valid JSON, e.g. {\"M\": 0.72, \"F\": 0.65}");
        return;
      }
    }
    setLoading(true);
    const payload = {
      name: form.name,
      sensitive_col: form.sensitive_col,
      target_col: form.target_col,
      baseline_group_rates: baseline,
      dp_threshold: parseFloat(form.dp_threshold) || 0.1,
      psi_warning:  parseFloat(form.psi_warning)  || 0.1,
      psi_critical: parseFloat(form.psi_critical) || 0.25,
    };
    if (form.audit_job_id.trim()) payload.audit_job_id = form.audit_job_id.trim();
    const res = await createMonitor(payload);
    setLoading(false);
    if (res.error) { setErr(res.error); return; }
    onCreate(res.monitor_id);
  };

  const inputStyle = {
    background: T.surfaceHi, border: `1px solid ${T.border}`,
    borderRadius: 7, color: T.text, padding: "8px 12px",
    fontSize: 13, fontFamily: T.font, width: "100%", boxSizing: "border-box",
    outline: "none",
  };
  const labelStyle = { fontSize: 11, color: T.textDim, fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 4, display: "block" };

  const columnOptions = selectedJob?.columns?.length ? selectedJob.columns : null;

  return (
    <div style={{
      position: "fixed", inset: 0, background: "#000a",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200,
    }}>
      <div style={{
        background: T.surface, border: `1px solid ${T.border}`,
        borderRadius: 14, padding: 32, width: 480, maxWidth: "95vw",
        maxHeight: "90vh", overflowY: "auto",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, color: T.text }}>📡 New Monitor</div>
            <div style={{ fontSize: 12, color: T.textDim, marginTop: 3 }}>Set up drift monitoring for a deployed model</div>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: T.textDim }}>✕</button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label style={labelStyle}>Monitor name</label>
            <input style={inputStyle} value={form.name} onChange={e => field("name", e.target.value)} />
          </div>

          {/* Job picker — replaces manually pasting a job UUID */}
          <div>
            <label style={labelStyle}>Audit job (auto-fills baseline + columns)</label>
            <select
              style={inputStyle}
              value={form.audit_job_id}
              onChange={e => handleJobPick(e.target.value)}
            >
              <option value="">
                {jobsLoading ? "Loading completed audits…" : "— Manual entry (no audit job) —"}
              </option>
              {jobs.map(j => (
                <option key={j.job_id} value={j.job_id}>
                  {(j.dataset_name || j.job_id.slice(0, 8))}
                  {j.created_at ? `  ·  ${new Date(j.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}` : ""}
                  {`  ·  target=${j.target || "?"}  sensitive=${j.sensitive || "?"}`}
                </option>
              ))}
            </select>
            {!jobsLoading && jobs.length === 0 && (
              <div style={{ fontSize: 11, color: T.textDim, marginTop: 4 }}>
                No completed audits with fairness results found yet. Run an audit first, or fill in fields manually below.
              </div>
            )}
          </div>

          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Sensitive column</label>
              {columnOptions ? (
                <select style={inputStyle} value={form.sensitive_col} onChange={e => field("sensitive_col", e.target.value)}>
                  {!columnOptions.includes(form.sensitive_col) && <option value={form.sensitive_col}>{form.sensitive_col}</option>}
                  {columnOptions.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              ) : (
                <input style={inputStyle} value={form.sensitive_col} onChange={e => field("sensitive_col", e.target.value)} placeholder="e.g. gender" />
              )}
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Target column</label>
              {columnOptions ? (
                <select style={inputStyle} value={form.target_col} onChange={e => field("target_col", e.target.value)}>
                  {!columnOptions.includes(form.target_col) && <option value={form.target_col}>{form.target_col}</option>}
                  {columnOptions.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              ) : (
                <input style={inputStyle} value={form.target_col} onChange={e => field("target_col", e.target.value)} placeholder="e.g. approved" />
              )}
            </div>
          </div>

          {!selectedJob && (
            <div>
              <label style={labelStyle}>Baseline group rates (JSON)</label>
              <textarea
                rows={3} style={{ ...inputStyle, resize: "vertical" }}
                value={form.baseline_raw}
                onChange={e => field("baseline_raw", e.target.value)}
                placeholder='{"GroupA": 0.72, "GroupB": 0.65}'
              />
              <div style={{ fontSize: 11, color: T.textDim, marginTop: 4 }}>
                Positive prediction rate per group at baseline. Not needed if you pick an audit job above.
              </div>
            </div>
          )}

          {selectedJob && (
            <div style={{ fontSize: 12, color: T.textDim, background: T.surfaceHi, borderRadius: 7, padding: "8px 12px" }}>
              ✓ Baseline group rates will be auto-extracted from this audit's fairness results.
            </div>
          )}

          <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 14, marginTop: 4 }}>
            <div style={{ fontSize: 12, color: T.textDim, fontWeight: 700, marginBottom: 10 }}>Alert Thresholds</div>
            <div style={{ display: "flex", gap: 12 }}>
              {[
                { key: "dp_threshold", label: "DP gap" },
                { key: "psi_warning",  label: "PSI warning" },
                { key: "psi_critical", label: "PSI critical" },
              ].map(({ key, label }) => (
                <div key={key} style={{ flex: 1 }}>
                  <label style={labelStyle}>{label}</label>
                  <input type="number" step="0.01" min="0" max="1" style={inputStyle} value={form[key]} onChange={e => field(key, e.target.value)} />
                </div>
              ))}
            </div>
          </div>

          {err && <div style={{ color: T.red, fontSize: 12, padding: "8px 12px", background: T.redDim, borderRadius: 7 }}>{err}</div>}

          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 8 }}>
            <button onClick={onClose} style={{ background: T.surfaceHi, border: `1px solid ${T.border}`, borderRadius: 7, padding: "8px 18px", color: T.textDim, cursor: "pointer", fontSize: 13 }}>
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={loading}
              style={{ background: T.sky, border: "none", borderRadius: 7, padding: "8px 20px", color: "#000", cursor: loading ? "not-allowed" : "pointer", fontWeight: 700, fontSize: 13 }}
            >
              {loading ? "Creating…" : "Create Monitor"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Monitor Detail Panel ───────────────────────────────────────────────────────

function MonitorDetail({ monitorId, onBack, T }) {
  const [monitor, setMonitor] = useState(null);
  const [simulating, setSimulating] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [activeTab, setActiveTab] = useState("charts"); // "charts" | "alerts"
  const pollRef = useRef(null);
  const simRef  = useRef(null);

  const fetchStatus = useCallback(async () => {
    const data = await getMonitorStatus(monitorId, 100);
    if (!data.error) setMonitor(data);
  }, [monitorId]);

  useEffect(() => {
    fetchStatus();
    return () => { clearInterval(pollRef.current); clearInterval(simRef.current); };
  }, [fetchStatus]);

  useEffect(() => {
    clearInterval(pollRef.current);
    if (autoRefresh) {
      pollRef.current = setInterval(fetchStatus, 3000);
    }
    return () => clearInterval(pollRef.current);
  }, [autoRefresh, fetchStatus]);

  // ── Demo simulation ──────────────────────────────────────────────────────
  const toggleSimulation = () => {
    if (simulating) {
      clearInterval(simRef.current);
      setSimulating(false);
      return;
    }
    setSimulating(true);
    let tick = 0;
    const rand = seededRand(Date.now());
    simRef.current = setInterval(async () => {
      tick++;
      // After tick 5, start introducing drift
      const groups = monitor ? Object.keys(monitor.baseline_group_rates) : ["M", "F"];
      const rows = Array.from({ length: 30 }, (_, i) => {
        const group = groups[i % groups.length];
        const base = monitor?.baseline_group_rates?.[group] ?? 0.5;
        // Gradually introduce drift after tick 5
        const bias = tick > 5 ? (tick - 5) * 0.04 * (group === groups[0] ? 1 : -0.5) : 0;
        const rate = Math.min(0.99, Math.max(0.01, base + bias + (rand() - 0.5) * 0.1));
        return { sensitive: group, prediction: rand() < rate ? 1 : 0 };
      });
      await ingestBatch(monitorId, rows);
      if (tick >= 20) {
        clearInterval(simRef.current);
        setSimulating(false);
      }
    }, 1500);
  };

  // ── Build chart data ─────────────────────────────────────────────────────
  const buildChartData = (snapshots) => {
    return snapshots.map((snap, i) => {
      const point = { name: fmtTime(snap.timestamp), batch: snap.batch_size };
      Object.entries(snap.group_rates || {}).forEach(([g, r]) => {
        point[`rate_${g}`] = +(r * 100).toFixed(1);
      });
      Object.entries(snap.drift_scores || {}).forEach(([g, ds]) => {
        point[`psi_${g}`] = ds.psi;
      });
      point.dp_gap = +(snap.dp_gap * 100).toFixed(2);
      return point;
    });
  };

  const handlePauseResume = async () => {
    if (monitor.status === "active") await pauseMonitor(monitorId);
    else await resumeMonitor(monitorId);
    fetchStatus();
  };

  if (!monitor) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 200, color: T.textDim }}>
        Loading monitor…
      </div>
    );
  }

  const snapshots = monitor.snapshots || [];
  const alerts    = monitor.alerts    || [];
  const chartData = buildChartData(snapshots);
  const groups    = Object.keys(monitor.baseline_group_rates || {});
  const lastSnap  = snapshots[snapshots.length - 1];
  const critCount = alerts.filter(a => a.level === "critical").length;
  const warnCount = alerts.filter(a => a.level === "warning").length;
  const maxPsi    = lastSnap
    ? Math.max(...Object.values(lastSnap.drift_scores || {}).map(d => d.psi))
    : null;

  const tabStyle = (active) => ({
    padding: "7px 18px", borderRadius: 7, fontSize: 13, fontWeight: 600,
    cursor: "pointer", border: "none", fontFamily: T.font,
    background: active ? T.surfaceHi : "transparent",
    color: active ? T.text : T.textDim,
    borderBottom: active ? `2px solid ${T.sky}` : "2px solid transparent",
  });

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
        <button onClick={onBack} style={{ background: T.surfaceHi, border: `1px solid ${T.border}`, borderRadius: 7, padding: "6px 14px", color: T.textDim, cursor: "pointer", fontSize: 13 }}>
          ← Back
        </button>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 20, fontWeight: 800, color: T.text }}>{monitor.name}</span>
            <span style={{
              fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 5,
              background: monitor.status === "active" ? T.greenDim : T.amberDim,
              color: monitor.status === "active" ? T.green : T.amber,
              letterSpacing: "0.05em",
            }}>{monitor.status.toUpperCase()}</span>
          </div>
          <div style={{ fontSize: 12, color: T.textDim, marginTop: 3 }}>
            Sensitive: <b style={{ color: T.text }}>{monitor.sensitive_col}</b> &nbsp;·&nbsp;
            Target: <b style={{ color: T.text }}>{monitor.target_col}</b> &nbsp;·&nbsp;
            Created: {fmtDateTime(monitor.created_at)}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={toggleSimulation}
            style={{
              background: simulating ? T.amberDim : T.skyDim,
              border: `1px solid ${simulating ? T.amber : T.sky}`,
              borderRadius: 7, padding: "7px 16px",
              color: simulating ? T.amber : T.sky,
              cursor: "pointer", fontSize: 13, fontWeight: 700,
            }}
          >
            {simulating ? "⏹ Stop Demo" : "▶ Simulate Traffic"}
          </button>
          <button
            onClick={handlePauseResume}
            style={{
              background: T.surfaceHi, border: `1px solid ${T.border}`,
              borderRadius: 7, padding: "7px 14px", color: T.textDim,
              cursor: "pointer", fontSize: 13,
            }}
          >
            {monitor.status === "active" ? "⏸ Pause" : "▶ Resume"}
          </button>
          <button
            onClick={() => setAutoRefresh(r => !r)}
            style={{
              background: autoRefresh ? T.greenDim : T.surfaceHi,
              border: `1px solid ${autoRefresh ? T.green : T.border}`,
              borderRadius: 7, padding: "7px 14px",
              color: autoRefresh ? T.green : T.textDim,
              cursor: "pointer", fontSize: 13,
            }}
          >
            {autoRefresh ? "🔴 Live" : "⚪ Paused"}
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
        <StatCard T={T} label="Snapshots" value={monitor.total_snapshots} sub="batches ingested" />
        <StatCard T={T} label="Total Alerts" value={monitor.total_alerts}
          sub={`${critCount} critical · ${warnCount} warning`}
          color={critCount > 0 ? T.red : warnCount > 0 ? T.amber : T.green}
        />
        <StatCard T={T} label="Current DP Gap"
          value={lastSnap ? `${(lastSnap.dp_gap * 100).toFixed(1)}%` : "—"}
          sub={`threshold ${(monitor.thresholds.dp_threshold * 100).toFixed(0)}%`}
          color={lastSnap && lastSnap.dp_gap > monitor.thresholds.dp_threshold ? T.amber : T.green}
        />
        <StatCard T={T} label="Max PSI"
          value={maxPsi != null ? maxPsi.toFixed(3) : "—"}
          sub={maxPsi != null ? psiLabel(maxPsi).text : "—"}
          color={maxPsi != null ? psiLabel(maxPsi).color : T.textDim}
        />
        <StatCard T={T} label="Batch Size" value={lastSnap ? lastSnap.batch_size : "—"} sub="last batch" />
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20, borderBottom: `1px solid ${T.border}` }}>
        <button style={tabStyle(activeTab === "charts")} onClick={() => setActiveTab("charts")}>📈 Drift Charts</button>
        <button style={tabStyle(activeTab === "alerts")} onClick={() => setActiveTab("alerts")}>
          🔔 Alerts
          {monitor.total_alerts > 0 && (
            <span style={{ marginLeft: 6, fontSize: 9, fontWeight: 800, padding: "1px 5px", borderRadius: 4, background: T.redDim, color: T.red }}>
              {monitor.total_alerts}
            </span>
          )}
        </button>
      </div>

      {activeTab === "charts" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
          {chartData.length === 0 ? (
            <div style={{
              background: T.surface, border: `1px dashed ${T.border}`, borderRadius: 12,
              padding: 48, textAlign: "center", color: T.textDim,
            }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>📊</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: T.text, marginBottom: 8 }}>No data yet</div>
              <div style={{ fontSize: 13 }}>Click <b style={{ color: T.sky }}>▶ Simulate Traffic</b> to generate demo predictions, or ingest real batches via the API.</div>
            </div>
          ) : (
            <>
              {/* Selection Rate Over Time */}
              <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 12, padding: 24 }}>
                <div style={{ fontWeight: 700, color: T.text, marginBottom: 4 }}>Selection Rate by Group</div>
                <div style={{ fontSize: 12, color: T.textDim, marginBottom: 16 }}>
                  Positive prediction rate per group over ingested batches. Diverging lines → bias drift.
                </div>
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                    <CartesianGrid stroke={T.border} strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fill: T.textDim, fontSize: 11 }} interval="preserveStartEnd" />
                    <YAxis tick={{ fill: T.textDim, fontSize: 11 }} tickFormatter={v => `${v}%`} domain={[0, 100]} />
                    <Tooltip
                      contentStyle={{ background: T.surfaceHi, border: `1px solid ${T.border}`, borderRadius: 8 }}
                      labelStyle={{ color: T.text }}
                      formatter={(v, name) => [`${v}%`, name.replace("rate_", "")]}
                    />
                    <Legend formatter={v => v.replace("rate_", "")} />
                    {groups.map((g, i) => (
                      <Line key={g} type="monotone" dataKey={`rate_${g}`} name={`rate_${g}`}
                        stroke={GROUP_COLORS[i % GROUP_COLORS.length]} strokeWidth={2}
                        dot={false} activeDot={{ r: 4 }}
                      />
                    ))}
                    {/* Baseline reference lines */}
                    {groups.map((g, i) => {
                      const base = (monitor.baseline_group_rates[g] || 0) * 100;
                      return (
                        <ReferenceLine key={`ref_${g}`} y={base}
                          stroke={GROUP_COLORS[i % GROUP_COLORS.length]}
                          strokeDasharray="6 3" strokeOpacity={0.4}
                        />
                      );
                    })}
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* PSI Over Time */}
              <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 12, padding: 24 }}>
                <div style={{ fontWeight: 700, color: T.text, marginBottom: 4 }}>PSI (Population Stability Index)</div>
                <div style={{ fontSize: 12, color: T.textDim, marginBottom: 16 }}>
                  PSI &lt; 0.10 = stable &nbsp;·&nbsp; 0.10–0.25 = warning &nbsp;·&nbsp; &gt; 0.25 = critical drift
                </div>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                    <CartesianGrid stroke={T.border} strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fill: T.textDim, fontSize: 11 }} interval="preserveStartEnd" />
                    <YAxis tick={{ fill: T.textDim, fontSize: 11 }} domain={[0, "auto"]} />
                    <Tooltip
                      contentStyle={{ background: T.surfaceHi, border: `1px solid ${T.border}`, borderRadius: 8 }}
                      labelStyle={{ color: T.text }}
                      formatter={(v, name) => [v.toFixed(4), name.replace("psi_", "PSI ")]}
                    />
                    <Legend formatter={v => v.replace("psi_", "PSI ")} />
                    <ReferenceLine y={0.10} stroke={T.amber} strokeDasharray="4 2" label={{ value: "warn", fill: T.amber, fontSize: 10 }} />
                    <ReferenceLine y={0.25} stroke={T.red}   strokeDasharray="4 2" label={{ value: "crit", fill: T.red, fontSize: 10 }} />
                    {groups.map((g, i) => (
                      <Line key={g} type="monotone" dataKey={`psi_${g}`} name={`psi_${g}`}
                        stroke={GROUP_COLORS[i % GROUP_COLORS.length]} strokeWidth={2}
                        dot={false} activeDot={{ r: 4 }}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* DP Gap Over Time */}
              <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 12, padding: 24 }}>
                <div style={{ fontWeight: 700, color: T.text, marginBottom: 4 }}>Demographic-Parity Gap</div>
                <div style={{ fontSize: 12, color: T.textDim, marginBottom: 16 }}>
                  Max − min selection rate across groups. Threshold: {(monitor.thresholds.dp_threshold * 100).toFixed(0)}%.
                </div>
                <ResponsiveContainer width="100%" height={180}>
                  <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                    <CartesianGrid stroke={T.border} strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fill: T.textDim, fontSize: 11 }} interval="preserveStartEnd" />
                    <YAxis tick={{ fill: T.textDim, fontSize: 11 }} tickFormatter={v => `${v}%`} domain={[0, "auto"]} />
                    <Tooltip
                      contentStyle={{ background: T.surfaceHi, border: `1px solid ${T.border}`, borderRadius: 8 }}
                      labelStyle={{ color: T.text }}
                      formatter={(v) => [`${v.toFixed(2)}%`, "DP Gap"]}
                    />
                    <ReferenceLine y={monitor.thresholds.dp_threshold * 100} stroke={T.amber} strokeDasharray="4 2" label={{ value: "threshold", fill: T.amber, fontSize: 10 }} />
                    <Line type="monotone" dataKey="dp_gap" name="dp_gap"
                      stroke={T.violet} strokeWidth={2} dot={false} activeDot={{ r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </div>
      )}

      {activeTab === "alerts" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {alerts.length === 0 ? (
            <div style={{ textAlign: "center", padding: 48, color: T.textDim }}>
              <div style={{ fontSize: 32, marginBottom: 10 }}>✅</div>
              <div style={{ fontWeight: 700, color: T.text }}>No alerts fired yet</div>
              <div style={{ fontSize: 12, marginTop: 6 }}>Drift thresholds are holding. Simulate traffic to test alerting.</div>
            </div>
          ) : (
            [...alerts].reverse().map((alert, i) => (
              <div key={i} style={{
                background: T.surface, border: `1px solid ${alert.level === "critical" ? T.red + "44" : T.border}`,
                borderRadius: 8, padding: "12px 16px",
                display: "flex", alignItems: "flex-start", gap: 12,
              }}>
                <div style={{ paddingTop: 2 }}>
                  <AlertBadge level={alert.level} T={T} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: T.text }}>{alert.message}</div>
                  <div style={{ fontSize: 11, color: T.textDim, marginTop: 4 }}>{fmtDateTime(alert.timestamp)}</div>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Monitor List ───────────────────────────────────────────────────────────────

function MonitorList({ monitors, onSelect, onDelete, onRefresh, T }) {
  const [deleting, setDeleting] = useState(null);

  const handleDelete = async (id, e) => {
    e.stopPropagation();
    if (!window.confirm("Delete this monitor and all its data?")) return;
    setDeleting(id);
    await deleteMonitor(id);
    setDeleting(null);
    onRefresh();
  };

  if (monitors.length === 0) {
    return (
      <div style={{
        background: T.surface, border: `1px dashed ${T.border}`,
        borderRadius: 14, padding: 56, textAlign: "center",
      }}>
        <div style={{ fontSize: 40, marginBottom: 14 }}>📡</div>
        <div style={{ fontSize: 18, fontWeight: 800, color: T.text, marginBottom: 8 }}>No monitors yet</div>
        <div style={{ fontSize: 13, color: T.textDim, maxWidth: 380, margin: "0 auto" }}>
          Create a monitor to track fairness drift in your deployed models in real time.
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {monitors.map(mon => {
        const maxPsiInfo = mon.last_dp_gap != null ? psiLabel(mon.last_dp_gap) : null;
        return (
          <div
            key={mon.id}
            onClick={() => onSelect(mon.id)}
            style={{
              background: T.surface, border: `1px solid ${T.border}`,
              borderRadius: 12, padding: "16px 20px", cursor: "pointer",
              display: "flex", alignItems: "center", gap: 16,
              transition: "border-color .15s",
            }}
            onMouseEnter={e => e.currentTarget.style.borderColor = T.sky + "88"}
            onMouseLeave={e => e.currentTarget.style.borderColor = T.border}
          >
            <div style={{ fontSize: 28 }}>📡</div>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontWeight: 700, color: T.text, fontSize: 15 }}>{mon.name}</span>
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                  background: mon.status === "active" ? T.greenDim : T.amberDim,
                  color: mon.status === "active" ? T.green : T.amber,
                }}>{mon.status.toUpperCase()}</span>
              </div>
              <div style={{ fontSize: 12, color: T.textDim }}>
                Sensitive: <b style={{ color: T.text }}>{mon.sensitive_col}</b> &nbsp;·&nbsp;
                Target: <b style={{ color: T.text }}>{mon.target_col}</b> &nbsp;·&nbsp;
                {mon.total_snapshots} snapshots &nbsp;·&nbsp;
                {mon.total_alerts > 0
                  ? <span style={{ color: T.amber }}>{mon.total_alerts} alerts</span>
                  : <span style={{ color: T.green }}>0 alerts</span>
                }
                {mon.last_snapshot_at && <>&nbsp;·&nbsp; Last: {fmtDateTime(mon.last_snapshot_at)}</>}
              </div>
            </div>
            {mon.last_dp_gap != null && (
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 11, color: T.textDim, marginBottom: 2 }}>DP Gap</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: mon.last_dp_gap > 0.1 ? T.amber : T.green }}>
                  {(mon.last_dp_gap * 100).toFixed(1)}%
                </div>
              </div>
            )}
            <button
              onClick={(e) => handleDelete(mon.id, e)}
              disabled={deleting === mon.id}
              style={{
                background: T.redDim, border: `1px solid ${T.red}44`, borderRadius: 7,
                color: T.red, cursor: "pointer", fontSize: 12, padding: "6px 12px",
                fontWeight: 600,
              }}
            >
              {deleting === mon.id ? "…" : "Delete"}
            </button>
          </div>
        );
      })}
    </div>
  );
}

// ── Main MonitoringPage ────────────────────────────────────────────────────────

export default function MonitoringPage() {
  const { T } = useTheme();
  const [monitors,    setMonitors]    = useState([]);
  const [selectedId,  setSelectedId]  = useState(null);
  const [showCreate,  setShowCreate]  = useState(false);
  const [loading,     setLoading]     = useState(true);

  const fetchList = useCallback(async () => {
    const data = await listMonitors();
    if (Array.isArray(data)) setMonitors(data);
    setLoading(false);
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  const handleCreated = (monitorId) => {
    setShowCreate(false);
    fetchList();
    setSelectedId(monitorId);
  };

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "36px 24px", fontFamily: T.font }}>
      {/* Page header */}
      {!selectedId && (
        <>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 32, flexWrap: "wrap", gap: 16 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
                <div style={{
                  width: 40, height: 40, borderRadius: 10,
                  background: `linear-gradient(135deg, ${T.sky}, ${T.violet})`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 20,
                }}>📡</div>
                <h1 style={{ margin: 0, fontSize: 24, fontWeight: 900, color: T.text }}>
                  Real-Time Monitoring
                </h1>
                <span style={{
                  fontSize: 10, fontWeight: 800, padding: "3px 8px", borderRadius: 5,
                  background: T.skyDim, color: T.sky, letterSpacing: "0.06em",
                }}>LIVE</span>
              </div>
              <p style={{ margin: 0, fontSize: 14, color: T.textDim, maxWidth: 560 }}>
                Track fairness drift in your deployed models over time. Get alerted when prediction bias
                exceeds thresholds — before it becomes a compliance issue.
              </p>
            </div>
            <button
              onClick={() => setShowCreate(true)}
              style={{
                background: `linear-gradient(135deg, ${T.sky}, ${T.violet})`,
                border: "none", borderRadius: 9, padding: "10px 22px",
                color: "#fff", fontWeight: 800, fontSize: 14, cursor: "pointer",
                boxShadow: `0 4px 16px ${T.sky}44`,
              }}
            >
              + New Monitor
            </button>
          </div>

          {/* How it works banner */}
          <div style={{
            background: T.surface, border: `1px solid ${T.border}`,
            borderRadius: 12, padding: "16px 24px", marginBottom: 28,
            display: "flex", gap: 32, flexWrap: "wrap",
          }}>
            {[
              { icon: "1️⃣", title: "Create a Monitor", desc: "Define baseline fairness rates from an audit result or manual input." },
              { icon: "2️⃣", title: "Ingest Predictions", desc: "Push live prediction batches via /monitor/ingest API or use the demo." },
              { icon: "3️⃣", title: "Track Drift", desc: "PSI and DP-gap charts update in real time. Alerts fire on threshold breach." },
            ].map(({ icon, title, desc }) => (
              <div key={title} style={{ display: "flex", gap: 12, alignItems: "flex-start", flex: 1, minWidth: 200 }}>
                <span style={{ fontSize: 22 }}>{icon}</span>
                <div>
                  <div style={{ fontWeight: 700, color: T.text, fontSize: 13 }}>{title}</div>
                  <div style={{ fontSize: 12, color: T.textDim, marginTop: 3 }}>{desc}</div>
                </div>
              </div>
            ))}
          </div>

          {loading
            ? <div style={{ color: T.textDim, padding: 32, textAlign: "center" }}>Loading monitors…</div>
            : <MonitorList monitors={monitors} onSelect={setSelectedId} onDelete={fetchList} onRefresh={fetchList} T={T} />
          }
        </>
      )}

      {selectedId && (
        <MonitorDetail
          monitorId={selectedId}
          onBack={() => { setSelectedId(null); fetchList(); }}
          T={T}
        />
      )}

      {showCreate && (
        <CreateMonitorModal onClose={() => setShowCreate(false)} onCreate={handleCreated} T={T} />
      )}
    </div>
  );
}
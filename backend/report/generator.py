# backend/report/generator.py
# ─────────────────────────────────────────────────────────────────────────────
# Generates a self-contained HTML audit report from all module results.
# Each module section is rendered only if that module was selected.
# ─────────────────────────────────────────────────────────────────────────────

import os, json
from datetime import datetime

REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)


def _fmt(val, decimals=4):
    if val is None: return "N/A"
    if isinstance(val, float): return f"{val:.{decimals}f}"
    return str(val)


def _score_color(val):
    if val is None: return "#6b7280"
    try:
        v = float(val)
        if abs(v) < 0.1: return "#22c55e"
        if abs(v) < 0.2: return "#f59e0b"
        return "#ef4444"
    except: return "#6b7280"


def _render_fairness(data: dict) -> str:
    overall = data.get("overall", {})
    by_group = data.get("by_group", {})
    perf = data.get("performance", {})
    dq = data.get("data_quality", {})
    suggestions = data.get("suggestions", [])

    if data.get("status") == "placeholder" or "error" in data:
        msg = data.get("error") or data.get("message", "No data")
        return f'<div class="module-error">⚠ {msg}</div>'

    overall_rows = "".join(
        f'<tr><td>{k}</td><td style="color:{_score_color(v)};font-weight:700">{_fmt(v)}</td></tr>'
        for k, v in overall.items()
    )

    group_headers = set()
    for g_data in by_group.values():
        group_headers.update(g_data.keys())
    group_headers = sorted(group_headers)

    group_header_html = "".join(f"<th>{h}</th>" for h in group_headers)
    group_rows_html = "".join(
        f'<tr><td><strong>{grp}</strong></td>'
        + "".join(f'<td>{_fmt(g_data.get(h))}</td>' for h in group_headers)
        + "</tr>"
        for grp, g_data in by_group.items()
    )

    perf_rows = "".join(
        f'<tr><td>{k}</td><td style="color:#38bdf8;font-weight:700">{_fmt(v)}</td></tr>'
        for k, v in (perf or {}).items() if not isinstance(v, dict)
    )

    dq_html = ""
    if dq:
        dq_html = f"""
        <div class="subsection">
            <h4>Data Quality</h4>
            <div class="kv-grid">
                <div class="kv"><span>Rows</span><strong>{dq.get('num_rows','N/A')}</strong></div>
                <div class="kv"><span>Columns</span><strong>{dq.get('num_columns','N/A')}</strong></div>
                <div class="kv"><span>Duplicate rows</span><strong>{dq.get('duplicate_rows','N/A')}</strong></div>
                <div class="kv"><span>Missing columns</span><strong>{len(dq.get('missing_columns',{}))}</strong></div>
            </div>
        </div>"""

    sugg_html = ""
    if suggestions:
        items = "".join(f"<li>{s}</li>" for s in suggestions)
        sugg_html = f'<div class="subsection"><h4>Suggestions</h4><ul class="sugg-list">{items}</ul></div>'

    return f"""
    <div class="subsection">
        <h4>Overall Fairness Metrics</h4>
        <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{overall_rows}</tbody></table>
    </div>
    <div class="subsection">
        <h4>By Group</h4>
        <div style="overflow-x:auto">
        <table><thead><tr><th>Group</th>{group_header_html}</tr></thead><tbody>{group_rows_html}</tbody></table>
        </div>
    </div>
    <div class="subsection">
        <h4>Model Performance</h4>
        <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{perf_rows}</tbody></table>
    </div>
    {dq_html}
    {sugg_html}
    """


def _render_explainability(data: dict) -> str:
    if data.get("status") == "placeholder":
        pd_ = data.get("placeholder_data", {})
        return f"""
        <div class="placeholder-banner">
            🔧 {data.get('message','Placeholder')}
        </div>
        <div class="kv-grid">
            <div class="kv"><span>Rows analysed</span><strong>{pd_.get('num_rows','—')}</strong></div>
            <div class="kv"><span>Features</span><strong>{pd_.get('num_features','—')}</strong></div>
        </div>"""
    if "error" in data:
        return f'<div class="module-error">⚠ {data["error"]}</div>'

    mi   = data.get("model_info", {})
    shap = data.get("shap", {})
    lime = data.get("lime", {})
    agg  = data.get("aggregated", {})

    model_rows = "".join(
        f"<tr><td>{k}</td><td style='color:#c8cdd8;font-weight:600'>{v}</td></tr>"
        for k, v in [
            ("Model Class",       mi.get("model_class", "—")),
            ("Framework",         mi.get("framework", "—")),
            ("Task",              mi.get("task", "—")),
            ("Explainer Used",    mi.get("explainer_used", "—")),
            ("Feature Count",     len(shap.get("feature_names", []))),
            ("Samples Analysed",  shap.get("n_samples", "—")),
            ("Baseline Trained",  "Yes" if mi.get("baseline_trained") else "No"),
        ]
    )

    fi = shap.get("feature_importance", {})
    sorted_fi = sorted(fi.items(), key=lambda x: x[1], reverse=True)
    shap_rows = "".join(
        f"""<tr>
            <td>{rank}</td>
            <td>{feat}</td>
            <td style="color:#a78bfa;font-weight:700">{val:.5f}</td>
        </tr>"""
        for rank, (feat, val) in enumerate(sorted_fi, 1)
    )

    shap_charts = ""
    if shap.get("summary_plot_b64"):
        shap_charts += f'<div style="margin-bottom:16px"><h5 style="color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">SHAP Summary Plot (Beeswarm)</h5><img src="data:image/png;base64,{shap["summary_plot_b64"]}" style="max-width:100%;border-radius:6px;border:1px solid var(--border)"></div>'
    if shap.get("bar_plot_b64"):
        shap_charts += f'<div style="margin-bottom:16px"><h5 style="color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">SHAP Feature Importance Bar Chart</h5><img src="data:image/png;base64,{shap["bar_plot_b64"]}" style="max-width:100%;border-radius:6px;border:1px solid var(--border)"></div>'

    lime_pred_proba = lime.get("prediction_proba", {})
    proba_str = ""
    if lime_pred_proba and isinstance(lime_pred_proba, dict):
        proba_str = " &nbsp;·&nbsp; ".join(
            f"Class {k}: <strong style='color:#a78bfa'>{v:.3f}</strong>"
            for k, v in lime_pred_proba.items()
        )
    elif isinstance(lime_pred_proba, list):
        proba_str = " &nbsp;·&nbsp; ".join(
            f"Class {i}: <strong style='color:#a78bfa'>{v:.3f}</strong>"
            for i, v in enumerate(lime_pred_proba)
        )

    lime_contribs = lime.get("contributions", {})
    lime_rows = "".join(
        f"""<tr>
            <td style="font-family:monospace;font-size:12px">{feat}</td>
            <td style="color:{'#22c55e' if val >= 0 else '#ef4444'};font-weight:700;font-family:monospace">
                {'+' if val >= 0 else ''}{val:.5f}
            </td>
        </tr>"""
        for feat, val in sorted(lime_contribs.items(), key=lambda x: abs(x[1]), reverse=True)
    )

    lime_chart = ""
    if lime.get("lime_plot_b64"):
        lime_chart = f'<div style="margin-top:16px"><h5 style="color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">LIME Explanation Plot</h5><img src="data:image/png;base64,{lime["lime_plot_b64"]}" style="max-width:100%;border-radius:6px;border:1px solid var(--border)"></div>'

    consensus_feats = agg.get("consensus_top_features", [])
    consensus_list = "".join(f"<li style='margin-bottom:4px'>• {f}</li>" for f in consensus_feats)
    per_feat = agg.get("per_feature_table", [])
    merged_rows = "".join(
        f"""<tr>
            <td style="font-weight:600">{row.get('feature','')}</td>
            <td style="color:#a78bfa;font-family:monospace">{_fmt(row.get('shap_importance'))}</td>
            <td style="color:{'#22c55e' if (row.get('lime_contribution') or 0) >= 0 else '#ef4444'};font-family:monospace">
                {('+' if (row.get('lime_contribution') or 0) >= 0 else '')}{_fmt(row.get('lime_contribution'))}
            </td>
            <td style="color:#22c55e;font-weight:700">{'✓' if row.get('in_consensus') else ''}</td>
        </tr>"""
        for row in per_feat
    )

    agreement = agg.get("agreement_score")
    agreement_pct = f"{agreement*100:.1f}%" if agreement is not None else "—"
    agreement_color = "#22c55e" if (agreement or 0) >= 0.7 else "#f59e0b" if (agreement or 0) >= 0.4 else "#ef4444"

    return f"""
    <div class="subsection">
        <h4>Model Overview</h4>
        <table><thead><tr><th>Attribute</th><th>Value</th></tr></thead><tbody>{model_rows}</tbody></table>
    </div>

    <div class="subsection">
        <h4>SHAP Analysis (Global Explainability)</h4>
        <p style="color:var(--dim);font-size:12px;margin-bottom:12px">
            Explainer: <strong>{shap.get('explainer_type','—')}</strong> &nbsp;·&nbsp;
            Samples: <strong>{shap.get('n_samples','—')}</strong> &nbsp;·&nbsp;
            Features: <strong>{shap.get('n_features','—')}</strong>
        </p>
        <table>
            <thead><tr><th>Rank</th><th>Feature</th><th>Mean |SHAP|</th></tr></thead>
            <tbody>{shap_rows}</tbody>
        </table>
        <div style="margin-top:16px">{shap_charts}</div>
    </div>

    <div class="subsection">
        <h4>LIME Analysis (Local Explainability)</h4>
        <p style="color:var(--dim);font-size:12px;margin-bottom:4px">
            Mode: <strong>{lime.get('mode','—')}</strong> &nbsp;·&nbsp;
            Sample index: <strong>{lime.get('sample_index','0')}</strong> &nbsp;·&nbsp;
            Prediction: <strong>{lime.get('prediction','—')}</strong>
        </p>
        <p style="color:var(--dim);font-size:12px;margin-bottom:12px">
            Prediction probabilities: {proba_str}
        </p>
        <table>
            <thead><tr><th>Feature / Condition</th><th>LIME Weight</th></tr></thead>
            <tbody>{lime_rows}</tbody>
        </table>
        {lime_chart}
    </div>

    <div class="subsection">
        <h4>Explainability Aggregated View</h4>
        <div class="kv-grid" style="margin-bottom:14px">
            <div class="kv">
                <span>SHAP–LIME Agreement Score</span>
                <strong style="color:{agreement_color}">{agreement_pct}</strong>
            </div>
            <div class="kv">
                <span>Consensus Features</span>
                <strong style="color:#fff">{len(consensus_feats)}</strong>
            </div>
        </div>
        {"<div style='margin-bottom:14px'><div style='color:var(--dim);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px'>Consensus Features (in BOTH SHAP and LIME)</div><ul style='list-style:none;padding:0;color:#c8cdd8;font-size:13px'>" + consensus_list + "</ul></div>" if consensus_feats else ""}
        {"<table><thead><tr><th>Feature</th><th>SHAP Imp.</th><th>LIME Contrib.</th><th>Consensus</th></tr></thead><tbody>" + merged_rows + "</tbody></table>" if per_feat else ""}
    </div>
    """


def _render_compliance(data: dict) -> str:
    if data.get("status") == "placeholder":
        pd_ = data.get("placeholder_data", {})
        cols = ", ".join(pd_.get("text_columns", [])) or "none detected"
        return f"""
        <div class="placeholder-banner">
            🔧 {data.get('message','Placeholder')}
        </div>
        <div class="kv-grid">
            <div class="kv"><span>Rows scanned</span><strong>{pd_.get('num_rows','—')}</strong></div>
            <div class="kv"><span>Text columns</span><strong>{cols}</strong></div>
        </div>"""
    if "error" in data:
        return f'<div class="module-error">⚠ {data["error"]}</div>'

    stats        = data.get("stats", {})
    summary      = data.get("summary", {})
    findings     = data.get("findings", [])
    col_report   = data.get("column_report", [])
    overall      = data.get("overall_status", "—")
    engine       = data.get("engine", "—")

    overall_color = "#22c55e" if overall == "compliant" else "#ef4444"

    stats_html = f"""
    <div class="kv-grid" style="margin-bottom:18px">
        <div class="kv"><span>Overall Status</span><strong style="color:{overall_color}">{overall.upper()}</strong></div>
        <div class="kv"><span>Total Columns</span><strong>{stats.get('total_columns','—')}</strong></div>
        <div class="kv"><span>PII Columns</span><strong style="color:#f59e0b">{stats.get('pii_columns', 0)}</strong></div>
        <div class="kv"><span>Regulations Failed</span><strong style="color:{'#ef4444' if stats.get('regulations_failed',0) > 0 else '#22c55e'}">{stats.get('regulations_failed', 0)}</strong></div>
        <div class="kv"><span>Detection Engine</span><strong style="color:#38bdf8">{engine}</strong></div>
    </div>"""

    reg_rows = "".join(
        f"""<tr>
            <td style="font-weight:600">{reg}</td>
            <td style="color:{'#22c55e' if status=='compliant' else '#ef4444'};font-weight:700">
                {'✓ Compliant' if status=='compliant' else '✗ ' + status.replace('_',' ').title()}
            </td>
        </tr>"""
        for reg, status in summary.items()
    )

    col_rows = "".join(
        f"""<tr>
            <td style="font-family:monospace;font-weight:600">{c.get('name','')}</td>
            <td>{', '.join(c.get('pii_entities', [])) or '—'}</td>
            <td style="color:{'#ef4444' if c.get('severity') in ('critical','high') else '#f59e0b' if c.get('severity')=='medium' else '#22c55e'};font-weight:700">
                {(c.get('severity') or '—').upper()}
            </td>
            <td style="font-size:11px;color:var(--dim)">{', '.join(c.get('regulations', [])) or '—'}</td>
        </tr>"""
        for c in col_report
    )

    findings_html = ""
    if findings:
        f_rows = "".join(
            f"""<tr>
                <td style="font-weight:600;font-size:12px">{f.get('regulation','')}</td>
                <td style="font-family:monospace;font-size:11px">{f.get('rule_id','')}</td>
                <td style="font-size:12px">{f.get('rule_description','')}</td>
                <td style="color:{'#ef4444' if f.get('status')=='non_compliant' else '#22c55e'};font-weight:700;font-size:11px">
                    {f.get('status','').replace('_',' ').title()}
                </td>
            </tr>"""
            for f in findings[:15]
        )
        findings_html = f"""
        <div class="subsection">
            <h4>Findings ({len(findings)} total)</h4>
            <div style="overflow-x:auto">
            <table>
                <thead><tr><th>Regulation</th><th>Rule ID</th><th>Description</th><th>Status</th></tr></thead>
                <tbody>{f_rows}</tbody>
            </table>
            </div>
        </div>"""

    return f"""
    <div class="subsection">
        <h4>Scan Overview</h4>
        {stats_html}
    </div>
    <div class="subsection">
        <h4>Regulation Summary</h4>
        <table><thead><tr><th>Regulation</th><th>Status</th></tr></thead>
        <tbody>{reg_rows}</tbody></table>
    </div>
    {"<div class='subsection'><h4>PII Columns Detected</h4><div style='overflow-x:auto'><table><thead><tr><th>Column</th><th>PII Entities</th><th>Severity</th><th>Regulations</th></tr></thead><tbody>" + col_rows + "</tbody></table></div></div>" if col_report else ""}
    {findings_html}
    """


def _render_energy(data: dict) -> str:
    if data.get("status") == "placeholder":
        return f"""
        <div class="placeholder-banner">
            🔧 {data.get('message','Placeholder')}
        </div>"""
    if "error" in data:
        return f'<div class="module-error">⚠ {data["error"]}</div>'

    sys_info  = data.get("system_info", {})
    recs      = data.get("recommendations", [])
    per_epoch = data.get("energy_per_epoch", [])

    energy_kwh = data.get("energy_kwh") or 0
    carbon_kg  = data.get("carbon_kg") or 0

    epoch_rows = "".join(
        f"<tr><td>Epoch {i+1}</td><td style='color:#38bdf8;font-family:monospace'>{v*1000:.6f} Wh</td></tr>"
        for i, v in enumerate(per_epoch)
    )
    epoch_table = f"""
    <div class="subsection">
        <h4>Energy per Epoch</h4>
        <table><thead><tr><th>Epoch</th><th>Energy (Wh)</th></tr></thead>
        <tbody>{epoch_rows}</tbody></table>
    </div>""" if epoch_rows else ""

    rec_html = ""
    if recs:
        items = "".join(f"<li>{r}</li>" for r in recs)
        rec_html = f'<div class="subsection"><h4>Recommendations</h4><ul class="sugg-list">{items}</ul></div>'

    return f"""
    <div class="subsection">
        <h4>Energy & Emissions Summary</h4>
        <div class="kv-grid">
            <div class="kv"><span>Total Energy (kWh)</span><strong style="color:#38bdf8">{_fmt(energy_kwh, 6)}</strong></div>
            <div class="kv"><span>Total Energy (Wh)</span><strong style="color:#38bdf8">{_fmt(energy_kwh * 1000, 4)}</strong></div>
            <div class="kv"><span>Carbon Emitted (kg CO₂)</span><strong style="color:#22c55e">{_fmt(carbon_kg, 6)}</strong></div>
            <div class="kv"><span>Carbon Emitted (g CO₂)</span><strong style="color:#22c55e">{_fmt(carbon_kg * 1000, 4)}</strong></div>
            <div class="kv"><span>Epochs</span><strong style="color:#f59e0b">{data.get('epochs','—')}</strong></div>
            <div class="kv"><span>Mode</span><strong style="color:#c8cdd8">{data.get('file_type','—').replace('_',' ').title()}</strong></div>
            <div class="kv"><span>Model</span><strong style="color:#c8cdd8">{data.get('model','—')}</strong></div>
            <div class="kv"><span>Num Samples</span><strong>{data.get('num_samples','—')}</strong></div>
            <div class="kv"><span>Num Features</span><strong>{data.get('num_features','—')}</strong></div>
        </div>
    </div>
    <div class="subsection">
        <h4>System Information</h4>
        <table>
            <thead><tr><th>Property</th><th>Value</th></tr></thead>
            <tbody>
                <tr><td>Platform</td><td style="font-family:monospace;font-size:12px">{sys_info.get('platform','—')}</td></tr>
                <tr><td>Python Version</td><td style="font-family:monospace">{sys_info.get('python_version','—')}</td></tr>
                <tr><td>CPU Count</td><td>{sys_info.get('cpu_count','—')}</td></tr>
            </tbody>
        </table>
    </div>
    {epoch_table}
    {rec_html}
    """


# ── Trust Score renderer ───────────────────────────────────────────────────────

def _render_trust_score(trust_score: dict) -> tuple:
    """
    Returns (trust_section_html, trust_chip_html).
    Both are empty strings if trust_score is None or score is None.
    """
    if not trust_score or trust_score.get("score") is None:
        return "", ""

    score      = trust_score["score"]
    risk_level = trust_score.get("risk_level", "Unknown")
    risk_color = trust_score.get("risk_color", "textDim")
    breakdown  = trust_score.get("breakdown", {})
    weights    = trust_score.get("weights_used", {})
    summary    = trust_score.get("summary", "")
    missing    = trust_score.get("missing", [])

    color_map  = {"green": "#22c55e", "amber": "#f59e0b", "red": "#ef4444", "textDim": "#6b7280"}
    color      = color_map.get(risk_color, "#6b7280")

    # SVG ring
    r        = 43
    circ     = 2 * 3.14159 * r
    filled   = circ * (score / 100)
    ring_svg = f"""
    <svg width="96" height="96" style="transform:rotate(-90deg);flex-shrink:0">
      <circle cx="48" cy="48" r="{r}" fill="none" stroke="{color}22" stroke-width="8"/>
      <circle cx="48" cy="48" r="{r}" fill="none" stroke="{color}" stroke-width="8"
        stroke-dasharray="{filled:.1f} {circ:.1f}" stroke-linecap="round"/>
    </svg>"""

    # Breakdown bars
    bar_rows = ""
    for mod, val in breakdown.items():
        bc  = "#22c55e" if val >= 75 else "#f59e0b" if val >= 50 else "#ef4444"
        wt  = weights.get(mod)
        wt_label = f" ({wt*100:.0f}%)" if wt is not None else ""
        bar_rows += f"""
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
          <div style="width:110px;font-size:12px;color:#c8cdd8;text-transform:capitalize;flex-shrink:0">
            {mod}{wt_label}
          </div>
          <div style="flex:1;height:6px;background:#1c2030;border-radius:3px;overflow:hidden">
            <div style="height:100%;width:{val:.1f}%;background:{bc};border-radius:3px"></div>
          </div>
          <div style="width:44px;text-align:right;font-size:12px;font-weight:700;color:{bc};flex-shrink:0">
            {val:.1f}
          </div>
        </div>"""

    missing_note = ""
    if missing:
        missing_note = f'<p style="color:#6b7280;font-size:11px;margin-top:10px">⚠ Not included (no data): {", ".join(missing)}</p>'

    badge_bg_map = {"green": "#22c55e22", "amber": "#f59e0b22", "red": "#ef444422", "textDim": "#1c2030"}
    badge_bg     = badge_bg_map.get(risk_color, "#1c2030")

    section = f"""
    <section class="module-card" style="border-top:3px solid {color};margin-bottom:24px">
      <div class="module-header">
        <div>
          <h3>🛡 AI Trust Score</h3>
          <p class="module-desc">Composite responsible-AI score weighted across all audited dimensions.</p>
        </div>
        <span style="background:{badge_bg};color:{color};border:1px solid {color}44;
              border-radius:20px;padding:4px 14px;font-size:12px;font-weight:800;white-space:nowrap">
          {risk_level}
        </span>
      </div>
      <div class="module-body">
        <div style="display:flex;align-items:center;gap:28px;margin-bottom:22px;flex-wrap:wrap">
          <div style="position:relative;width:96px;height:96px;flex-shrink:0">
            {ring_svg}
            <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center">
              <span style="font-size:22px;font-weight:900;color:{color};line-height:1">{score:.1f}</span>
              <span style="font-size:10px;color:#6b7280">/ 100</span>
            </div>
          </div>
          <div style="flex:1;min-width:200px">
            <div style="height:8px;background:#1c2030;border-radius:4px;overflow:hidden;margin-bottom:10px">
              <div style="height:100%;width:{min(score,100):.1f}%;background:linear-gradient(90deg,{color}99,{color});border-radius:4px"></div>
            </div>
            <p style="color:#c8cdd8;font-size:13px;line-height:1.6">{summary}</p>
          </div>
        </div>
        <div class="subsection">
          <h4>Score Breakdown by Module</h4>
          {bar_rows}
          {missing_note}
        </div>
      </div>
    </section>"""

    chip = f'<div class="summary-chip"><span>Trust Score</span><strong style="color:{color}">{score:.1f}</strong></div>'

    return section, chip


MODULE_RENDERERS = {
    "fairness":       ("⚖ Fairness",        "#f59e0b", _render_fairness),
    "explainability": ("🔍 Explainability",  "#a78bfa", _render_explainability),
    "compliance":     ("🛡 Compliance",       "#22c55e", _render_compliance),
    "energy":         ("⚡ Energy Efficiency","#38bdf8", _render_energy),
}

MODULE_DESCRIPTIONS = {
    "fairness":       "Fairlearn-based analysis of demographic parity, equalized odds, and group-level fairness metrics.",
    "explainability": "SHAP and LIME explanations showing which features drive model predictions.",
    "compliance":     "Microsoft Presidio scan for personally identifiable information (PII) in the dataset.",
    "energy":         "CodeCarbon tracking of CO₂ emissions and energy consumption during model execution.",
}


def generate_unified_report(job_id: str, module_results: dict, modules: list,
                             trust_score: dict = None) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Trust score ────────────────────────────────────────────────────────────
    trust_section_html, trust_chip_html = _render_trust_score(trust_score)

    # ── Module sections ────────────────────────────────────────────────────────
    sections_html = ""
    for module_name in modules:
        data = module_results.get(module_name, {"error": "No result returned"})
        label, accent, renderer = MODULE_RENDERERS.get(
            module_name,
            (module_name.title(), "#6b7280", lambda d: str(d))
        )
        desc = MODULE_DESCRIPTIONS.get(module_name, "")
        body = renderer(data)
        status = data.get("status", "done")
        status_badge = (
            '<span class="badge-ok">✓ Complete</span>'    if status in ("ok", "done") else
            '<span class="badge-warn">⚠ Placeholder</span>' if status == "placeholder" else
            '<span class="badge-err">✗ Error</span>'
        )
        sections_html += f"""
        <section class="module-card" style="border-top: 3px solid {accent}">
            <div class="module-header">
                <div>
                    <h3>{label}</h3>
                    <p class="module-desc">{desc}</p>
                </div>
                {status_badge}
            </div>
            <div class="module-body">{body}</div>
        </section>"""

    # ── Summary counts ─────────────────────────────────────────────────────────
    n_ok    = sum(1 for m in modules if module_results.get(m, {}).get("status") in ("ok", "done"))
    n_ph    = sum(1 for m in modules if module_results.get(m, {}).get("status") == "placeholder")
    n_err   = sum(1 for m in modules if "error" in module_results.get(m, {}))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EcoPulse AI Audit Report — {job_id[:8]}</title>
<style>
  :root {{
    --bg: #0c0e12; --surface: #141821; --surface2: #1c2030;
    --border: #2a2f3d; --text: #c8cdd8; --dim: #6b7280;
    --amber: #f59e0b; --green: #22c55e; --red: #ef4444;
    --sky: #38bdf8; --violet: #a78bfa;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; font-size: 14px; line-height: 1.6; }}
  .header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 24px 40px; }}
  .header h1 {{ font-size: 22px; font-weight: 800; color: #fff; letter-spacing: -0.02em; }}
  .header h1 span {{ color: var(--amber); }}
  .meta {{ color: var(--dim); font-size: 12px; margin-top: 6px; }}
  .container {{ max-width: 960px; margin: 0 auto; padding: 32px 24px; }}
  .summary-bar {{ display: flex; gap: 12px; margin-bottom: 28px; flex-wrap: wrap; }}
  .summary-chip {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 10px 16px; font-size: 12px; }}
  .summary-chip strong {{ display: block; font-size: 18px; font-weight: 800; color: #fff; }}
  .module-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 24px; overflow: hidden; }}
  .module-header {{ display: flex; justify-content: space-between; align-items: flex-start; padding: 18px 22px 14px; border-bottom: 1px solid var(--border); }}
  .module-header h3 {{ font-size: 16px; font-weight: 700; color: #fff; }}
  .module-desc {{ color: var(--dim); font-size: 12px; margin-top: 3px; max-width: 560px; }}
  .module-body {{ padding: 18px 22px; }}
  .subsection {{ margin-bottom: 20px; }}
  .subsection h4 {{ font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--dim); margin-bottom: 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); text-align: left; }}
  th {{ color: var(--dim); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }}
  .kv-grid {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .kv {{ background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; min-width: 140px; }}
  .kv span {{ display: block; color: var(--dim); font-size: 11px; margin-bottom: 2px; }}
  .kv strong {{ font-size: 16px; color: #fff; }}
  .sugg-list {{ padding-left: 18px; color: var(--text); }}
  .sugg-list li {{ margin-bottom: 6px; font-size: 13px; }}
  .placeholder-banner {{ background: #1c1e10; border: 1px solid #3d3d10; color: #a3a320; border-radius: 6px; padding: 12px 16px; font-size: 13px; margin-bottom: 14px; }}
  .module-error {{ background: #1c1010; border: 1px solid #3d1010; color: var(--red); border-radius: 6px; padding: 12px 16px; font-size: 13px; }}
  .badge-ok   {{ background: #22c55e22; color: var(--green);  border: 1px solid #22c55e44; border-radius: 20px; padding: 3px 10px; font-size: 11px; font-weight: 700; white-space: nowrap; }}
  .badge-warn {{ background: #f59e0b22; color: var(--amber);  border: 1px solid #f59e0b44; border-radius: 20px; padding: 3px 10px; font-size: 11px; font-weight: 700; white-space: nowrap; }}
  .badge-err  {{ background: #ef444422; color: var(--red);    border: 1px solid #ef444444; border-radius: 20px; padding: 3px 10px; font-size: 11px; font-weight: 700; white-space: nowrap; }}
  .footer {{ text-align: center; color: var(--dim); font-size: 11px; padding: 32px 0 48px; border-top: 1px solid var(--border); margin-top: 8px; }}
</style>
</head>
<body>
<div class="header">
  <h1>EcoPulse <span>AI Audit Suite</span> — Unified Audit Report</h1>
  <div class="meta">
    Job ID: {job_id} &nbsp;·&nbsp; Generated: {timestamp} &nbsp;·&nbsp;
    Modules: {', '.join(modules)}
  </div>
</div>

<div class="container">
  <div class="summary-bar">
    <div class="summary-chip"><span>Modules run</span><strong>{len(modules)}</strong></div>
    <div class="summary-chip"><span>Complete</span><strong style="color:var(--green)">{n_ok}</strong></div>
    <div class="summary-chip"><span>Placeholder</span><strong style="color:var(--amber)">{n_ph}</strong></div>
    <div class="summary-chip"><span>Errors</span><strong style="color:var(--red)">{n_err}</strong></div>
    {trust_chip_html}
  </div>

  {trust_section_html}

  {sections_html}
</div>

<div class="footer">
  EcoPulse AI Audit Suite &nbsp;·&nbsp; {timestamp}
</div>
</body>
</html>"""

    path = os.path.join(REPORT_DIR, f"report_{job_id}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
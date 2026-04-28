// frontend/src/pages/GlossaryPage.jsx
import React, { useState } from "react";
import { useTheme } from "../theme";

const GLOSSARY = [
  // ── Fairness ──────────────────────────────────────────────────────────────
  {
    term: "Demographic Parity",
    module: "fairness",
    short: "Equal selection rates across groups.",
    detail: "A model satisfies demographic parity when the probability of a positive prediction is the same for all values of the sensitive attribute. Also called statistical parity. Example: a hiring model should accept candidates at the same rate regardless of gender.",
  },
  {
    term: "Demographic Parity Difference",
    module: "fairness",
    short: "Max − min selection rate across groups.",
    detail: "Numerically measures how far a model is from demographic parity. A value of 0 means perfect parity. Values below 0.1 are generally considered acceptable. Computed as: max(P(ŷ=1 | A=a)) − min(P(ŷ=1 | A=a)) over all groups a.",
  },
  {
    term: "Equalized Odds",
    module: "fairness",
    short: "Equal TPR and FPR across groups.",
    detail: "A model satisfies equalized odds when both the true positive rate (TPR) and false positive rate (FPR) are equal across all groups. Stronger than demographic parity — it conditions on the true label. Requires equal accuracy for both positive and negative cases.",
  },
  {
    term: "Equalized Odds Difference",
    module: "fairness",
    short: "Max difference in TPR/FPR across groups.",
    detail: "Measures the worst-case violation of equalized odds. Computed as: max(|TPR_a − TPR_b|, |FPR_a − FPR_b|) over all group pairs. A value of 0 means equalized odds holds perfectly.",
  },
  {
    term: "Selection Rate",
    module: "fairness",
    short: "Fraction of positive predictions for a group.",
    detail: "The proportion of individuals in a group who receive a positive model prediction. For example, in a loan application scenario, the selection rate for females is the fraction of female applicants predicted as creditworthy. Comparing selection rates across groups reveals demographic parity violations.",
  },
  {
    term: "True Positive Rate (TPR) / Recall / Sensitivity",
    module: "fairness",
    short: "Fraction of actual positives correctly predicted.",
    detail: "TPR = TP / (TP + FN). Measures how many of the truly positive cases the model correctly identifies. In fairness, comparing TPR across groups checks whether the model is equally good at identifying positive cases for all groups.",
  },
  {
    term: "False Positive Rate (FPR)",
    module: "fairness",
    short: "Fraction of actual negatives incorrectly predicted as positive.",
    detail: "FPR = FP / (FP + TN). In fairness, a higher FPR for one group means that group is more often incorrectly flagged. For example, in recidivism prediction, a higher FPR for a minority group means they are more often incorrectly predicted to reoffend.",
  },
  {
    term: "False Negative Rate (FNR)",
    module: "fairness",
    short: "Fraction of actual positives missed by the model.",
    detail: "FNR = FN / (FN + TP) = 1 − TPR. In fairness, higher FNR for a group means the model more often fails to identify positive cases in that group. For example, in medical screening, a higher FNR for women means the model misses more true disease cases in women.",
  },
  {
    term: "Sensitive Attribute",
    module: "fairness",
    short: "A protected characteristic like race, gender, or age.",
    detail: "A feature of a person that should not unjustifiably influence model predictions. Examples: race, gender, age, religion, disability status. Fairness analysis measures whether the model's predictions differ across groups defined by this attribute.",
  },
  {
    term: "ExponentiatedGradient",
    module: "fairness",
    short: "Fairlearn's mitigation algorithm.",
    detail: "A fairness mitigation technique from Fairlearn that reframes constrained fair classification as a sequence of cost-sensitive learning problems. It trains an ensemble of classifiers with varying costs and selects the best randomised combination that satisfies the fairness constraint while minimising loss.",
  },
  {
    term: "Mitigation",
    module: "fairness",
    short: "Reducing bias in a model's predictions.",
    detail: "Post-processing or in-processing techniques that modify a model or its outputs to reduce fairness violations. FairCheck supports ExponentiatedGradient (in-processing) for baseline models and threshold-based post-processing for user-uploaded models.",
  },
  // ── Explainability ─────────────────────────────────────────────────────────
  {
    term: "SHAP (SHapley Additive exPlanations)",
    module: "explainability",
    short: "Game-theoretic feature importance values.",
    detail: "SHAP assigns each feature a contribution value for a specific prediction, based on Shapley values from cooperative game theory. A positive SHAP value means the feature pushed the prediction higher; a negative value means it pushed it lower. SHAP values are consistent and locally accurate.",
  },
  {
    term: "LIME (Local Interpretable Model-agnostic Explanations)",
    module: "explainability",
    short: "Locally faithful surrogate model explanations.",
    detail: "LIME explains individual predictions by fitting a simple interpretable model (e.g. linear) around a single data point. It perturbs the input, observes how predictions change, and fits the surrogate model to approximate the black-box model locally.",
  },
  {
    term: "Feature Importance",
    module: "explainability",
    short: "How much each feature contributes to predictions.",
    detail: "A ranking of input features by how strongly they influence model predictions, globally across the dataset. Unlike SHAP (per-instance), global feature importance summarises across all predictions — e.g. permutation importance or mean |SHAP| values.",
  },
  {
    term: "Model Agnostic",
    module: "explainability",
    short: "Works with any ML model.",
    detail: "An explanation method is model-agnostic if it treats the model as a black box and can be applied regardless of the underlying algorithm (decision tree, neural network, SVM, etc.). LIME and SHAP TreeExplainer/KernelExplainer are both model-agnostic approaches.",
  },
  // ── Compliance ─────────────────────────────────────────────────────────────
  {
    term: "PII (Personally Identifiable Information)",
    module: "compliance",
    short: "Data that can identify a specific individual.",
    detail: "Any information that can be used to distinguish or trace an individual's identity. Examples: full names, email addresses, phone numbers, Social Security numbers, IP addresses, date of birth combined with location. GDPR, CCPA, and HIPAA all regulate PII handling.",
  },
  {
    term: "Presidio",
    module: "compliance",
    short: "Microsoft's open-source PII detection library.",
    detail: "Microsoft Presidio is a data protection SDK that detects and anonymises PII in text and structured data. It uses named entity recognition (NER) and pattern matching to identify entities like PERSON, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, US_SSN, and more.",
  },
  {
    term: "Anonymisation",
    module: "compliance",
    short: "Removing or masking PII from data.",
    detail: "The process of transforming data so that individuals cannot be identified. Techniques include redaction (removing the value), replacement (substituting a fake value), hashing, and generalisation. Presidio's AnonymizerEngine can apply these transformations after detection.",
  },
  {
    term: "GDPR",
    module: "compliance",
    short: "EU data protection regulation.",
    detail: "The General Data Protection Regulation (EU 2016/679) governs how organisations collect, store, and process personal data of EU citizens. It requires lawful basis for processing, data minimisation, and grants individuals rights to access, rectify, and erase their data.",
  },
  // ── Energy ─────────────────────────────────────────────────────────────────
  {
    term: "CodeCarbon",
    module: "energy",
    short: "Python library for tracking ML carbon emissions.",
    detail: "CodeCarbon tracks the CO₂ equivalent emissions produced by running Python code. It estimates energy consumption based on CPU/GPU/RAM usage, multiplied by the carbon intensity of the local power grid (gCO₂/kWh). Supports experiment tracking with CSV and cloud logging.",
  },
  {
    term: "Carbon Intensity",
    module: "energy",
    short: "CO₂ emitted per unit of electricity (gCO₂/kWh).",
    detail: "A measure of how 'clean' the electricity grid is. A grid powered mostly by renewables has low carbon intensity; one relying on coal has high intensity. The same computation run in Iceland (geothermal) emits far less CO₂ than one run in a coal-heavy region.",
  },
  {
    term: "CO₂ Equivalent (CO₂eq)",
    module: "energy",
    short: "Unified measure of greenhouse gas impact.",
    detail: "A standard unit for comparing the climate impact of different greenhouse gases. Methane and nitrous oxide have higher warming potential than CO₂ — CO₂eq converts them all to a single comparable number. CodeCarbon reports emissions in kilograms of CO₂eq.",
  },
  {
    term: "Energy Efficiency (ML)",
    module: "energy",
    short: "Minimising compute resources per unit of model quality.",
    detail: "In ML, energy efficiency means achieving a target model performance with the least computation — fewer training steps, smaller architectures, efficient hardware. Reporting emissions alongside model accuracy (the 'accuracy-emissions tradeoff') is a growing best practice in responsible AI.",
  },
];

const GlossaryPage = () => {
  const { T } = useTheme();

  const MODULE_COLORS = {
    fairness:       { color: T.amber,  dim: T.amberDim,  label: "Fairness"        },
    explainability: { color: T.violet, dim: T.violetDim, label: "Explainability"  },
    compliance:     { color: T.green,  dim: T.greenDim,  label: "Compliance"      },
    energy:         { color: T.sky,    dim: T.skyDim,    label: "Energy"          },
  };

  const [search,    setSearch]    = useState("");
  const [activeTag, setActiveTag] = useState("all");
  const [expanded,  setExpanded]  = useState(null);

  const filtered = GLOSSARY.filter(entry => {
    const matchTag    = activeTag === "all" || entry.module === activeTag;
    const searchLower = search.toLowerCase();
    const matchSearch = !search ||
      entry.term.toLowerCase().includes(searchLower) ||
      entry.short.toLowerCase().includes(searchLower) ||
      entry.detail.toLowerCase().includes(searchLower);
    return matchTag && matchSearch;
  });

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: "40px 24px", fontFamily: T.font }}>

      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ color: "#fff", fontSize: 26, fontWeight: 900, letterSpacing: "-0.03em", marginBottom: 8 }}>
          Glossary
        </h1>
        <p style={{ color: T.textDim, fontSize: 14, lineHeight: 1.7, maxWidth: 560 }}>
          Definitions for key terms used across all audit modules.
          Click any term to expand its full explanation.
        </p>
      </div>

      {/* Search + filter */}
      <div style={{ display: "flex", gap: 12, marginBottom: 28, flexWrap: "wrap", alignItems: "center" }}>
        <input
          type="text"
          placeholder="Search terms…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            flex: 1, minWidth: 200, padding: "9px 14px",
            background: T.surfaceHi, border: `1px solid ${T.border}`,
            borderRadius: 8, color: T.text, fontFamily: T.font, fontSize: 13,
            outline: "none",
          }}
        />
        <div style={{ display: "flex", gap: 6 }}>
          {["all", "fairness", "explainability", "compliance", "energy"].map(tag => {
            const meta = tag === "all" ? { color: T.textDim, dim: T.surfaceHi, label: "All" } : MODULE_COLORS[tag];
            const active = activeTag === tag;
            return (
              <button
                key={tag}
                onClick={() => setActiveTag(tag)}
                style={{
                  padding: "6px 12px", borderRadius: 20, fontSize: 12, fontWeight: 700,
                  cursor: "pointer", fontFamily: T.font,
                  background: active ? meta.dim : "transparent",
                  color:      active ? meta.color : T.textDim,
                  border:     `1px solid ${active ? meta.color + "55" : T.border}`,
                  transition: "all .15s",
                }}
              >
                {meta.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Count */}
      <div style={{ color: T.textDim, fontSize: 12, marginBottom: 16 }}>
        {filtered.length} term{filtered.length !== 1 ? "s" : ""}
      </div>

      {/* Terms list */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {filtered.map((entry, i) => {
          const meta    = MODULE_COLORS[entry.module];
          const isOpen  = expanded === i;
          return (
            <div
              key={i}
              onClick={() => setExpanded(isOpen ? null : i)}
              style={{
                background:   T.surface,
                border:       `1px solid ${isOpen ? meta.color + "55" : T.border}`,
                borderRadius: 10,
                padding:      "14px 18px",
                cursor:       "pointer",
                borderLeft:   `3px solid ${meta.color}`,
                transition:   "border-color .2s",
              }}
              onMouseEnter={e => { if (!isOpen) e.currentTarget.style.borderColor = meta.color + "44"; }}
              onMouseLeave={e => { if (!isOpen) e.currentTarget.style.borderColor = T.border; }}
            >
              {/* Row */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 10,
                    background: meta.dim, color: meta.color, border: `1px solid ${meta.color}33`,
                    whiteSpace: "nowrap", flexShrink: 0, letterSpacing: "0.03em",
                  }}>
                    {meta.label.toUpperCase()}
                  </span>
                  <span style={{ color: "#fff", fontSize: 14, fontWeight: 700 }}>{entry.term}</span>
                  <span style={{ color: T.textDim, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    — {entry.short}
                  </span>
                </div>
                <span style={{ color: T.textDim, fontSize: 16, flexShrink: 0, transform: isOpen ? "rotate(90deg)" : "none", transition: "transform .2s" }}>›</span>
              </div>

              {/* Expanded detail */}
              {isOpen && (
                <div style={{
                  marginTop: 14, paddingTop: 14, borderTop: `1px solid ${T.border}`,
                  color: T.text, fontSize: 14, lineHeight: 1.75,
                }}>
                  {entry.detail}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {filtered.length === 0 && (
        <div style={{ textAlign: "center", color: T.textDim, fontSize: 14, padding: "48px 0" }}>
          No terms match your search.
        </div>
      )}
    </div>
  );
};

export default GlossaryPage;

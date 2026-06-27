// frontend/src/App.js
// ═══════════════════════════════════════════════════════════════════════════════
// Root app — 3 pages only:
//   "home"       → HomePage (unified upload + module config form)
//   "audit"      → AuditPage (sequential module runner with popups)
//   "glossary"   → GlossaryPage
//
// MitigationPage is rendered as an overlay on top of AuditPage when triggered.
// ═══════════════════════════════════════════════════════════════════════════════

import React, { useState } from "react";
import Navbar          from "./components/Navbar";
import HomePage        from "./pages/HomePage";
import AuditPage       from "./pages/AuditPage";
import MitigationPage  from "./pages/MitigationPage";
import GlossaryPage    from "./pages/GlossaryPage";
import AnalyticsPage   from "./pages/AnalyticsPage";
  import MonitoringPage  from "./pages/MonitoringPage";

import { ThemeProvider, useTheme } from "./theme";

function AppContent() {
  const { T } = useTheme();

  // "home" | "audit" | "glossary"
  const [currentPage,  setCurrentPage]  = useState("home");
  const [auditParams,  setAuditParams]  = useState(null);
  const [showMitigation, setShowMitigation] = useState(false);
  const [mitigationPrefill, setMitigationPrefill] = useState({});

  const handleStartAudit = (params) => {
    setAuditParams(params);
    setShowMitigation(false);
    setCurrentPage("audit");
  };

  const handleOpenMitigation = (prefill = {}) => {
    setMitigationPrefill(prefill);
    setShowMitigation(true);
  };

  const handleCloseMitigation = () => {
    setShowMitigation(false);
  };

  return (
    <div style={{ minHeight: "100vh", background: T.bg, fontFamily: T.font }}>
      <Navbar currentPage={currentPage} onNavigate={setCurrentPage} />

      {currentPage === "home" && (
        <HomePage onStartAudit={handleStartAudit} />
      )}

      {currentPage === "audit" && (
        <AuditPage
          auditParams={auditParams}
          onBack={() => setCurrentPage("home")}
          onOpenMitigation={handleOpenMitigation}
        />
      )}

      {currentPage === "glossary" && (
        <GlossaryPage />
      )}

      {currentPage === "analytics" && (
        <AnalyticsPage />
      )}

        {currentPage === "monitoring" && (
    <MonitoringPage />
  )}
 

      {/* Mitigation overlay — rendered on top of AuditPage */}
      {showMitigation && (
        <MitigationPage
          prefillFile={mitigationPrefill.csvFile}
          prefillTarget={mitigationPrefill.target}
          prefillSensitive={mitigationPrefill.sensitive}
          onClose={handleCloseMitigation}
        />
      )}
    </div>
  );
}

function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  );
}

export default App;
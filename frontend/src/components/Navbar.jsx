// frontend/src/components/Navbar.jsx
import React from "react";
import { useTheme } from "../theme";

const NAV_LINKS = [
  { label: "Home",       page: "home",       icon: "🏠" },
  { label: "Analytics",  page: "analytics",  icon: "📊" },
  { label: "Monitoring", page: "monitoring", icon: "📡", badge: "NEW" },
  { label: "Glossary",   page: "glossary",   icon: "📖" },
];

const Navbar = ({ currentPage, onNavigate }) => {
  const { T, theme, toggleTheme } = useTheme();

  return (
    <nav style={{
      background: T.surface,
      borderBottom: `1px solid ${T.border}`,
      fontFamily: T.font,
      position: "sticky", top: 0, zIndex: 100,
    }}>
      <div style={{
        maxWidth: 1200, margin: "0 auto", padding: "0 32px",
        height: 52, display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        {/* Logo */}
        <button
          onClick={() => onNavigate("home")}
          style={{
            display: "flex", alignItems: "center", gap: 10,
            background: "none", border: "none", cursor: "pointer", padding: 0,
          }}
        >
          <div style={{
            width: 28, height: 28, borderRadius: 7,
            background: `linear-gradient(135deg, ${T.amber}, #e07b00)`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 14, fontWeight: 900, color: "#000",
          }}>⚖</div>
          <span style={{ color: "#fff", fontSize: 16, fontWeight: 800, letterSpacing: "-0.02em" }}>
            EcoPulse <span style={{ color: T.amber }}>AI</span>
          </span>
          <span style={{
            fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
            color: T.textDim, borderLeft: `1px solid ${T.border}`, paddingLeft: 10, marginLeft: 2,
          }}>
            Audit Suite
          </span>
        </button>

        {/* Nav links + theme toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          {NAV_LINKS.map(({ label, page, icon, badge }) => {
            const active = currentPage === page;
            return (
              <button
                key={page}
                onClick={() => onNavigate(page)}
                style={{
                  color: active ? "#fff" : T.textDim,
                  fontSize: 13, fontWeight: 600,
                  padding: "5px 12px", borderRadius: 6,
                  background: active ? T.surfaceHi : "transparent",
                  border: active ? `1px solid ${T.border}` : "1px solid transparent",
                  cursor: "pointer", fontFamily: T.font, transition: "all .15s",
                  display: "flex", alignItems: "center", gap: 5,
                }}
                onMouseEnter={e => { if (!active) { e.currentTarget.style.color = T.text; e.currentTarget.style.background = T.surfaceHi; }}}
                onMouseLeave={e => { if (!active) { e.currentTarget.style.color = T.textDim; e.currentTarget.style.background = "transparent"; }}}
              >
                <span style={{ fontSize: 12 }}>{icon}</span>
                {label}
                {badge && (
                  <span style={{
                    fontSize: 9, fontWeight: 800, padding: "1px 5px", borderRadius: 4,
                    background: T.amber + "33", color: T.amber, letterSpacing: "0.04em",
                  }}>{badge}</span>
                )}
              </button>
            );
          })}

          <button
            onClick={toggleTheme}
            style={{
              marginLeft: 8, width: 32, height: 32, borderRadius: 6,
              background: T.surfaceHi, border: `1px solid ${T.border}`,
              cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 16, transition: "all .15s",
            }}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
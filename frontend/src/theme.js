import React, { createContext, useContext, useState, useEffect } from 'react';

const themes = {
  dark: {
    bg:         "#0c0e12",
    surface:    "#141821",
    surfaceHi:  "#1c2030",
    border:     "#2a2f3d",
    text:       "#c8cdd8",
    textDim:    "#6b7280",
    amber:      "#f59e0b",
    amberDim:   "#f59e0b22",
    red:        "#ef4444",
    redDim:     "#ef444422",
    green:      "#22c55e",
    greenDim:   "#22c55e22",
    sky:        "#38bdf8",
    skyDim:     "#38bdf822",
    violet:     "#a78bfa",
    violetDim:  "#a78bfa22",
    font:       "'Geist', 'SF Mono', system-ui, sans-serif",
  },
  light: {
    bg:         "#ffffff",
    surface:    "#f8fafc",
    surfaceHi:  "#e2e8f0",
    border:     "#cbd5e1",
    text:       "#1e293b",
    textDim:    "#64748b",
    amber:      "#d97706",
    amberDim:   "#d9770622",
    red:        "#dc2626",
    redDim:     "#dc262622",
    green:      "#16a34a",
    greenDim:   "#16a34a22",
    sky:        "#0284c7",
    skyDim:     "#0284c722",
    violet:     "#7c3aed",
    violetDim:  "#7c3aed22",
    font:       "'Geist', 'SF Mono', system-ui, sans-serif",
  },
};

// Compatibility export for existing imports: `import { T } from "../theme"`.
// This remains dark by default; dynamic theme-aware components should use `useTheme()`.
export const T = themes.dark;

const ThemeContext = createContext({
  T: themes.dark,
  theme: 'dark',
  toggleTheme: () => {},
});

export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState('dark');

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme && themes[savedTheme]) {
      setTheme(savedTheme);
    }
  }, []);

  const toggleTheme = () => {
    const newTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    localStorage.setItem('theme', newTheme);
  };

  const themeVars = themes[theme];

  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty('--bg', themeVars.bg);
    root.style.setProperty('--surface', themeVars.surface);
    root.style.setProperty('--surfaceHi', themeVars.surfaceHi);
    root.style.setProperty('--border', themeVars.border);
    root.style.setProperty('--text', themeVars.text);
    root.style.setProperty('--textDim', themeVars.textDim);
    root.style.setProperty('--amber', themeVars.amber);
    root.style.setProperty('--red', themeVars.red);
    root.style.setProperty('--green', themeVars.green);
    root.style.setProperty('--sky', themeVars.sky);
    root.style.setProperty('--violet', themeVars.violet);
  }, [themeVars]);

  return (
    <ThemeContext.Provider value={{ T: themeVars, theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => useContext(ThemeContext);

export default T;

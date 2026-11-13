import { useSyncExternalStore } from "react";

export type Theme = "dark" | "light";
const KEY = "rinz.theme";
const listeners = new Set<() => void>();

function initial(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "dark" || saved === "light") return saved;
  } catch { /* storage blocked */ }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

let current: Theme = initial();
document.documentElement.dataset.theme = current;

export function setTheme(t: Theme) {
  current = t;
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem(KEY, t); } catch { /* ignore */ }
  listeners.forEach((l) => l());
}

export function useTheme(): Theme {
  return useSyncExternalStore((l) => { listeners.add(l); return () => listeners.delete(l); }, () => current);
}

/** Colours for chart libraries, which need real colour values rather than CSS variables. */
export const CHART = {
  dark: { axis: "#8b9cad", grid: "#22313f", border: "#253546", bg: "#162330", tipBg: "#1b2a38", tipBorder: "#34485c", tipText: "#e4eaf0",
    up: "#3fbf8f", down: "#ef6b62", bar: "#ef6b62", line: "#6fa8f5", candleUp: "#3fbf8f", candleDown: "#ef6b62", empty: "#253546" },
  light: { axis: "#5b6b7a", grid: "#e3e9ee", border: "#dbe2e8", bg: "#ffffff", tipBg: "#ffffff", tipBorder: "#c3ced8", tipText: "#14202b",
    up: "#17845c", down: "#cc3b32", bar: "#cc3b32", line: "#2563c9", candleUp: "#17845c", candleDown: "#cc3b32", empty: "#e3e9ee" },
} as const;

export const useChartColors = () => CHART[useTheme()];

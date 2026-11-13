import { BookMarked, Blocks, CandlestickChart, Dna, SlidersHorizontal, Crosshair, Database, FlaskConical, ScanSearch, Hand, LayoutDashboard, Layers, Zap, type LucideIcon } from "lucide-react";

export type Page = { id: string; path: string; label: string; icon: LucideIcon; color: string; group: string };

export const DESK_COLORS = { ema: "#7fb0f0", ict: "#f0965a", smc: "#d98fc0", candle: "#5fc9c0" } as const;

/** Only the pages the forex workflow actually uses. */
export const PAGES: Page[] = [
  { id: "dashboard", path: "/", label: "Dashboard", icon: LayoutDashboard, color: "currentColor", group: "Overview" },
  { id: "ema", path: "/desk/ema", label: "EMA Desk", icon: Layers, color: DESK_COLORS.ema, group: "Strategy desks" },
  { id: "candle", path: "/desk/candle", label: "Candle Desk", icon: CandlestickChart, color: DESK_COLORS.candle, group: "Strategy desks" },
  { id: "ict", path: "/desk/ict", label: "ICT Desk", icon: Zap, color: DESK_COLORS.ict, group: "Strategy desks" },
  { id: "smc", path: "/desk/smc", label: "SMC Desk", icon: Crosshair, color: DESK_COLORS.smc, group: "Strategy desks" },
  { id: "manual", path: "/desk/manual", label: "Manual Trades", icon: Hand, color: "#9aa8b5", group: "Strategy desks" },
  { id: "backtest-lab", path: "/backtest-lab", label: "Backtest Lab", icon: FlaskConical, color: "#8b5cf6", group: "Research" },
  { id: "builder", path: "/builder", label: "Rule Builder", icon: Blocks, color: "#ec4899", group: "Research" },
  { id: "optimizer", path: "/optimizer", label: "Optimiser", icon: SlidersHorizontal, color: "#22c55e", group: "Research" },
  { id: "generator", path: "/generator", label: "Strategy Generator", icon: Dna, color: "#2dd4bf", group: "Research" },
  { id: "library", path: "/library", label: "Strategy Library", icon: BookMarked, color: "#8b5cf6", group: "Research" },
  { id: "chart-lab", path: "/chart-lab", label: "Chart Lab", icon: ScanSearch, color: "#f59e0b", group: "Research" },
  { id: "data", path: "/data", label: "Market Data", icon: Database, color: "#2dd4bf", group: "Research" },
];

export const GROUPS = [...new Set(PAGES.map((p) => p.group))];

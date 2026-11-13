import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Moon, OctagonX, PanelLeftClose, PanelLeftOpen, Sun } from "lucide-react";
import { API } from "./api";
import { GROUPS, PAGES } from "./nav";
import { setTheme, useTheme } from "./theme";
import KillDialog from "./trading/KillDialog";

type Status = {
  environment: string; mode: "demo" | "live"; live_trading_enabled: boolean;
  brokers: { id: string; label: string; configured: boolean; connected: boolean; detail?: string; account_mode?: string; server?: string }[];
};
const pad = (n: number) => String(n).padStart(2, "0");
const SIDEBAR_KEY = "rinz.sidebar";

function useStatus() {
  const [status, setStatus] = useState<Status | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  useEffect(() => {
    let dead = false;
    const poll = async () => {
      const t0 = performance.now();
      try {
        const r = await fetch(`${API}/status`);
        if (!r.ok) throw new Error();
        const d = await r.json();
        if (!dead) { setStatus(d); setLatency(Math.round(performance.now() - t0)); }
      } catch { if (!dead) { setStatus(null); setLatency(null); } }
    };
    poll();
    const id = setInterval(poll, 15000);
    return () => { dead = true; clearInterval(id); };
  }, []);
  return { status, latency };
}

/** Sidebar starts open; once closed it stays closed (remembered) until opened again. */
function useSidebar() {
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem(SIDEBAR_KEY) !== "closed"; } catch { return true; }
  });
  useEffect(() => { try { localStorage.setItem(SIDEBAR_KEY, open ? "open" : "closed"); } catch { /* ignore */ } }, [open]);
  return [open, setOpen] as const;
}

/** Four session arcs around a dot: the brand mark echoes the session clock. */
function Mark() {
  const arcs = ["var(--s-sydney)", "var(--s-tokyo)", "var(--s-london)", "var(--s-newyork)"];
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
      {arcs.map((c, i) => (
        <path key={c} d="M13 2.5 A10.5 10.5 0 0 1 23.5 13" fill="none" stroke={c} strokeWidth="3" strokeLinecap="round"
          transform={`rotate(${i * 90} 13 13)`} />
      ))}
      <circle cx="13" cy="13" r="3" fill="var(--text)" />
    </svg>
  );
}

export default function Shell() {
  const loc = useLocation();
  const { status, latency } = useStatus();
  const [now, setNow] = useState(new Date());
  const [open, setOpen] = useSidebar();
  const [killOpen, setKillOpen] = useState(false);
  const [killNote, setKillNote] = useState("");
  const theme = useTheme();

  useEffect(() => { const id = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(id); }, []);
  useEffect(() => { if (!killNote) return; const id = setTimeout(() => setKillNote(""), 12000); return () => clearTimeout(id); }, [killNote]);

  const active = PAGES.find((p) => p.path === loc.pathname) ?? PAGES[0];
  const mode = status?.mode ?? "demo";
  const utc = `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())}`;
  const apiUp = latency !== null;
  const broker = status?.brokers.find((b) => b.connected) ?? status?.brokers.find((b) => b.configured) ?? status?.brokers[0];
  const isDesk = (g: string) => g === "Strategy desks";

  return (
    <div className={`sh ${open ? "side-open" : "side-closed"}`}>
      <aside className="sh-side" aria-label="Main navigation">
        <NavLink to="/" className="sh-brand" aria-label="Rinz Algo home"><Mark />{open && <b>Rinz Algo</b>}</NavLink>
        <nav className="sh-nav">
          {GROUPS.map((g) => (
            <div key={g} className="sh-group">
              {open && <h4>{g}</h4>}
              {PAGES.filter((p) => p.group === g).map((p) => (
                <NavLink key={p.id} to={p.path} end title={open ? undefined : p.label}
                  className={({ isActive }) => `sh-link ${isActive ? "active" : ""}`}
                  style={{ ["--c" as string]: isDesk(g) ? p.color : "var(--accent)" }}>
                  <p.icon size={18} color={isDesk(g) ? p.color : "currentColor"} aria-hidden="true" />
                  {open && <span>{p.label}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <button className="sh-toggle" onClick={() => setOpen(!open)} aria-label={open ? "Collapse sidebar" : "Expand sidebar"} title={open ? "Collapse" : "Expand"}>
          {open ? <><PanelLeftClose size={18} /><span>Collapse</span></> : <PanelLeftOpen size={18} />}
        </button>
      </aside>

      <header className="sh-top">
        <h1 className="sh-title">{active.label}</h1>
        <span className="sh-spacer" />
        <div className="sh-conn" role="status" aria-label="Connection status">
          <span title={apiUp ? `Backend responding in ${latency} ms` : "Backend not reachable on port 8000"}>
            <i className={`sig ${apiUp ? "ok" : "bad"}`} />{apiUp ? `Server ${latency} ms` : "Server offline"}
          </span>
          <span title={broker?.detail ?? "No broker set up"}>
            <i className={`sig ${broker?.connected ? "ok" : "off"}`} />
            {broker ? `${broker.server ?? broker.label}${broker.connected ? "" : broker.configured ? " not connected" : " not set up"}` : "No broker"}
          </span>
        </div>
        <span className="sh-clock" title="Coordinated Universal Time">{utc}<small>UTC</small></span>
        <span className={`sh-env ${mode}`}>{mode === "live" ? "Live money" : "Demo"}</span>
        <button className="icon-btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`} title={theme === "dark" ? "Light mode" : "Dark mode"}>
          {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
        </button>
        <button className="kill" onClick={() => setKillOpen(true)} title="Close all Rinz positions and halt every strategy">
          <OctagonX size={16} /><span>Kill switch</span>
        </button>
      </header>
      {killNote && <div className="kill-note" role="alert">{killNote}</div>}
      {killOpen && <KillDialog onClose={() => setKillOpen(false)} onDone={setKillNote} />}

      <main className="sh-main"><Outlet /></main>
    </div>
  );
}

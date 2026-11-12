import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { Eye, LogOut, Menu, Star, Tag } from "lucide-react";
import { API } from "./api";
import { DESK_PILLS, FAVORITES, PAGES } from "./nav";
import { SESSIONS, activeSessions, fxMarketOpen } from "./sessions";

type Status = {
  environment: string; mode: "demo" | "live"; live_trading_enabled: boolean;
  brokers: { id: string; label: string; configured: boolean; connected: boolean }[];
};
const pad = (n: number) => String(n).padStart(2, "0");

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

export default function Shell() {
  const nav = useNavigate();
  const loc = useLocation();
  const { status, latency } = useStatus();
  const [now, setNow] = useState(new Date());
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(() => localStorage.getItem("rinz.pinned") === "1");
  const [loading, setLoading] = useState(false);
  const [labels, setLabels] = useState(true);
  const [fontStep, setFontStep] = useState(() => Number(localStorage.getItem("rinz.font") ?? 0));
  const first = useRef(true);

  useEffect(() => { const id = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(id); }, []);
  useEffect(() => { document.documentElement.style.setProperty("--font-size", `${12 + fontStep}px`); localStorage.setItem("rinz.font", String(fontStep)); }, [fontStep]);
  useEffect(() => { localStorage.setItem("rinz.pinned", pinned ? "1" : "0"); }, [pinned]);
  useEffect(() => { // branded loader on route change (not on first paint)
    if (first.current) { first.current = false; return; }
    setLoading(true); const t = setTimeout(() => setLoading(false), 350); return () => clearTimeout(t);
  }, [loc.pathname]);

  const go = (path: string) => { nav(path); if (!pinned) setOpen(false); };
  const active = PAGES.find((p) => p.path === loc.pathname) ?? PAGES[0];
  const live = activeSessions(now).map((s) => s.id);
  const marketOpen = fxMarketOpen(now);
  const mode = status?.mode ?? "demo";
  const utc = `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())}`;
  const date = now.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });

  return (
    <>
      <aside className="sh-rail" aria-label="Pages">
        <button className="rail-btn" title="Menu" onClick={() => setOpen(true)}><Menu size={15} /></button>
        <button className="rail-btn" title="Favorites" style={{ color: "var(--amber)" }} onClick={() => setOpen(true)}><Star size={15} /></button>
        {PAGES.map((p) => (
          <button key={p.id} title={`${p.label}${p.status !== "ready" ? ` (${p.status})` : ""}`} onClick={() => go(p.path)}
            className={`rail-btn ${active.id === p.id ? "active" : ""} ${p.status !== "ready" ? "planned" : ""}`} style={{ color: p.color, ["--c" as string]: p.color }}>
            <p.icon size={15} />
          </button>
        ))}
      </aside>

      {(open || pinned) && !pinned && <div className="sh-scrim" onClick={() => setOpen(false)} />}
      <nav className={`sh-drawer ${open ? "open" : ""} ${pinned ? "pinned" : ""}`} aria-label="Navigation drawer">
        <button className="pin" onClick={() => setPinned(!pinned)}>{pinned ? "UNPIN" : "PIN OPEN"} ›</button>
        <h4>★ FAVORITES</h4>
        {[PAGES[0], ...FAVORITES].map((p) => (
          <button key={p.id} className={`drawer-item ${active.id === p.id ? "active" : ""}`} style={{ ["--c" as string]: p.color }} onClick={() => go(p.path)}>
            <p.icon size={14} color={p.color} /> {p.label}
            {p.status !== "ready" && <small>{p.status === "inferred" ? "?" : "soon"}</small>}
          </button>
        ))}
      </nav>

      <header className="sh-top">
        <div className="sh-brand"><b>RINZ ALGO</b><small>{date}</small></div>
        <span className="sh-clock" title="UTC">{utc}<small className="muted"> UTC</small></span>
        <span className={`sh-env ${mode}`}>{mode === "live" ? "LIVE" : status?.environment === "local" ? "DEV · DEMO" : "DEMO"}</span>
        <button className="pill fill" onClick={() => setOpen(true)}><Menu size={11} /> MENU</button>
        {DESK_PILLS.map((p) => (
          <button key={p.id} className={`pill ${active.id === p.id ? "on" : ""}`} style={{ color: p.color }} onClick={() => go(p.path)}><p.icon size={11} /> {p.short}</button>
        ))}
        <span className="sess" title={marketOpen ? "Active sessions" : "Forex market closed (Fri 17:00 → Sun 17:00 New York)"}>
          {marketOpen ? SESSIONS.map((s) => <i key={s.id} className={live.includes(s.id) ? "on" : ""} style={live.includes(s.id) ? { background: s.color } : undefined}>{s.label.slice(0, 3).toUpperCase()}</i>)
            : <i>MARKET CLOSED</i>}
        </span>
        {status?.brokers.map((b) => (
          <span key={b.id} className="pill" style={{ color: b.connected ? "var(--green)" : "var(--muted)" }} title={b.connected ? "Connected" : b.configured ? "Configured, not connected" : "Not configured"}>
            <i className={`dot ${b.connected ? "ok" : b.configured ? "warn" : ""}`} /> {b.label}
          </span>
        ))}
        <span className="pill" title="API latency"><i className={`dot ${latency === null ? "bad" : "ok"}`} /> API {latency === null ? "DOWN" : `${latency}ms`}</span>
        <span className="sh-spacer" />
        <button className={`pill ${labels ? "on" : ""}`} onClick={() => setLabels(!labels)}><Tag size={11} /> LABELS</button>
        <button className="pill" onClick={() => setFontStep((fontStep + 1) % 4)} title="Font size">Aa</button>
        <span className="pill" title="Theme"><i className="dot ok" /> MONO DARK</span>
        <button className="pill" title="Hide values"><Eye size={11} /></button>
        <button className="kill" onClick={() => alert("Kill switch arrives with execution (Phase 5)")}>KILL SWITCH</button>
        <button className="pill" title="Logout"><LogOut size={11} /></button>
      </header>

      {loading && <div className="sh-loader" aria-live="polite"><div><div className="ring" /><b style={{ letterSpacing: ".2em" }}>RINZ ALGO</b><div className="muted" style={{ fontSize: 10 }}>waking the desk</div><div className="bar"><i /></div></div></div>}
      <main className={`sh-main ${pinned ? "pinned" : ""} ${labels ? "" : "no-labels"}`}><Outlet /></main>
    </>
  );
}

import { useEffect, useMemo, useState } from "react";
import { SESSIONS, activeSessions, daySegments, fxMarketOpen, humanMinutes, minutesToChange } from "./sessions";
import "./session-clock.css";

const pad = (n: number) => String(n).padStart(2, "0");
const HOURS = [0, 3, 6, 9, 12, 15, 18, 21, 24];

/** Where the FX market is in its day: one row per session across the current UTC day, with a live "now" line. */
export default function SessionClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const id = setInterval(() => setNow(new Date()), 30_000); return () => clearInterval(id); }, []);

  const minuteKey = Math.floor(now.getTime() / 60_000);
  const view = useMemo(() => {
    const t = new Date(minuteKey * 60_000);
    const day0 = new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate()));
    const rows = SESSIONS.map((s) => {
      const segs = daySegments(s, day0);
      const open = activeSessions(t).some((a) => a.id === s.id);
      return { s, segs, open, change: minutesToChange(s, t) };
    });
    return { rows, pos: (t.getTime() - day0.getTime()) / 86_400_000, marketOpen: fxMarketOpen(t) };
  }, [minuteKey]);

  const live = view.rows.filter((r) => r.open).map((r) => r.s.label);
  const local = now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  const utc = `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}`;

  const headline = !view.marketOpen
    ? "The forex market is closed for the weekend."
    : live.length >= 2
      ? `${live.join(" and ")} are both open, the most liquid hours of the day.`
      : live.length === 1
        ? `${live[0]} is open.`
        : "Between sessions. Liquidity is thin.";

  return (
    <section className="sc" aria-label="Forex sessions">
      <header className="sc-head">
        <h2>{headline}</h2>
        <span className="muted">{utc} UTC <span className="sc-local">· {local} your time</span></span>
      </header>

      <div className="sc-grid">
        {view.rows.map(({ s, segs, open, change }) => (
          <div className="sc-row" key={s.id} style={{ ["--sc" as string]: s.color }}>
            <div className="sc-name">
              <b><i className={open ? "on" : ""} />{s.label}</b>
              <small>{change == null ? "" : open ? `closes in ${humanMinutes(change)}` : `opens in ${humanMinutes(change)}`}</small>
            </div>
            <div className="sc-track">
              {segs.map(([a, b]) => (
                <span key={a} className={`sc-seg ${open && view.pos >= a && view.pos < b ? "live" : ""}`}
                  style={{ left: `${a * 100}%`, width: `${(b - a) * 100}%` }} title={`${s.label} session`} />
              ))}
            </div>
          </div>
        ))}

        <div className="sc-axis" aria-hidden="true">
          <span />
          <div className="sc-ticks">
            {HOURS.map((h) => <span key={h} style={{ left: `${(h / 24) * 100}%` }}>{pad(h % 24)}:00</span>)}
          </div>
        </div>
        <div className="sc-now" style={{ ["--x" as string]: view.pos }} aria-hidden="true"><span>now</span></div>
      </div>
    </section>
  );
}

// Forex trading sessions, evaluated in each centre's own timezone so daylight saving is correct.
export const SESSIONS = [
  { id: "sydney", label: "Sydney", tz: "Australia/Sydney", open: 7, close: 16, color: "var(--s-sydney)" },
  { id: "tokyo", label: "Tokyo", tz: "Asia/Tokyo", open: 9, close: 18, color: "var(--s-tokyo)" },
  { id: "london", label: "London", tz: "Europe/London", open: 8, close: 17, color: "var(--s-london)" },
  { id: "newyork", label: "New York", tz: "America/New_York", open: 8, close: 17, color: "var(--s-newyork)" },
] as const;
export type Session = (typeof SESSIONS)[number];

const fmts = new Map<string, Intl.DateTimeFormat>();
function localParts(date: Date, tz: string) {
  let f = fmts.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "numeric", minute: "numeric", hour12: false, weekday: "short" });
    fmts.set(tz, f);
  }
  const p = Object.fromEntries(f.formatToParts(date).map((x) => [x.type, x.value]));
  return { hour: (Number(p.hour) % 24) + Number(p.minute) / 60, weekday: p.weekday as string };
}

/** FX is open from Sun 17:00 New York to Fri 17:00 New York. */
export function fxMarketOpen(date: Date): boolean {
  const { hour, weekday } = localParts(date, "America/New_York");
  if (weekday === "Sat") return false;
  if (weekday === "Fri" && hour >= 17) return false;
  if (weekday === "Sun" && hour < 17) return false;
  return true;
}

export function sessionOpen(s: Session, date: Date): boolean {
  if (!fxMarketOpen(date)) return false;
  const { hour, weekday } = localParts(date, s.tz);
  return hour >= s.open && hour < s.close && weekday !== "Sat" && weekday !== "Sun";
}

export function activeSessions(date: Date) {
  return SESSIONS.filter((s) => sessionOpen(s, date));
}

const STEP = 5 * 60_000;

/** Open stretches of a session inside [from, from + 24h), as fractions 0..1 of that window. */
export function daySegments(s: Session, from: Date): [number, number][] {
  const out: [number, number][] = [];
  const n = (24 * 3600_000) / STEP;
  let start = -1;
  for (let i = 0; i <= n; i++) {
    const open = i < n && sessionOpen(s, new Date(from.getTime() + i * STEP));
    if (open && start < 0) start = i;
    if (!open && start >= 0) { out.push([start / n, i / n]); start = -1; }
  }
  return out;
}

/** Minutes until the session next changes state (opens or closes), scanning up to 8 days ahead. */
export function minutesToChange(s: Session, now: Date): number | null {
  const was = sessionOpen(s, now);
  for (let t = STEP; t <= 8 * 24 * 3600_000; t += STEP) {
    if (sessionOpen(s, new Date(now.getTime() + t)) !== was) return Math.round(t / 60_000);
  }
  return null;
}

export function humanMinutes(m: number): string {
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60), r = m % 60;
  if (h >= 24) { const d = Math.floor(h / 24); return `${d}d ${h % 24}h`; }
  return r ? `${h}h ${r}m` : `${h}h`;
}

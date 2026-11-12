// Forex trading sessions, evaluated in each centre's own timezone so daylight saving is correct.
export const SESSIONS = [
  { id: "sydney", label: "Sydney", tz: "Australia/Sydney", open: 7, close: 16, color: "#f59e0b" },
  { id: "tokyo", label: "Tokyo", tz: "Asia/Tokyo", open: 9, close: 18, color: "#ec4899" },
  { id: "london", label: "London", tz: "Europe/London", open: 8, close: 17, color: "#3b6cf6" },
  { id: "newyork", label: "New York", tz: "America/New_York", open: 8, close: 17, color: "#22c55e" },
] as const;

function localParts(date: Date, tz: string) {
  const f = new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "numeric", hour12: false, weekday: "short" });
  const p = Object.fromEntries(f.formatToParts(date).map((x) => [x.type, x.value]));
  return { hour: Number(p.hour) % 24, weekday: p.weekday as string };
}

/** FX is open from Sun 17:00 New York to Fri 17:00 New York. */
export function fxMarketOpen(date: Date): boolean {
  const f = new Intl.DateTimeFormat("en-GB", { timeZone: "America/New_York", hour: "numeric", hour12: false, weekday: "short" });
  const p = Object.fromEntries(f.formatToParts(date).map((x) => [x.type, x.value]));
  const h = Number(p.hour) % 24;
  if (p.weekday === "Sat") return false;
  if (p.weekday === "Fri" && h >= 17) return false;
  if (p.weekday === "Sun" && h < 17) return false;
  return true;
}

export function activeSessions(date: Date) {
  if (!fxMarketOpen(date)) return [];
  return SESSIONS.filter((s) => {
    const { hour, weekday } = localParts(date, s.tz);
    return hour >= s.open && hour < s.close && weekday !== "Sat" && weekday !== "Sun";
  });
}

export const money = (n: number, plus = false) =>
  `${plus && n > 0 ? "+" : n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export const tone = (n: number) => (n > 0 ? "up" : n < 0 ? "down" : "");
export const pct = (n: number) => `${Math.round(n * 100)}%`;
export const pips = (n: number) => `${n > 0 ? "+" : ""}${n.toFixed(1)}`;
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
/** "Thu 5 Nov 14:30" in UTC */
export const dt = (iso: string) => { const d = new Date(iso); return `${DOW[d.getUTCDay()]} ${d.getUTCDate()} ${MON[d.getUTCMonth()]} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`; };
export const dShort = (iso: string) => { const d = new Date(iso.length === 10 ? iso + "T00:00:00Z" : iso); return `${d.getUTCDate()} ${MON[d.getUTCMonth()]}`; };
export const dLong = (iso: string) => { const d = new Date(iso.length === 10 ? iso + "T00:00:00Z" : iso); return `${DOW[d.getUTCDay()]} ${d.getUTCDate()} ${MON[d.getUTCMonth()]}`; };
export const held = (min: number) => (min >= 1440 ? `${Math.floor(min / 1440)}d ${Math.floor((min % 1440) / 60)}h` : min >= 60 ? `${Math.floor(min / 60)}h ${min % 60}m` : `${min}m`);
export const price = (symbol: string, n: number) => n.toFixed(symbol.endsWith("JPY") ? 3 : 5);
export const reasonLabel: Record<string, string> = { tp: "Take profit hit", sl: "Stop loss hit", end: "Closed at end of data" };

const NY_FMT = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", hourCycle: "h23" });
/** FX trading day (YYYY-MM-DD): rolls at 17:00 New York, same rule as the backend, so every page groups days identically. */
export function tradingDay(iso: string): string {
  const p = Object.fromEntries(NY_FMT.formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  const d = new Date(Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day)));
  if (Number(p.hour) >= 17) d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

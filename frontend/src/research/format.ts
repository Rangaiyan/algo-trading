export const money = (n: number) => `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
export const pf = (x: number | null | undefined) => (x == null ? "—" : x.toFixed(2));
export const pctv = (x: number) => `${x > 0 ? "+" : ""}${x.toFixed(1)}%`;
export const tone = (n: number) => (n > 0 ? "up" : n < 0 ? "down" : "");

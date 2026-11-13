import { CheckCircle2, CircleDashed, XCircle } from "lucide-react";
import type { GateRow, Slim } from "../api";
import { money, pctv, pf, tone } from "./format";

export function Verdict({ v }: { v: string | null | undefined }) {
  const label = v === "pass" ? "PASSES GATE 1" : v === "fail" ? "FAILS GATE 1" : v === "pending" ? "HOLD-OUT PENDING" : "NOT VALIDATED";
  return <span className={`verdict ${v ?? "none"}`}>{label}</span>;
}

export function GateTable({ rows }: { rows: GateRow[] }) {
  return (
    <table className="tbl gate">
      <thead><tr><th>Gate 1 criterion</th><th>Result</th><th>Value</th><th>Required</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.criterion} className={r.status}>
          <td>{r.criterion}</td>
          <td className="gate-st">{r.status === "pass" ? <CheckCircle2 size={15} /> : r.status === "fail" ? <XCircle size={15} /> : <CircleDashed size={15} />} {r.status}</td>
          <td>{String(r.value ?? "—")}</td>
          <td className="muted">{r.required}</td>
        </tr>))}
      </tbody>
    </table>
  );
}

export function MetricRows({ rows }: { rows: { label: string; m: Slim | null | undefined; note?: string }[] }) {
  return (
    <table className="tbl">
      <thead><tr><th>Run</th><th>Trades</th><th>Net</th><th>Return</th><th>Win</th><th>PF</th><th>Max DD</th><th>Sharpe</th></tr></thead>
      <tbody>{rows.filter((r) => r.m).map(({ label, m, note }) => (
        <tr key={label}>
          <td>{label}{note && <small className="muted"> {note}</small>}</td>
          <td>{m!.trades}</td>
          <td className={tone(m!.net_profit)}>{money(m!.net_profit)}</td>
          <td className={tone(m!.return_pct)}>{pctv(m!.return_pct)}</td>
          <td>{Math.round(m!.win_rate * 100)}%</td>
          <td className={(m!.profit_factor ?? 0) >= 1.3 ? "up" : (m!.profit_factor ?? 0) < 1 ? "down" : ""}>{pf(m!.profit_factor)}</td>
          <td>{m!.max_drawdown_pct.toFixed(1)}%</td>
          <td>{m!.sharpe.toFixed(2)}</td>
        </tr>))}
      </tbody>
    </table>
  );
}

export function Params({ p }: { p: Record<string, unknown> }) {
  const entries = Object.entries(p).filter(([k]) => k !== "spec");
  if (!entries.length) return <span className="muted">strategy defaults</span>;
  return <span className="params">{entries.map(([k, v]) => <span key={k} className="chip">{k} {Array.isArray(v) ? v.join("+") : String(v)}</span>)}</span>;
}

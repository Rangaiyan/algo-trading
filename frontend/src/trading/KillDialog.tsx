import { useEffect, useRef, useState } from "react";
import { OctagonX } from "lucide-react";
import { killSwitch } from "../api";

/** Kill switch (doc 13): close Rinz positions, cancel pending orders, halt all trading. Typed confirmation. */
export default function KillDialog({ onClose, onDone }: { onClose: () => void; onDone?: (msg: string) => void }) {
  const [text, setText] = useState("");
  const [manual, setManual] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [busy, onClose]);

  async function go() {
    setBusy(true); setErr("");
    try {
      const r = await killSwitch(manual);
      const msg = `Kill switch done: closed ${r.closed.length} position(s), cancelled ${r.cancelled.length} order(s)` +
        (r.failed.length ? `, ${r.failed.length} FAILED (${r.failed.map((f) => f.reason).join("; ")}). Close those in MT5.` : ". Trading is halted.");
      onDone?.(msg);
      onClose();
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <div className="modal-scrim" role="dialog" aria-modal="true" aria-labelledby="kill-title" onClick={() => !busy && onClose()}>
      <div className="modal kill-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-body">
          <h2 id="kill-title" className="kill-title"><OctagonX size={22} /> Kill switch</h2>
          <p>This immediately:</p>
          <ul>
            <li>closes every position opened by Rinz (at market),</li>
            <li>cancels every pending Rinz order,</li>
            <li>pauses all strategy sessions and <b>halts trading</b> until you press Resume.</li>
          </ul>
          <label className="check"><input type="checkbox" checked={manual} onChange={(e) => setManual(e.target.checked)} />
            <span>Also close my <b>manual</b> trades and orders</span></label>
          <label className="kill-confirm">Type <b>FLATTEN</b> to confirm
            <input ref={input} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && text === "FLATTEN" && go()} aria-label="Type FLATTEN to confirm" />
          </label>
          {err && <p className="err" role="alert">{err}</p>}
          <div className="kill-actions">
            <button className="pill" onClick={onClose} disabled={busy}>Cancel</button>
            <button className="kill" onClick={go} disabled={busy || text !== "FLATTEN"}><OctagonX size={16} /> {busy ? "Flattening…" : "Flatten and halt"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

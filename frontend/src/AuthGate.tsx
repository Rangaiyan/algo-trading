import { useEffect, useState } from "react";
import { KeyRound } from "lucide-react";
import { getToken, setToken } from "./auth";

/** Asks for the backend access token when the backend answers 401. */
export default function AuthGate() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  useEffect(() => {
    const show = () => setOpen(true);
    window.addEventListener("rinz:auth-required", show);
    return () => window.removeEventListener("rinz:auth-required", show);
  }, []);
  if (!open) return null;
  const had = !!getToken();
  return (
    <div className="modal-scrim" role="dialog" aria-modal="true" aria-labelledby="auth-title">
      <div className="modal kill-modal">
        <form className="modal-body" onSubmit={(e) => { e.preventDefault(); setToken(value.trim()); window.location.reload(); }}>
          <h2 id="auth-title" className="auth-title"><KeyRound size={20} /> Access token</h2>
          <p className="muted">{had ? "The saved token was not accepted." : "This Rinz backend needs an access token."} Enter the
            {" "}<code>APP_ACCESS_TOKEN</code> value from the backend's <code>.env</code> file. It is stored only in this browser.</p>
          <input className="auth-input" type="password" autoComplete="current-password" value={value} autoFocus
            onChange={(e) => setValue(e.target.value)} aria-label="Access token" />
          <div className="kill-actions">
            <button type="button" className="pill" onClick={() => setOpen(false)}>Cancel</button>
            <button className="run" style={{ width: "auto" }} disabled={!value.trim()}>Sign in</button>
          </div>
        </form>
      </div>
    </div>
  );
}

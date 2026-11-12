import { useLocation } from "react-router-dom";
import { PAGES } from "./nav";

const NOTE = {
  planned: "Specified from the reference screenshots. Not built yet.",
  inferred: "Only the menu name appears in the reference; there is no screenshot of its content. Confirm what you want before it is built.",
  ready: "",
};

export default function PlannedPage() {
  const { pathname } = useLocation();
  const p = PAGES.find((x) => x.path === pathname);
  if (!p) return <p className="muted">Page not found.</p>;
  return (
    <>
      <div className="pg-head">
        <div className="pg-icon" style={{ color: p.color }}><p.icon size={20} /></div>
        <div style={{ flex: 1 }}><h1>{p.label}</h1><p>{p.summary}</p></div>
        <span className={`tag ${p.status}`}>{p.status}</span>
      </div>
      <div className="panel">
        <h3>{NOTE[p.status]}</h3>
        {p.was && <p className="muted">Reference page: “{p.was}”.</p>}
        <h3>Features to build</h3>
        <ul className="feat">{p.features.map((f) => <li key={f}>{f}</li>)}</ul>
      </div>
    </>
  );
}

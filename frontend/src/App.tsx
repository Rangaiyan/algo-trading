import { HashRouter, Route, Routes } from "react-router-dom";
import "./shell.css";
import "./App.css";
import BacktestLab from "./BacktestLab";
import Dashboard from "./Dashboard";
import DeskPage from "./desk/DeskPage";
import PlannedPage from "./PlannedPage";
import Shell from "./Shell";
import { PAGES } from "./nav";

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Dashboard />} />
          <Route path="/backtest-lab" element={<BacktestLab />} />
          {["ema", "ict", "smc", "candle"].map((d) => <Route key={d} path={`/desk/${d}`} element={<DeskPage desk={d} />} />)}
          {PAGES.filter((p) => !["dashboard", "backtest-lab", "ema", "ict", "smc", "candle"].includes(p.id)).map((p) => (
            <Route key={p.id} path={p.path} element={<PlannedPage />} />
          ))}
          <Route path="*" element={<PlannedPage />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}

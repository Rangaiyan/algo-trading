import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import "./shell.css";
import "./App.css";
import "./dashboard.css";
import "./desk/desk.css";
import BacktestLab from "./BacktestLab";
import Dashboard from "./Dashboard";
import DeskPage from "./desk/DeskPage";
import Shell from "./Shell";

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Dashboard />} />
          <Route path="/backtest-lab" element={<BacktestLab />} />
          {["ema", "candle", "ict", "smc", "manual"].map((d) => <Route key={d} path={`/desk/${d}`} element={<DeskPage desk={d} />} />)}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}

import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import "./shell.css";
import "./App.css";
import "./dashboard.css";
import "./desk/desk.css";
import BacktestLab from "./BacktestLab";
import Dashboard from "./Dashboard";
import DataPage from "./DataPage";
import ChartLab from "./lab/ChartLab";
import Builder from "./research/Builder";
import Generator from "./research/Generator";
import Library from "./research/Library";
import Optimizer from "./research/Optimizer";
import DeskPage from "./desk/DeskPage";
import Shell from "./Shell";

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Dashboard />} />
          <Route path="/backtest-lab" element={<BacktestLab />} />
          <Route path="/data" element={<DataPage />} />
          <Route path="/chart-lab" element={<ChartLab />} />
          <Route path="/builder" element={<Builder />} />
          <Route path="/optimizer" element={<Optimizer />} />
          <Route path="/library" element={<Library />} />
          <Route path="/generator" element={<Generator />} />
          {["ema", "candle", "ict", "smc", "manual"].map((d) => <Route key={d} path={`/desk/${d}`} element={<DeskPage desk={d} />} />)}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}

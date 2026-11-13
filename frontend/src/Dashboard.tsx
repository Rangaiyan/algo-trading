import LiveAccount from "./LiveAccount";
import SessionClock from "./SessionClock";
import "./dashboard.css";

/** Home page: where the market is in its day, then the real MT5 account. */
export default function Dashboard() {
  return (
    <>
      <SessionClock />
      <LiveAccount />
    </>
  );
}

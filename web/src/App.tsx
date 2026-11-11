import { useEffect, useState } from "react";
import { getHealth } from "./api";
import { DisplaySettingsPage } from "./pages/DisplaySettingsPage";
import { StatsViewerPage } from "./pages/StatsViewerPage";

type Tab = "viewer" | "settings";

export default function App() {
  const [tab, setTab] = useState<Tab>("viewer");
  const [health, setHealth] = useState<string>("checking…");

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((body) => {
        if (!cancelled) setHealth(`API ${body.status} · v${body.version}`);
      })
      .catch(() => {
        if (!cancelled) setHealth("API offline");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const healthOk = health.startsWith("API ok");

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>PentaKlip</h1>
          <p>Replay stats viewer · per-lane display settings</p>
        </div>
        <div className={`health ${healthOk ? "ok" : ""}`}>{health}</div>
      </header>

      <nav className="tabs">
        <button
          className={`tab ${tab === "viewer" ? "active" : ""}`}
          onClick={() => setTab("viewer")}
        >
          スタッツ表示
        </button>
        <button
          className={`tab ${tab === "settings" ? "active" : ""}`}
          onClick={() => setTab("settings")}
        >
          表示設定
        </button>
      </nav>

      {tab === "viewer" ? <StatsViewerPage /> : <DisplaySettingsPage />}
    </div>
  );
}

import { useEffect, useState } from "react";
import { getHealth } from "./api";
import { AutoSplitPage } from "./pages/AutoSplitPage";
import { DisplaySettingsPage } from "./pages/DisplaySettingsPage";
import { ReplacePage } from "./pages/ReplacePage";
import { StatsViewerPage } from "./pages/StatsViewerPage";
import { ToolsPage } from "./pages/ToolsPage";

type Tab = "replace" | "autosplit" | "tools" | "viewer" | "settings";

export default function App() {
  const [tab, setTab] = useState<Tab>("replace");
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
        </div>
        <div className={`health ${healthOk ? "ok" : ""}`}>{health}</div>
      </header>

      <nav className="tabs">
        {(
          [
            ["replace", "置き換え"],
            ["autosplit", "自動切り分け"],
            ["tools", "ffmpeg"],
            ["viewer", "スタッツ"],
            ["settings", "表示設定"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            className={`tab ${tab === id ? "active" : ""}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      {/* Keep pages mounted so Stats charts survive tab switches. */}
      <div className="tab-panel" hidden={tab !== "replace"}>
        <ReplacePage />
      </div>
      <div className="tab-panel" hidden={tab !== "autosplit"}>
        <AutoSplitPage />
      </div>
      <div className="tab-panel" hidden={tab !== "tools"}>
        <ToolsPage />
      </div>
      <div className="tab-panel" hidden={tab !== "viewer"}>
        <StatsViewerPage />
      </div>
      <div className="tab-panel" hidden={tab !== "settings"}>
        <DisplaySettingsPage />
      </div>
    </div>
  );
}

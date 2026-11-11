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
          <p>リプレイ置き換え · 自動クリップ · スタッツ</p>
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
            ["settings", "スタッツ設定"],
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

      {tab === "replace" ? <ReplacePage /> : null}
      {tab === "autosplit" ? <AutoSplitPage /> : null}
      {tab === "tools" ? <ToolsPage /> : null}
      {tab === "viewer" ? <StatsViewerPage /> : null}
      {tab === "settings" ? <DisplaySettingsPage /> : null}
    </div>
  );
}

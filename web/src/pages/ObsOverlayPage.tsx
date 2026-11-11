import { useCallback, useEffect, useMemo, useState } from "react";
import { aggregateStatsFolder, buildCharts, getUiPreferences } from "../api";
import { RadarStatChart } from "../components/RadarStatChart";
import type { ChartSpec } from "../types";

function params() {
  return new URLSearchParams(window.location.search);
}

export function ObsOverlayPage() {
  const q = useMemo(() => params(), []);
  const positionFilter = (q.get("position") || "").toUpperCase() || null;
  const playerFilter = q.get("player");
  const refreshSec = Math.max(0, Number(q.get("refresh") || "0") || 0);
  const chroma = q.get("chroma"); // e.g. #00ff00 for chroma key
  const dirParam = q.get("dir");

  const [directory, setDirectory] = useState(dirParam ?? "");
  const [radars, setRadars] = useState<ChartSpec[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (dir: string) => {
    if (!dir.trim()) {
      setError("dir クエリまたは UI 設定のフォルダが必要です");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await aggregateStatsFolder({
        directory: dir.trim(),
        apply_roster: true,
      });
      const charts = await buildCharts(result.aggregated);
      let list = charts.charts.filter((c) => c.chart_type === "radar");
      if (positionFilter) {
        list = list.filter(
          (c) => (c.position || "").toUpperCase() === positionFilter,
        );
      }
      if (playerFilter) {
        const needle = playerFilter.toLowerCase();
        list = list.filter((c) =>
          c.series.some(
            (s) =>
              s.key === "player" &&
              s.player_id.toLowerCase().includes(needle),
          ),
        );
      }
      setRadars(list);
      setMeta(
        [
          `games ${result.game_count}`,
          `radars ${list.length}`,
          positionFilter ? `pos ${positionFilter}` : null,
          playerFilter ? `player ${playerFilter}` : null,
        ]
          .filter(Boolean)
          .join(" · "),
      );
    } catch (err) {
      setError(String(err));
      setRadars([]);
    } finally {
      setBusy(false);
    }
  }, [playerFilter, positionFilter]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let dir = dirParam ?? "";
      if (!dir) {
        try {
          const prefs = await getUiPreferences();
          dir = prefs.last_events_dir || prefs.last_output_root || "";
        } catch {
          /* optional */
        }
      }
      if (cancelled) return;
      setDirectory(dir);
      if (dir) await load(dir);
    })();
    return () => {
      cancelled = true;
    };
  }, [dirParam, load]);

  useEffect(() => {
    if (refreshSec <= 0 || !directory) return;
    const id = window.setInterval(() => {
      void load(directory);
    }, refreshSec * 1000);
    return () => window.clearInterval(id);
  }, [directory, load, refreshSec]);

  useEffect(() => {
    document.documentElement.classList.add("obs-overlay");
    document.body.classList.add("obs-overlay");
    if (chroma) {
      document.documentElement.style.background = chroma;
      document.body.style.background = chroma;
    }
    return () => {
      document.documentElement.classList.remove("obs-overlay");
      document.body.classList.remove("obs-overlay");
      document.documentElement.style.background = "";
      document.body.style.background = "";
    };
  }, [chroma]);

  return (
    <div className="obs-root">
      <div className="obs-toolbar">
        <span className="mono">OBS · radar</span>
        {meta ? <span>{meta}</span> : null}
        {busy ? <span>更新中…</span> : null}
        <button
          type="button"
          className="btn"
          disabled={busy || !directory}
          onClick={() => void load(directory)}
        >
          再読込
        </button>
      </div>
      {error ? <p className="error obs-error">{error}</p> : null}
      <div className="obs-radar-grid">
        {radars.map((chart) => (
          <RadarStatChart key={chart.chart_id} chart={chart} compact />
        ))}
      </div>
      {!busy && radars.length === 0 && !error ? (
        <p className="hint obs-hint">
          レーダーがありません。例:{" "}
          <span className="mono">
            /obs?dir=D:\stats&amp;position=MIDDLE&amp;refresh=30
          </span>
        </p>
      ) : null}
    </div>
  );
}

export function isObsPath(pathname: string = window.location.pathname): boolean {
  return pathname === "/obs" || pathname.startsWith("/obs/");
}

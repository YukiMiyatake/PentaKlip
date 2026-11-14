import { useCallback, useEffect, useMemo, useState } from "react";
import { aggregateStatsFolder, buildCharts, getUiPreferences } from "../api";
import { LaneFilterBar } from "../components/LaneFilterBar";
import { RadarStatChart } from "../components/RadarStatChart";
import {
  filterChartsByLane,
  loadLaneFilter,
  normalizeLaneFilter,
  saveLaneFilter,
  type LaneFilter,
} from "../lanes";
import {
  filterChartsByPlayerVisibility,
  loadHiddenPlayers,
  parseHiddenParam,
} from "../playerVisibility";
import {
  notifyViewFiltersChanged,
  subscribeDisplaySettingsChanged,
  subscribeViewFiltersChanged,
} from "../sync";
import type { ChartSpec } from "../types";

function params() {
  return new URLSearchParams(window.location.search);
}

function resolveLane(q: URLSearchParams): LaneFilter {
  const fromUrl = q.get("position");
  if (fromUrl != null && fromUrl !== "") return normalizeLaneFilter(fromUrl);
  return loadLaneFilter();
}

function resolveHidden(q: URLSearchParams): Set<string> {
  const fromUrl = parseHiddenParam(q.get("hide"));
  if (fromUrl.size > 0) return fromUrl;
  return loadHiddenPlayers();
}

/**
 * OBS Browser Source overlay. Lane filter can be set here or from the Stats
 * tab / URL `position` query (kept in sync via localStorage + BroadcastChannel).
 */
export function ObsOverlayPage() {
  const q = useMemo(() => params(), []);
  const playerFilter = q.get("player");
  const refreshSec = Math.max(0, Number(q.get("refresh") || "0") || 0);
  const chroma = q.get("chroma");
  const dirParam = q.get("dir");

  const [directory, setDirectory] = useState(dirParam ?? "");
  const [laneFilter, setLaneFilter] = useState<LaneFilter>(() => resolveLane(q));
  const [hiddenPlayers, setHiddenPlayers] = useState<Set<string>>(() =>
    resolveHidden(q),
  );
  const [allRadars, setAllRadars] = useState<ChartSpec[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const radars = useMemo(() => {
    const byLane = filterChartsByLane(allRadars, laneFilter);
    return filterChartsByPlayerVisibility(byLane, hiddenPlayers);
  }, [allRadars, laneFilter, hiddenPlayers]);

  const applyLaneToUrl = useCallback((next: LaneFilter) => {
    const u = new URL(window.location.href);
    if (next === "ALL") u.searchParams.delete("position");
    else u.searchParams.set("position", next);
    window.history.replaceState({}, "", u);
  }, []);

  const syncFiltersFromStorage = useCallback(() => {
    const latest = params();
    // Prefer persisted filter so Stats ↔ OBS stay aligned after either side changes.
    const lane = loadLaneFilter();
    setLaneFilter(lane);
    applyLaneToUrl(lane);
    setHiddenPlayers(resolveHidden(latest));
  }, [applyLaneToUrl]);

  function onLaneChange(next: LaneFilter) {
    setLaneFilter(next);
    saveLaneFilter(next);
    applyLaneToUrl(next);
    notifyViewFiltersChanged();
  }

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
      setAllRadars(list);
      setMeta(`games ${result.game_count} · radars ${list.length}`);
    } catch (err) {
      setError(String(err));
      setAllRadars([]);
    } finally {
      setBusy(false);
    }
  }, [playerFilter]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let dir = dirParam ?? "";
      if (!dir) {
        try {
          const prefs = await getUiPreferences();
          if (prefs.last_output_root) {
            const base = prefs.last_output_root.replace(/[/\\]+$/, "");
            const sep =
              prefs.last_output_root.includes("/") &&
              !prefs.last_output_root.includes("\\")
                ? "/"
                : "\\";
            dir = `${base}${sep}stats`;
          } else {
            dir = prefs.last_events_dir || "";
          }
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
    const onSettings = () => {
      if (directory) void load(directory);
    };
    const onFilters = () => syncFiltersFromStorage();
    const offSettings = subscribeDisplaySettingsChanged(onSettings);
    const offFilters = subscribeViewFiltersChanged(onFilters);
    const onStorage = (ev: StorageEvent) => {
      if (
        ev.key === "pentaklip.hiddenPlayerStats" ||
        ev.key === "pentaklip.laneFilter"
      ) {
        syncFiltersFromStorage();
      }
    };
    window.addEventListener("storage", onStorage);
    return () => {
      offSettings();
      offFilters();
      window.removeEventListener("storage", onStorage);
    };
  }, [directory, load, syncFiltersFromStorage]);

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
        <LaneFilterBar
          value={laneFilter}
          onChange={onLaneChange}
          compact
        />
        {meta ? (
          <span className="obs-toolbar-meta">
            {meta}
            {playerFilter ? ` · player ${playerFilter}` : ""}
            {hiddenPlayers.size > 0 ? ` · hide ${hiddenPlayers.size}` : ""}
            {` · show ${radars.length}`}
            {busy ? " · …" : ""}
          </span>
        ) : null}
      </div>
      {error ? <p className="error obs-error">{error}</p> : null}
      <div className="obs-radar-grid">
        {radars.map((chart) => (
          <RadarStatChart key={chart.chart_id} chart={chart} compact />
        ))}
      </div>
      {!busy && radars.length === 0 && !error ? (
        <p className="hint obs-hint">
          レーダーがありません。スタッツ画面でレーン / プレイヤーを選び、OBS
          リンクを開いてください。例:{" "}
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

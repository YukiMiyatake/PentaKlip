import { useCallback, useEffect, useMemo, useState } from "react";
import { aggregateStatsFolder, buildCharts, getUiPreferences } from "../api";
import { LaneFilterBar } from "../components/LaneFilterBar";
import { RadarLayoutControls } from "../components/RadarLayoutControls";
import { RadarLayoutGrid } from "../components/RadarLayoutGrid";
import { RadarStatChart } from "../components/RadarStatChart";
import { RadarThresholdControl } from "../components/RadarThresholdControl";
import {
  ensureRadarLayout,
  loadRadarLayout,
  moveRadarChart,
  resetRadarLayout,
  resizeRadarLayout,
  saveRadarLayout,
  setRadarColumnHeader,
  type RadarLayoutState,
} from "../radarLayout";
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
  RADAR_SCALE_MODE_DEFAULT,
  RADAR_THRESHOLD_DEFAULT,
  loadRadarScaleMode,
  loadRadarThresholdPct,
  normalizeRadarScaleMode,
  normalizeRadarThresholdPct,
  saveRadarScaleMode,
  saveRadarThresholdPct,
  type RadarScaleMode,
} from "../radarScale";
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

function resolveThreshold(q: URLSearchParams): number {
  const fromUrl = q.get("span") ?? q.get("threshold");
  if (fromUrl != null && fromUrl !== "") {
    return normalizeRadarThresholdPct(fromUrl);
  }
  return loadRadarThresholdPct();
}

function resolveScaleMode(q: URLSearchParams): RadarScaleMode {
  const fromUrl = q.get("scale");
  if (fromUrl != null && fromUrl !== "") {
    return normalizeRadarScaleMode(fromUrl);
  }
  return loadRadarScaleMode();
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
  const [radarScaleMode, setRadarScaleMode] = useState<RadarScaleMode>(() =>
    resolveScaleMode(q),
  );
  const [radarThresholdPct, setRadarThresholdPct] = useState(() =>
    resolveThreshold(q),
  );
  const [radarLayout, setRadarLayout] = useState<RadarLayoutState>(() =>
    loadRadarLayout(),
  );
  const [allRadars, setAllRadars] = useState<ChartSpec[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const radars = useMemo(() => {
    const byLane = filterChartsByLane(allRadars, laneFilter);
    return filterChartsByPlayerVisibility(byLane, hiddenPlayers);
  }, [allRadars, laneFilter, hiddenPlayers]);

  const applyFiltersToUrl = useCallback(
    (lane: LaneFilter, mode: RadarScaleMode, threshold: number) => {
      const u = new URL(window.location.href);
      if (lane === "ALL") u.searchParams.delete("position");
      else u.searchParams.set("position", lane);
      if (mode === RADAR_SCALE_MODE_DEFAULT) u.searchParams.delete("scale");
      else u.searchParams.set("scale", mode);
      if (threshold === RADAR_THRESHOLD_DEFAULT) u.searchParams.delete("span");
      else u.searchParams.set("span", String(threshold));
      u.searchParams.delete("threshold");
      window.history.replaceState({}, "", u);
    },
    [],
  );

  const syncFiltersFromStorage = useCallback(() => {
    const latest = params();
    // Prefer persisted filters so Stats ↔ OBS stay aligned after either side changes.
    const lane = loadLaneFilter();
    const mode = loadRadarScaleMode();
    const threshold = loadRadarThresholdPct();
    setLaneFilter(lane);
    setRadarScaleMode(mode);
    setRadarThresholdPct(threshold);
    setRadarLayout(loadRadarLayout());
    applyFiltersToUrl(lane, mode, threshold);
    setHiddenPlayers(resolveHidden(latest));
  }, [applyFiltersToUrl]);

  function persistRadarLayout(next: RadarLayoutState, opts?: { quiet?: boolean }) {
    setRadarLayout(next);
    saveRadarLayout(next);
    if (!opts?.quiet) notifyViewFiltersChanged();
  }

  function onLaneChange(next: LaneFilter) {
    setLaneFilter(next);
    saveLaneFilter(next);
    applyFiltersToUrl(next, radarScaleMode, radarThresholdPct);
    notifyViewFiltersChanged();
  }

  function onRadarScaleModeChange(next: RadarScaleMode) {
    setRadarScaleMode(next);
    saveRadarScaleMode(next);
    applyFiltersToUrl(laneFilter, next, radarThresholdPct);
    notifyViewFiltersChanged();
  }

  function onRadarThresholdChange(next: number) {
    setRadarThresholdPct(next);
    saveRadarThresholdPct(next);
    applyFiltersToUrl(laneFilter, radarScaleMode, next);
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
        ev.key === "pentaklip.laneFilter" ||
        ev.key === "pentaklip.radarThresholdPct" ||
        ev.key === "pentaklip.radarScaleMode" ||
        ev.key === "pentaklip.radarLayout"
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
        <RadarThresholdControl
          mode={radarScaleMode}
          thresholdPct={radarThresholdPct}
          onModeChange={onRadarScaleModeChange}
          onThresholdChange={onRadarThresholdChange}
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
      {radars.length > 0 ? (
        <>
          <RadarLayoutControls
            layout={ensureRadarLayout(
              radarLayout,
              radars.map((c) => c.chart_id),
            )}
            compact
            onColsChange={(cols) => {
              const ids = radars.map((c) => c.chart_id);
              persistRadarLayout(
                resizeRadarLayout(radarLayout, cols, radarLayout.rows, ids),
              );
            }}
            onRowsChange={(rows) => {
              const ids = radars.map((c) => c.chart_id);
              persistRadarLayout(
                resizeRadarLayout(radarLayout, radarLayout.cols, rows, ids),
              );
            }}
            onReset={() => {
              persistRadarLayout(
                resetRadarLayout(
                  radars.map((c) => c.chart_id),
                  radarLayout.columnHeaders,
                ),
              );
            }}
          />
          <RadarLayoutGrid
            charts={radars}
            layout={radarLayout}
            compact
            onMove={(chartId, toSlot) => {
              const ids = radars.map((c) => c.chart_id);
              persistRadarLayout(
                moveRadarChart(radarLayout, chartId, toSlot, ids),
              );
            }}
            onColumnHeaderChange={(col, text) => {
              persistRadarLayout(setRadarColumnHeader(radarLayout, col, text), {
                quiet: true,
              });
            }}
            renderChart={(chart) => (
              <RadarStatChart
                chart={chart}
                compact
                scaleMode={radarScaleMode}
                thresholdPct={radarThresholdPct}
              />
            )}
          />
        </>
      ) : null}
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

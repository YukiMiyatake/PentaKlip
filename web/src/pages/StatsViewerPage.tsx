import { useCallback, useEffect, useMemo, useState } from "react";
import {
  aggregateStatsFolder,
  buildCharts,
  getDisplaySettings,
  getUiPreferences,
  putDisplaySettings,
} from "../api";
import { LaneCompareChart } from "../components/LaneCompareChart";
import { LaneFilterBar } from "../components/LaneFilterBar";
import { PlayerVisibilityBar } from "../components/PlayerVisibilityBar";
import { RadarLayoutControls } from "../components/RadarLayoutControls";
import { RadarLayoutGrid } from "../components/RadarLayoutGrid";
import { RadarStatChart } from "../components/RadarStatChart";
import { RadarThresholdControl } from "../components/RadarThresholdControl";
import { StatChart } from "../components/StatChart";
import { StatTable } from "../components/StatTable";
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
  saveLaneFilter,
  type LaneFilter,
} from "../lanes";
import {
  encodeHiddenParam,
  excludedToHiddenSet,
  hiddenSetToExcluded,
  listPlayersFromAggregated,
  loadHiddenPlayers,
  playersForLaneFilter,
  saveHiddenPlayers,
} from "../playerVisibility";
import {
  RADAR_SCALE_MODE_DEFAULT,
  RADAR_THRESHOLD_DEFAULT,
  loadRadarScaleMode,
  loadRadarThresholdPct,
  saveRadarScaleMode,
  saveRadarThresholdPct,
  type RadarScaleMode,
} from "../radarScale";
import {
  notifyDisplaySettingsChanged,
  notifyViewFiltersChanged,
  subscribeDisplaySettingsChanged,
  subscribeOutputRootChanged,
  subscribeViewFiltersChanged,
} from "../sync";
import type { AggregatedReplayStats, ChartBundle, Position } from "../types";

function statsDirFromOutputRoot(root: string): string {
  const base = root.replace(/[/\\]+$/, "");
  const sep = root.includes("/") && !root.includes("\\") ? "/" : "\\";
  return `${base}${sep}stats`;
}

const POSITIONS: Position[] = [
  "TOP",
  "JUNGLE",
  "MIDDLE",
  "BOTTOM",
  "UTILITY",
  "UNKNOWN",
];

type Props = {
  /** When true, sync stats dir from saved output root. */
  active?: boolean;
};

export function StatsViewerPage({ active = true }: Props) {
  const [directory, setDirectory] = useState("");
  const [aggregated, setAggregated] = useState<AggregatedReplayStats | null>(
    null,
  );
  const [bundle, setBundle] = useState<ChartBundle | null>(null);
  const [meta, setMeta] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [laneFilter, setLaneFilter] = useState<LaneFilter>(() => loadLaneFilter());
  const [hiddenPlayers, setHiddenPlayers] = useState<Set<string>>(() =>
    loadHiddenPlayers(),
  );
  const [radarScaleMode, setRadarScaleMode] = useState<RadarScaleMode>(() =>
    loadRadarScaleMode(),
  );
  const [radarThresholdPct, setRadarThresholdPct] = useState(() =>
    loadRadarThresholdPct(),
  );
  const [radarLayout, setRadarLayout] = useState<RadarLayoutState>(() =>
    loadRadarLayout(),
  );

  const syncDirectoryFromPrefs = useCallback(async () => {
    const p = await getUiPreferences();
    if (p.last_output_root) {
      setDirectory(statsDirFromOutputRoot(p.last_output_root));
      return;
    }
    if (p.last_events_dir) {
      setDirectory(p.last_events_dir);
    }
  }, []);

  useEffect(() => {
    if (!active) return;
    void syncDirectoryFromPrefs().catch(() => {
      /* optional */
    });
  }, [active, syncDirectoryFromPrefs]);

  useEffect(() => {
    return subscribeOutputRootChanged(() => {
      void syncDirectoryFromPrefs().catch(() => {
        /* optional */
      });
    });
  }, [syncDirectoryFromPrefs]);

  const rebuildCharts = useCallback(async (agg: AggregatedReplayStats) => {
    const charts = await buildCharts(agg);
    setBundle(charts);
    return charts;
  }, []);

  useEffect(() => {
    return subscribeDisplaySettingsChanged(() => {
      if (!aggregated) return;
      void rebuildCharts(aggregated).catch((err) => setError(String(err)));
    });
  }, [aggregated, rebuildCharts]);

  function onLaneChange(next: LaneFilter) {
    setLaneFilter(next);
    saveLaneFilter(next);
    notifyViewFiltersChanged();
  }

  function onRadarScaleModeChange(next: RadarScaleMode) {
    setRadarScaleMode(next);
    saveRadarScaleMode(next);
    notifyViewFiltersChanged();
  }

  function onRadarThresholdChange(next: number) {
    setRadarThresholdPct(next);
    saveRadarThresholdPct(next);
    notifyViewFiltersChanged();
  }

  useEffect(() => {
    return subscribeViewFiltersChanged(() => {
      setRadarScaleMode(loadRadarScaleMode());
      setRadarThresholdPct(loadRadarThresholdPct());
      setRadarLayout(loadRadarLayout());
    });
  }, []);

  function persistRadarLayout(next: RadarLayoutState) {
    setRadarLayout(next);
    saveRadarLayout(next);
    notifyViewFiltersChanged();
  }

  async function persistExclusions(next: Set<string>, agg: AggregatedReplayStats) {
    const current = await getDisplaySettings();
    const fromHidden = hiddenSetToExcluded(next);
    const players = listPlayersFromAggregated(agg);
    const touched = new Set(players.map((p) => p.position));
    const merged: Partial<Record<Position, string[]>> = {
      ...(current.excluded_players_by_position ?? {}),
    };
    for (const position of POSITIONS) {
      if (!touched.has(position)) continue;
      merged[position] = fromHidden[position] ?? [];
    }
    await putDisplaySettings({
      ...current,
      excluded_players_by_position: merged,
    });
    notifyDisplaySettingsChanged();
  }

  async function onHiddenChange(next: Set<string>) {
    setHiddenPlayers(next);
    saveHiddenPlayers(next);
    notifyViewFiltersChanged();
    if (!aggregated) return;
    try {
      await persistExclusions(next, aggregated);
    } catch (err) {
      setError(String(err));
    }
  }

  async function resolveHiddenForAggregate(
    agg: AggregatedReplayStats,
  ): Promise<Set<string>> {
    try {
      const settings = await getDisplaySettings();
      const players = listPlayersFromAggregated(agg);
      const fromSettings = excludedToHiddenSet(
        settings.excluded_players_by_position,
        players,
      );
      if (
        fromSettings.size > 0 ||
        Object.values(settings.excluded_players_by_position ?? {}).some(
          (names) => (names?.length ?? 0) > 0,
        )
      ) {
        return fromSettings;
      }
    } catch {
      /* fall through */
    }
    return loadHiddenPlayers();
  }

  async function onFolderAggregate() {
    if (!directory.trim()) {
      setError("フォルダパスを入力してください");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await aggregateStatsFolder({
        directory: directory.trim(),
        apply_roster: true,
      });
      setAggregated(result.aggregated);
      const hidden = await resolveHiddenForAggregate(result.aggregated);
      setHiddenPlayers(hidden);
      saveHiddenPlayers(hidden);
      await persistExclusions(hidden, result.aggregated);
      const charts = await rebuildCharts(result.aggregated);
      const ssEnriched = Number(
        (result.aggregated.meta as { scoreboard_ss_enriched?: number } | undefined)
          ?.scoreboard_ss_enriched ?? 0,
      );
      setMeta(
        [
          `folder: ${result.directory}`,
          `games: ${result.game_count}`,
          `files: ${result.file_count}`,
          `duration avg: ${result.aggregated.game_duration_sec.toFixed(0)}s`,
          `charts: ${charts.charts.length}`,
          ssEnriched > 0 ? `OCR DMG: ${ssEnriched}` : null,
        ]
          .filter(Boolean)
          .join(" · "),
      );
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onFile(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const text = await file.text();
      const json = JSON.parse(text) as Record<string, unknown>;
      const next = extractAggregated(json);
      setAggregated(next);
      const hidden = await resolveHiddenForAggregate(next);
      setHiddenPlayers(hidden);
      saveHiddenPlayers(hidden);
      await persistExclusions(hidden, next);
      const charts = await rebuildCharts(next);
      setMeta(
        [
          next.original_match_id ? `match: ${next.original_match_id}` : null,
          `duration: ${next.game_duration_sec.toFixed(0)}s`,
          `charts: ${charts.charts.length}`,
        ]
          .filter(Boolean)
          .join(" · "),
      );
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  const players = useMemo(
    () => listPlayersFromAggregated(aggregated),
    [aggregated],
  );
  const playersInLane = useMemo(
    () => playersForLaneFilter(players, laneFilter),
    [players, laneFilter],
  );

  // Server already dropped excluded players from tables / averages / radars.
  const visible = useMemo(() => {
    const charts = bundle?.charts ?? [];
    return filterChartsByLane(charts, laneFilter);
  }, [bundle, laneFilter]);

  const compares = visible.filter((c) => c.chart_type === "lane_compare");
  const radars = visible.filter((c) => c.chart_type === "radar");
  const tables = visible.filter((c) => c.chart_type === "table");
  const lines = visible.filter((c) => c.chart_type === "line");

  const obsUrl = (() => {
    const u = new URL("/obs", window.location.origin);
    if (directory.trim()) u.searchParams.set("dir", directory.trim());
    u.searchParams.set("refresh", "30");
    if (laneFilter !== "ALL") u.searchParams.set("position", laneFilter);
    if (radarScaleMode !== RADAR_SCALE_MODE_DEFAULT) {
      u.searchParams.set("scale", radarScaleMode);
    }
    if (radarThresholdPct !== RADAR_THRESHOLD_DEFAULT) {
      u.searchParams.set("span", String(radarThresholdPct));
    }
    if (hiddenPlayers.size > 0) {
      u.searchParams.set("hide", encodeHiddenParam(hiddenPlayers));
    }
    return u.toString();
  })();

  return (
    <section className="panel">
      <h2>スタッツ</h2>

      <div className="result-box">
        <div className="row">
          <input
            className="text-input grow"
            placeholder="出力ベース\\stats"
            value={directory}
            onChange={(e) => setDirectory(e.target.value)}
          />
          <button
            className="btn primary"
            disabled={busy}
            onClick={() => void onFolderAggregate()}
          >
            {busy ? "集計中…" : "集計"}
          </button>
        </div>
        <p className="hint">自動切り分けの出力ベースを設定すると「出力ベース\stats」に追従します</p>
        <div className="row actions">
          <input
            type="file"
            accept=".json,application/json"
            disabled={busy}
            onChange={(event) => void onFile(event.target.files?.[0] ?? null)}
          />
          <a className="btn ghost" href={obsUrl} target="_blank" rel="noreferrer">
            OBS
          </a>
        </div>
      </div>
      {meta ? <p className="success">{meta}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      {bundle ? (
        <div className="lane-filter-row">
          <LaneFilterBar value={laneFilter} onChange={onLaneChange} />
          <span className="hint">
            {laneFilter === "ALL"
              ? `全 ${bundle.charts.length} チャート`
              : `${visible.length} / ${bundle.charts.length}`}
            {hiddenPlayers.size > 0
              ? ` · 計算除外 ${hiddenPlayers.size} 人`
              : ""}
          </span>
          <PlayerVisibilityBar
            players={playersInLane}
            hidden={hiddenPlayers}
            onChange={(next) => void onHiddenChange(next)}
          />
        </div>
      ) : null}

      {radars.length > 0 ? (
        <div className="radar-section" style={{ marginTop: 20 }}>
          <div className="section-title-row">
            <h3 className="section-title">レーダー</h3>
            <RadarThresholdControl
              mode={radarScaleMode}
              thresholdPct={radarThresholdPct}
              onModeChange={onRadarScaleModeChange}
              onThresholdChange={onRadarThresholdChange}
            />
          </div>
          <RadarLayoutControls
            layout={ensureRadarLayout(
              radarLayout,
              radars.map((c) => c.chart_id),
            )}
            onColsChange={(cols) => {
              const ids = radars.map((c) => c.chart_id);
              persistRadarLayout(resizeRadarLayout(radarLayout, cols, radarLayout.rows, ids));
            }}
            onRowsChange={(rows) => {
              const ids = radars.map((c) => c.chart_id);
              persistRadarLayout(resizeRadarLayout(radarLayout, radarLayout.cols, rows, ids));
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
            onMove={(chartId, toSlot) => {
              const ids = radars.map((c) => c.chart_id);
              persistRadarLayout(moveRadarChart(radarLayout, chartId, toSlot, ids));
            }}
            onColumnHeaderChange={(col, text) => {
              persistRadarLayout(setRadarColumnHeader(radarLayout, col, text));
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
        </div>
      ) : null}

      {compares.length > 0 ? (
        <div className="lane-compare-grid" style={{ marginTop: 20 }}>
          <h3 className="section-title">レーン別プレイヤー比較</h3>
          {compares.map((chart) => (
            <LaneCompareChart key={chart.chart_id} chart={chart} />
          ))}
        </div>
      ) : null}

      {tables.length > 0 ? (
        <div className="chart-grid" style={{ marginTop: 20 }}>
          <h3 className="section-title">テーブル</h3>
          {tables.map((chart) => (
            <StatTable key={chart.chart_id} chart={chart} />
          ))}
        </div>
      ) : null}

      {lines.length > 0 ? (
        <div className="chart-grid" style={{ marginTop: 16 }}>
          <h3 className="section-title">時系列</h3>
          {lines.map((chart) => (
            <StatChart key={chart.chart_id} chart={chart} />
          ))}
        </div>
      ) : null}

      {bundle && visible.length === 0 ? (
        <p className="hint" style={{ marginTop: 16 }}>
          このレーンのチャートはありません。
        </p>
      ) : null}
    </section>
  );
}

function extractAggregated(json: Record<string, unknown>): AggregatedReplayStats {
  if (json.aggregated && typeof json.aggregated === "object") {
    return json.aggregated as AggregatedReplayStats;
  }
  if (typeof json.game_duration_sec === "number" && Array.isArray(json.players)) {
    return json as unknown as AggregatedReplayStats;
  }
  throw new Error(
    "集計 JSON を認識できません。finalize の aggregated、または /api/stats/aggregate の結果を指定してください。",
  );
}

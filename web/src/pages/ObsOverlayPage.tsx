import { useCallback, useEffect, useMemo, useState } from "react";
import { aggregateStatsFolder, buildCharts, getUiPreferences } from "../api";
import { LaneFilterBar } from "../components/LaneFilterBar";
import { PlayerVisibilityBar } from "../components/PlayerVisibilityBar";
import { RadarStatChart } from "../components/RadarStatChart";
import {
  filterChartsByLane,
  normalizeLaneFilter,
  type LaneFilter,
} from "../lanes";
import {
  encodeHiddenParam,
  filterChartsByPlayerVisibility,
  listPlayersFromCharts,
  loadHiddenPlayers,
  parseHiddenParam,
  playersForLaneFilter,
  saveHiddenPlayers,
} from "../playerVisibility";
import type { ChartSpec } from "../types";

function params() {
  return new URLSearchParams(window.location.search);
}

function writeQuery(patch: {
  lane?: LaneFilter;
  hidden?: ReadonlySet<string>;
}) {
  const u = new URL(window.location.href);
  if (patch.lane !== undefined) {
    if (patch.lane === "ALL") u.searchParams.delete("position");
    else u.searchParams.set("position", patch.lane);
  }
  if (patch.hidden !== undefined) {
    if (patch.hidden.size === 0) u.searchParams.delete("hide");
    else u.searchParams.set("hide", encodeHiddenParam(patch.hidden));
  }
  window.history.replaceState({}, "", u);
}

export function ObsOverlayPage() {
  const q = useMemo(() => params(), []);
  const initialLane = normalizeLaneFilter(q.get("position"));
  const playerFilter = q.get("player");
  const refreshSec = Math.max(0, Number(q.get("refresh") || "0") || 0);
  const chroma = q.get("chroma"); // e.g. #00ff00 for chroma key
  const dirParam = q.get("dir");
  const hideFromUrl = parseHiddenParam(q.get("hide"));

  const [directory, setDirectory] = useState(dirParam ?? "");
  const [laneFilter, setLaneFilter] = useState<LaneFilter>(initialLane);
  const [hiddenPlayers, setHiddenPlayers] = useState<Set<string>>(() => {
    if (hideFromUrl.size > 0) return hideFromUrl;
    return loadHiddenPlayers();
  });
  const [allRadars, setAllRadars] = useState<ChartSpec[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const players = useMemo(() => listPlayersFromCharts(allRadars), [allRadars]);
  const playersInLane = useMemo(
    () => playersForLaneFilter(players, laneFilter),
    [players, laneFilter],
  );

  const radars = useMemo(() => {
    const byLane = filterChartsByLane(allRadars, laneFilter);
    return filterChartsByPlayerVisibility(byLane, hiddenPlayers);
  }, [allRadars, laneFilter, hiddenPlayers]);

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

  function onLaneChange(next: LaneFilter) {
    setLaneFilter(next);
    writeQuery({ lane: next });
  }

  function onHiddenChange(next: Set<string>) {
    setHiddenPlayers(next);
    saveHiddenPlayers(next);
    writeQuery({ hidden: next });
  }

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
          <span>
            {meta}
            {laneFilter !== "ALL" ? ` · ${laneFilter}` : ""}
            {playerFilter ? ` · player ${playerFilter}` : ""}
            {hiddenPlayers.size > 0 ? ` · hide ${hiddenPlayers.size}` : ""}
            {` · show ${radars.length}`}
          </span>
        ) : null}
        {busy ? <span>更新中…</span> : null}
        <button
          type="button"
          className="btn"
          disabled={busy || !directory}
          onClick={() => void load(directory)}
        >
          再読込
        </button>
        <PlayerVisibilityBar
          players={playersInLane}
          hidden={hiddenPlayers}
          onChange={onHiddenChange}
          compact
        />
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

import { LANE_FILTER_ORDER, type LaneFilter } from "./lanes";
import type { ChartSpec, Position } from "./types";

export type PlayerRef = {
  position: Position;
  player_id: string;
};

const STORAGE_KEY = "pentaklip.hiddenPlayerStats";

/** Charts that belong to one player's personal stats view. */
export function isPlayerStatChart(chart: ChartSpec): boolean {
  return chart.chart_type === "radar" || chart.chart_type === "line";
}

export function playerKey(position: string, playerId: string): string {
  return `${position}|${playerId}`;
}

export function parsePlayerKey(key: string): PlayerRef | null {
  const idx = key.indexOf("|");
  if (idx <= 0) return null;
  const position = key.slice(0, idx) as Position;
  const player_id = key.slice(idx + 1);
  if (!position || !player_id) return null;
  return { position, player_id };
}

export function chartFocusPlayer(chart: ChartSpec): PlayerRef | null {
  if (!isPlayerStatChart(chart)) return null;
  const position = (chart.position || "UNKNOWN") as Position;
  if (chart.chart_type === "radar") {
    const focus =
      chart.series.find((s) => s.key === "player") ?? chart.series[0];
    if (!focus?.player_id) return null;
    return { position, player_id: focus.player_id };
  }
  const focus = chart.series[0];
  if (!focus?.player_id) return null;
  return { position: (focus.position || position) as Position, player_id: focus.player_id };
}

/** Unique players that have personal radar/line charts, ordered by lane then name. */
export function listPlayersFromCharts(charts: ChartSpec[]): PlayerRef[] {
  const seen = new Map<string, PlayerRef>();
  for (const chart of charts) {
    const ref = chartFocusPlayer(chart);
    if (!ref) continue;
    const key = playerKey(ref.position, ref.player_id);
    if (!seen.has(key)) seen.set(key, ref);
  }
  const laneRank = new Map(
    LANE_FILTER_ORDER.map((p, i) => [p, i] as const),
  );
  return [...seen.values()].sort((a, b) => {
    const ra = laneRank.get(a.position) ?? 99;
    const rb = laneRank.get(b.position) ?? 99;
    if (ra !== rb) return ra - rb;
    return a.player_id.localeCompare(b.player_id, "ja");
  });
}

/**
 * Hide personal player charts (radar / line) for keys in `hidden`.
 * Table and lane_compare stay visible.
 */
export function filterChartsByPlayerVisibility(
  charts: ChartSpec[],
  hidden: ReadonlySet<string>,
): ChartSpec[] {
  if (hidden.size === 0) return charts;
  return charts.filter((chart) => {
    if (!isPlayerStatChart(chart)) return true;
    const ref = chartFocusPlayer(chart);
    if (!ref) return true;
    return !hidden.has(playerKey(ref.position, ref.player_id));
  });
}

export function playersForLaneFilter(
  players: PlayerRef[],
  lane: LaneFilter,
): PlayerRef[] {
  if (lane === "ALL") return players;
  return players.filter((p) => p.position === lane);
}

export function loadHiddenPlayers(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return new Set();
    return new Set(
      parsed.filter((v): v is string => typeof v === "string" && v.includes("|")),
    );
  } catch {
    return new Set();
  }
}

export function saveHiddenPlayers(hidden: ReadonlySet<string>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...hidden]));
  } catch {
    /* ignore quota / private mode */
  }
}

/** Encode hidden keys for OBS URL: hide=TOP%7CAlice,MIDDLE%7CBob */
export function encodeHiddenParam(hidden: ReadonlySet<string>): string {
  return [...hidden].sort().join(",");
}

export function parseHiddenParam(value: string | null | undefined): Set<string> {
  if (!value?.trim()) return new Set();
  const out = new Set<string>();
  for (const part of value.split(",")) {
    const key = part.trim();
    if (key.includes("|")) out.add(key);
  }
  return out;
}

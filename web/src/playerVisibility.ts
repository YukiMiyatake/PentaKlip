import { LANE_FILTER_ORDER, type LaneFilter } from "./lanes";
import type {
  AggregatedReplayStats,
  ChartSpec,
  DisplaySettings,
  Position,
} from "./types";

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

function sortPlayerRefs(players: PlayerRef[]): PlayerRef[] {
  const laneRank = new Map(
    LANE_FILTER_ORDER.map((p, i) => [p, i] as const),
  );
  return [...players].sort((a, b) => {
    const ra = laneRank.get(a.position) ?? 99;
    const rb = laneRank.get(b.position) ?? 99;
    if (ra !== rb) return ra - rb;
    return a.player_id.localeCompare(b.player_id, "ja");
  });
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
  return sortPlayerRefs([...seen.values()]);
}

/** Prefer aggregated roster so excluded players stay toggleable. */
export function listPlayersFromAggregated(
  aggregated: AggregatedReplayStats | null | undefined,
): PlayerRef[] {
  const seen = new Map<string, PlayerRef>();
  for (const player of aggregated?.players ?? []) {
    if (!player?.player_id || !player.position) continue;
    const ref: PlayerRef = {
      position: player.position,
      player_id: player.player_id,
    };
    const key = playerKey(ref.position, ref.player_id);
    if (!seen.has(key)) seen.set(key, ref);
  }
  return sortPlayerRefs([...seen.values()]);
}

export function exclusionName(playerId: string): string {
  const trimmed = playerId.trim();
  if (!trimmed.includes("#")) return trimmed;
  return trimmed.split("#", 1)[0]?.trim() || trimmed;
}

export function hiddenSetToExcluded(
  hidden: ReadonlySet<string>,
): Partial<Record<Position, string[]>> {
  const buckets = new Map<Position, string[]>();
  const seen = new Map<Position, Set<string>>();
  for (const key of hidden) {
    const ref = parsePlayerKey(key);
    if (!ref) continue;
    const name = exclusionName(ref.player_id);
    if (!name) continue;
    const fold = name.toLowerCase();
    const used = seen.get(ref.position) ?? new Set<string>();
    if (used.has(fold)) continue;
    used.add(fold);
    seen.set(ref.position, used);
    const list = buckets.get(ref.position) ?? [];
    list.push(name);
    buckets.set(ref.position, list);
  }
  return Object.fromEntries(buckets) as Partial<Record<Position, string[]>>;
}

export function excludedToHiddenSet(
  excluded: DisplaySettings["excluded_players_by_position"] | undefined,
  players: PlayerRef[],
): Set<string> {
  const hidden = new Set<string>();
  if (!excluded) return hidden;
  for (const ref of players) {
    const aliases = excluded[ref.position] ?? [];
    if (aliases.length === 0) continue;
    const obs = exclusionName(ref.player_id).toLowerCase();
    const hit = aliases.some((alias) => {
      const a = exclusionName(alias).toLowerCase();
      return a === obs || obs.includes(a) || a.includes(obs);
    });
    if (hit) hidden.add(playerKey(ref.position, ref.player_id));
  }
  return hidden;
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

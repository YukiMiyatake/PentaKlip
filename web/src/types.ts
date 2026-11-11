export type Position =
  | "TOP"
  | "JUNGLE"
  | "MIDDLE"
  | "BOTTOM"
  | "UTILITY"
  | "UNKNOWN";

export type StatKeyInfo = {
  key: string;
  label: string;
};

export type Catalog = {
  positions: Position[];
  table_stat_keys: StatKeyInfo[];
  series_stat_keys: StatKeyInfo[];
  all_stat_keys: StatKeyInfo[];
};

export type DisplaySettings = {
  table_by_position: Partial<Record<Position, string[]>>;
  charts_by_position: Partial<Record<Position, string[]>>;
};

export type TimePoint = {
  game_time_sec: number;
  value: number;
};

export type ChartSeries = {
  key: string;
  label: string;
  player_id: string;
  position: Position;
  points: TimePoint[];
  value?: string | number | boolean | null;
};

export type ChartSpec = {
  chart_id: string;
  chart_type: "line" | "bar" | "table" | string;
  title: string;
  position?: Position | null;
  series: ChartSeries[];
  columns: string[];
  rows: Record<string, unknown>[];
};

export type ChartBundle = {
  charts: ChartSpec[];
  display_settings_applied: Record<string, string[]>;
};

export type AggregatedReplayStats = {
  schema_version: number;
  original_match_id?: string | null;
  local_replay_id?: string | null;
  game_duration_sec: number;
  players: unknown[];
  team_totals?: Record<string, Record<string, number>>;
  meta?: Record<string, unknown>;
};

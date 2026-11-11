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
  roster_by_position?: Partial<Record<Position, string[]>>;
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

export type RoflOverview = {
  path: string;
  filename: string;
  match_id?: string | null;
  match_id_source?: "meta" | "meta_fingerprint" | "filename" | null;
  format?: string | null;
  game_version?: string | null;
  game_length_ms?: number | null;
  game_length_sec?: number | null;
  game_mode?: string | null;
  map_name?: string | null;
  is_practice_tool?: boolean | null;
  player_count?: number | null;
  players: string[];
  size_bytes: number;
  note?: string | null;
};

export type UiPreferences = {
  fixed_target_rofl: string | null;
  last_source_dir: string | null;
  last_video_dir: string | null;
  last_events_dir: string | null;
  last_output_root: string | null;
  last_game_id: string | null;
};

export type FsEntry = {
  name: string;
  path: string;
  is_dir: boolean;
  size_bytes?: number | null;
  suffix?: string | null;
};

export type LocalReplayItem = {
  path: string;
  filename: string;
  match_id: string | null;
  size_bytes: number;
};

export type FfmpegStatus = {
  found: boolean;
  path?: string | null;
  version_line?: string | null;
  on_path: boolean;
  hints: string[];
};

export type FfmpegQuality = "light" | "standard" | "high";

export type FfmpegEncoder = "auto" | "nvenc" | "qsv" | "amf" | "cpu";

export type FfmpegSettings = {
  ffmpeg_path: string | null;
  quality: FfmpegQuality;
  encoder: FfmpegEncoder;
  auto_convert_webm: boolean;
  available_encoders?: FfmpegEncoder[];
  effective_encoder?: FfmpegEncoder;
  effective_codec?: string;
};

export type EventsLiveStatus = {
  available: boolean;
  events: Record<string, unknown>[];
  event_count: number;
  game_time_sec?: number | null;
  game_id?: string | null;
  player_count?: number | null;
  source: string;
  error?: string | null;
  warning?: string | null;
};

export type EventsExportResult = {
  path: string;
  event_count: number;
  game_id: string;
  game_dir: string;
  game_time_sec?: number | null;
  source: string;
  stats_bundle_path?: string | null;
  stats_aggregated_path?: string | null;
  player_count?: number | null;
};

export type CreateClipsResponse = {
  source_video: string;
  output_dir: string;
  clip_count: number;
  clips: Array<{
    kind: string;
    label?: string | null;
    game_time_sec: number;
    start_sec: number;
    end_sec: number;
    output_path: string;
  }>;
  game_id?: string | null;
  original_source_video?: string | null;
  converted?: boolean;
  event_coverage?: {
    total_events?: number;
    by_name?: Record<string, number>;
    used_for_clips?: Record<string, number>;
    ignored?: Record<string, number>;
    clip_event_names?: string[];
  } | null;
};

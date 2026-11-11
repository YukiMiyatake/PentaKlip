import type {
  AggregatedReplayStats,
  Catalog,
  ChartBundle,
  CreateClipsResponse,
  DisplaySettings,
  EventsExportResult,
  EventsLiveStatus,
  FfmpegStatus,
  FsEntry,
  LocalReplayItem,
  RoflOverview,
  UiPreferences,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export function getCatalog(): Promise<Catalog> {
  return request("/api/stats/catalog");
}

export function getDisplaySettings(): Promise<DisplaySettings> {
  return request("/api/stats/display-settings");
}

export function putDisplaySettings(
  settings: DisplaySettings,
): Promise<DisplaySettings> {
  return request("/api/stats/display-settings", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}

export function resetDisplaySettings(): Promise<DisplaySettings> {
  return request("/api/stats/display-settings/reset", { method: "POST" });
}

export function buildCharts(
  aggregated: AggregatedReplayStats,
  display?: DisplaySettings | null,
): Promise<ChartBundle> {
  return request("/api/stats/charts", {
    method: "POST",
    body: JSON.stringify({
      aggregated,
      display: display ?? null,
    }),
  });
}

export function getHealth(): Promise<{ status: string; version: string }> {
  return request("/api/health");
}

export function getUiPreferences(): Promise<UiPreferences> {
  return request("/api/ui/preferences");
}

export function putUiPreferences(prefs: UiPreferences): Promise<UiPreferences> {
  return request("/api/ui/preferences", {
    method: "PUT",
    body: JSON.stringify(prefs),
  });
}

export function listLocalReplays(): Promise<LocalReplayItem[]> {
  return request("/api/replays/local");
}

export function inspectRofl(path: string): Promise<RoflOverview> {
  return request(`/api/replays/inspect?path=${encodeURIComponent(path)}`);
}

export function installReplay(body: {
  source_path: string;
  local_replay_id: string;
  mode?: "copy" | "move" | "rename_in_place";
  dry_run?: boolean;
}): Promise<{
  original_match_id: string;
  local_replay_id: string;
  installed_path: string;
  overwritten: boolean;
  replay_db_id?: number | null;
}> {
  return request("/api/replays/install", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listDir(
  directory: string,
  suffixes?: string[],
): Promise<{ directory: string; entries: FsEntry[] }> {
  return request("/api/fs/list", {
    method: "POST",
    body: JSON.stringify({ directory, suffixes: suffixes ?? null }),
  });
}

export function getFfmpegStatus(): Promise<FfmpegStatus> {
  return request("/api/tools/ffmpeg");
}

export function installFfmpeg(): Promise<{
  ok?: boolean;
  returncode: number;
  stdout: string;
  stderr: string;
  status: FfmpegStatus;
}> {
  return request("/api/tools/ffmpeg/install", { method: "POST" });
}

export function addFfmpegToPath(): Promise<FfmpegStatus> {
  return request("/api/tools/ffmpeg/add-to-path", { method: "POST" });
}

export function getLiveEvents(): Promise<EventsLiveStatus> {
  return request("/api/events/live");
}

export function exportEvents(body: {
  output_path?: string | null;
  directory?: string | null;
  filename?: string | null;
  events?: Record<string, unknown>[] | null;
  game_time_sec?: number | null;
  source?: string;
}): Promise<EventsExportResult> {
  return request("/api/events/export", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function autoSplitClips(body: {
  source_video_path: string;
  events?: unknown[];
  events_path?: string | null;
  padding_before_sec?: number;
  padding_after_sec?: number;
  original_match_id?: string | null;
  dry_run?: boolean;
}): Promise<CreateClipsResponse> {
  return request("/api/clips/auto-split", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

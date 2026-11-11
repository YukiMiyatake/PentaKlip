import type {
  AggregatedReplayStats,
  Catalog,
  ChartBundle,
  DisplaySettings,
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

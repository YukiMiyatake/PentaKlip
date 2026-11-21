import type { ChartSpec, Position } from "./types";

type SavePickerWindow = Window & {
  showSaveFilePicker?: (options?: {
    suggestedName?: string;
    types?: Array<{
      description?: string;
      accept: Record<string, string[]>;
    }>;
  }) => Promise<{
    createWritable: () => Promise<{
      write: (data: Blob) => Promise<void>;
      close: () => Promise<void>;
    }>;
  }>;
};

function asNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function asString(value: unknown): string {
  if (value == null) return "";
  return String(value);
}

/** RFC4180 cell escape. */
function csvCell(value: string | number | null | undefined): string {
  if (value == null) return "";
  const text = String(value);
  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

type StatRow = {
  position: string;
  statKey: string;
  stat: string;
  laneAvg: number | null;
  byPlayer: Map<string, number | null>;
};

/**
 * Wide CSV: one row per stat axis, columns = lane_avg + each player raw value.
 * Built from visible OBS radar charts (same set as on screen).
 */
export function buildObsStatsCsv(radars: ChartSpec[]): string {
  const playersOrdered: string[] = [];
  const seenPlayers = new Set<string>();
  const rowsByKey = new Map<string, StatRow>();
  const statOrder: string[] = [];

  for (const chart of radars) {
    const playerSeries = chart.series.find((s) => s.key === "player");
    const playerId = playerSeries?.player_id?.trim();
    if (!playerSeries || !playerId) continue;
    if (!seenPlayers.has(playerId)) {
      seenPlayers.add(playerId);
      playersOrdered.push(playerId);
    }

    const position = (chart.position ??
      playerSeries.position ??
      "UNKNOWN") as Position;

    for (const row of chart.rows) {
      const statKey = asString(row.stat_key).trim();
      if (!statKey) continue;
      const mapKey = `${position}\u0001${statKey}`;
      let entry = rowsByKey.get(mapKey);
      if (!entry) {
        entry = {
          position,
          statKey,
          stat: asString(row.axis) || statKey,
          laneAvg: null,
          byPlayer: new Map(),
        };
        rowsByKey.set(mapKey, entry);
        statOrder.push(mapKey);
      }
      if (entry.laneAvg == null) {
        entry.laneAvg = asNumber(row.baseline);
      }
      if (!entry.byPlayer.has(playerId)) {
        entry.byPlayer.set(playerId, asNumber(row.player));
      }
    }
  }

  const header = [
    "position",
    "stat_key",
    "stat",
    "lane_avg",
    ...playersOrdered,
  ];
  const lines: string[] = [header.map(csvCell).join(",")];

  for (const mapKey of statOrder) {
    const entry = rowsByKey.get(mapKey);
    if (!entry) continue;
    const cells: Array<string | number | null> = [
      entry.position,
      entry.statKey,
      entry.stat,
      entry.laneAvg,
      ...playersOrdered.map((id) =>
        entry.byPlayer.has(id) ? (entry.byPlayer.get(id) ?? null) : null,
      ),
    ];
    lines.push(cells.map(csvCell).join(","));
  }

  // BOM for Excel JP
  return `\uFEFF${lines.join("\r\n")}\r\n`;
}

export async function saveTextFile(
  content: string,
  suggestedName: string,
  mime: string,
): Promise<void> {
  const blob = new Blob([content], { type: mime });
  const w = window as SavePickerWindow;
  if (typeof w.showSaveFilePicker === "function") {
    try {
      const handle = await w.showSaveFilePicker({
        suggestedName,
        types: [
          {
            description: "CSV",
            accept: { "text/csv": [".csv"] },
          },
        ],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      throw err;
    }
  }

  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = suggestedName;
    a.click();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function exportObsStatsCsv(radars: ChartSpec[]): Promise<void> {
  if (radars.length === 0) {
    throw new Error("出力するレーダーがありません");
  }
  const csv = buildObsStatsCsv(radars);
  await saveTextFile(csv, defaultObsCsvName(), "text/csv;charset=utf-8");
}

export function defaultObsCsvName(): string {
  const stamp = new Date()
    .toISOString()
    .slice(0, 19)
    .replace(/[:T]/g, (ch) => (ch === "T" ? "_" : ch === ":" ? "" : "-"));
  return `pentaklip-obs-stats-${stamp}.csv`;
}

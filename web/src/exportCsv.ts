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

type PositionCsv = {
  position: string;
  /** Display labels in axis order (CSM, KDA, …). */
  statLabels: string[];
  /** Parallel to statLabels. */
  statKeys: string[];
  players: string[];
  laneAvgLabel: string;
  laneAvg: Map<string, number | null>;
  /** playerId → (statKey → value) */
  byPlayer: Map<string, Map<string, number | null>>;
};

/**
 * Player-row CSV: header = stats; rows = lane average then each player.
 * Built from visible OBS radar charts (same set as on screen).
 */
export function buildObsStatsCsv(radars: ChartSpec[]): string {
  const byPosition = new Map<string, PositionCsv>();
  const positionOrder: string[] = [];

  for (const chart of radars) {
    const playerSeries = chart.series.find((s) => s.key === "player");
    const playerId = playerSeries?.player_id?.trim();
    if (!playerSeries || !playerId) continue;

    const position = String(
      chart.position ?? playerSeries.position ?? "UNKNOWN",
    ) as Position;
    let bucket = byPosition.get(position);
    if (!bucket) {
      const baseline = chart.series.find((s) => s.key === "baseline");
      bucket = {
        position,
        statLabels: [],
        statKeys: [],
        players: [],
        laneAvgLabel: baseline?.label?.trim() || "レーン平均",
        laneAvg: new Map(),
        byPlayer: new Map(),
      };
      byPosition.set(position, bucket);
      positionOrder.push(position);
    }

    if (!bucket.players.includes(playerId)) {
      bucket.players.push(playerId);
    }
    if (!bucket.byPlayer.has(playerId)) {
      bucket.byPlayer.set(playerId, new Map());
    }
    const playerMap = bucket.byPlayer.get(playerId)!;

    for (const row of chart.rows) {
      const statKey = asString(row.stat_key).trim();
      if (!statKey) continue;
      const label = asString(row.axis).trim() || statKey;
      if (!bucket.statKeys.includes(statKey)) {
        bucket.statKeys.push(statKey);
        bucket.statLabels.push(label);
      }
      if (!bucket.laneAvg.has(statKey)) {
        bucket.laneAvg.set(statKey, asNumber(row.baseline));
      } else if (bucket.laneAvg.get(statKey) == null) {
        const avg = asNumber(row.baseline);
        if (avg != null) bucket.laneAvg.set(statKey, avg);
      }
      if (!playerMap.has(statKey)) {
        playerMap.set(statKey, asNumber(row.player));
      }
    }
  }

  // Union of stat columns across positions (stable first-seen order).
  const allStatKeys: string[] = [];
  const allStatLabels: string[] = [];
  for (const pos of positionOrder) {
    const bucket = byPosition.get(pos);
    if (!bucket) continue;
    for (let i = 0; i < bucket.statKeys.length; i += 1) {
      const key = bucket.statKeys[i]!;
      if (allStatKeys.includes(key)) continue;
      allStatKeys.push(key);
      allStatLabels.push(bucket.statLabels[i] || key);
    }
  }

  const header = ["position", "player", ...allStatLabels];
  const lines: string[] = [header.map(csvCell).join(",")];

  for (const pos of positionOrder) {
    const bucket = byPosition.get(pos);
    if (!bucket) continue;

    const avgCells: Array<string | number | null> = [
      bucket.position,
      bucket.laneAvgLabel,
      ...allStatKeys.map((key) => bucket.laneAvg.get(key) ?? null),
    ];
    lines.push(avgCells.map(csvCell).join(","));

    for (const playerId of bucket.players) {
      const vals = bucket.byPlayer.get(playerId);
      const cells: Array<string | number | null> = [
        bucket.position,
        playerId,
        ...allStatKeys.map((key) => vals?.get(key) ?? null),
      ];
      lines.push(cells.map(csvCell).join(","));
    }
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

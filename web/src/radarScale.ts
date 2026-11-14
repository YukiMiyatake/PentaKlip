/**
 * Client-side radar remapping. Server still sends raw values + peak;
 * UI chooses how those map onto the [0, 1] chart domain.
 */

export const RADAR_THRESHOLD_STORAGE_KEY = "pentaklip.radarThresholdPct";
export const RADAR_SCALE_MODE_STORAGE_KEY = "pentaklip.radarScaleMode";

export const RADAR_THRESHOLD_MIN = 5;
export const RADAR_THRESHOLD_MAX = 100;
export const RADAR_THRESHOLD_DEFAULT = 30;
export const RADAR_THRESHOLD_STEP = 5;

/** Average pinned near the outer ring in `avg_outer` mode. */
const AVG_OUTER_RING = 0.75;

export type RadarScaleMode = "peak" | "center" | "full" | "avg_outer";

export const RADAR_SCALE_MODE_ORDER: RadarScaleMode[] = [
  "peak",
  "center",
  "avg_outer",
  "full",
];

export const RADAR_SCALE_MODE_LABELS: Record<RadarScaleMode, string> = {
  peak: "最大基準",
  center: "平均中心",
  avg_outer: "平均外周",
  full: "従来",
};

export const RADAR_SCALE_MODE_HINTS: Record<RadarScaleMode, string> = {
  peak: "最大を外周に置き、上側 N% だけ拡大（現行）",
  center: "平均を中央に置き、±N% を全体に拡大（前回）",
  avg_outer: "平均を外側リングに固定し、±N% で差を強調（大きく見えやすい）",
  full: "0〜最大の従来スケール（スレッショルドなし）",
};

export const RADAR_SCALE_MODE_DEFAULT: RadarScaleMode = "peak";

export type RadarScaleRow = {
  player?: number | null;
  baseline?: number | null;
  lower_is_better?: boolean;
  signed?: boolean;
  max?: number | null;
  player_norm?: number | null;
  baseline_norm?: number | null;
};

export function clampRadarThresholdPct(value: number): number {
  if (!Number.isFinite(value)) return RADAR_THRESHOLD_DEFAULT;
  const stepped =
    Math.round(value / RADAR_THRESHOLD_STEP) * RADAR_THRESHOLD_STEP;
  return Math.min(
    RADAR_THRESHOLD_MAX,
    Math.max(RADAR_THRESHOLD_MIN, stepped),
  );
}

export function normalizeRadarThresholdPct(
  value: string | number | null | undefined,
): number {
  if (value == null || value === "") return RADAR_THRESHOLD_DEFAULT;
  const n = typeof value === "number" ? value : Number(value);
  return clampRadarThresholdPct(n);
}

export function normalizeRadarScaleMode(
  value: string | null | undefined,
): RadarScaleMode {
  if (!value) return RADAR_SCALE_MODE_DEFAULT;
  const key = value.trim().toLowerCase().replace(/-/g, "_");
  if ((RADAR_SCALE_MODE_ORDER as string[]).includes(key)) {
    return key as RadarScaleMode;
  }
  // URL / legacy aliases
  if (key === "floor" || key === "peak_floor") return "peak";
  if (key === "avg" || key === "avg_center" || key === "middle") return "center";
  if (key === "classic" || key === "zero" || key === "max") return "full";
  if (key === "outer" || key === "avg_ring") return "avg_outer";
  return RADAR_SCALE_MODE_DEFAULT;
}

export function loadRadarThresholdPct(): number {
  try {
    return normalizeRadarThresholdPct(
      localStorage.getItem(RADAR_THRESHOLD_STORAGE_KEY),
    );
  } catch {
    return RADAR_THRESHOLD_DEFAULT;
  }
}

export function saveRadarThresholdPct(pct: number): void {
  try {
    localStorage.setItem(
      RADAR_THRESHOLD_STORAGE_KEY,
      String(clampRadarThresholdPct(pct)),
    );
  } catch {
    /* ignore */
  }
}

export function loadRadarScaleMode(): RadarScaleMode {
  try {
    return normalizeRadarScaleMode(
      localStorage.getItem(RADAR_SCALE_MODE_STORAGE_KEY),
    );
  } catch {
    return RADAR_SCALE_MODE_DEFAULT;
  }
}

export function saveRadarScaleMode(mode: RadarScaleMode): void {
  try {
    localStorage.setItem(RADAR_SCALE_MODE_STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}

/** Modes that use the threshold slider. */
export function radarScaleUsesThreshold(mode: RadarScaleMode): boolean {
  return mode !== "full";
}

export function radarScaleTag(
  mode: RadarScaleMode,
  thresholdPct: number,
): string {
  const label = RADAR_SCALE_MODE_LABELS[mode];
  if (!radarScaleUsesThreshold(mode)) return label;
  if (mode === "center" || mode === "avg_outer") {
    return `${label} ±${thresholdPct}%`;
  }
  return `${label} ${thresholdPct}%`;
}

function asNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n));
}

function spanFromPct(thresholdPct: number): number {
  return Math.max(
    0.01,
    Math.min(1, clampRadarThresholdPct(thresholdPct) / 100),
  );
}

function mapSigned(
  value: number | null,
  peak: number,
  span: number,
): number {
  if (value == null) return 0.5;
  const half = peak * span;
  return clamp01((value + half) / (2 * half));
}

/** Current: outer = peak, floor = peak*(1-span). */
function normsPeakFloor(
  player: number | null,
  baseline: number | null,
  peak: number,
  span: number,
  lower: boolean,
): { player_norm: number; baseline_norm: number } {
  const floor = peak * (1 - span);
  const range = Math.max(peak - floor, 1e-9);
  const mapAbs = (v: number | null): number => {
    if (v == null) return 0;
    const ratio = clamp01((Math.abs(v) - floor) / range);
    return lower ? 1 - ratio : ratio;
  };
  return { player_norm: mapAbs(player), baseline_norm: mapAbs(baseline) };
}

/** Previous: baseline at 0.5, ±span of |baseline|. */
function normsAvgCenter(
  player: number | null,
  baseline: number | null,
  peak: number,
  span: number,
  lower: boolean,
): { player_norm: number; baseline_norm: number } {
  if (baseline == null) {
    return normsPeakFloor(player, baseline, peak, span, lower);
  }
  const ref = Math.abs(baseline) > 1e-9 ? Math.abs(baseline) : peak;
  const half = Math.max(ref * span, 1e-9);
  const map = (v: number | null): number => {
    if (v == null) return 0;
    const delta = lower ? baseline - v : v - baseline;
    return clamp01(0.5 + 0.5 * (delta / half));
  };
  return { player_norm: map(player), baseline_norm: 0.5 };
}

/**
 * Baseline fixed near outer ring; deviations use ±span of |baseline|.
 * Keeps polygons large while still comparing to average.
 */
function normsAvgOuter(
  player: number | null,
  baseline: number | null,
  peak: number,
  span: number,
  lower: boolean,
): { player_norm: number; baseline_norm: number } {
  if (baseline == null) {
    return normsPeakFloor(player, baseline, peak, span, lower);
  }
  const ref = Math.abs(baseline) > 1e-9 ? Math.abs(baseline) : peak;
  const half = Math.max(ref * span, 1e-9);
  const ring = AVG_OUTER_RING;
  const map = (v: number | null): number => {
    if (v == null) return 0;
    const delta = lower ? baseline - v : v - baseline;
    // At ±half → hit 0 or 1 while baseline stays at `ring`.
    const roomOut = 1 - ring;
    const roomIn = ring;
    if (delta >= 0) {
      return clamp01(ring + roomOut * (delta / half));
    }
    return clamp01(ring + roomIn * (delta / half));
  };
  return { player_norm: map(player), baseline_norm: ring };
}

/** Classic 0 → peak (threshold ignored). */
function normsFull(
  player: number | null,
  baseline: number | null,
  peak: number,
  lower: boolean,
): { player_norm: number; baseline_norm: number } {
  const mapAbs = (v: number | null): number => {
    if (v == null) return 0;
    const ratio = clamp01(Math.abs(v) / peak);
    return lower ? 1 - ratio : ratio;
  };
  return { player_norm: mapAbs(player), baseline_norm: mapAbs(baseline) };
}

export function radarNormsForScale(
  row: RadarScaleRow,
  mode: RadarScaleMode,
  thresholdPct: number,
): { player_norm: number; baseline_norm: number } {
  const span = spanFromPct(thresholdPct);
  const player = asNumber(row.player);
  const baseline = asNumber(row.baseline);
  const lower = Boolean(row.lower_is_better);
  const signed = Boolean(row.signed);
  const peak = Math.max(asNumber(row.max) ?? 0, 1e-9);

  if (signed) {
    const signedSpan = mode === "full" ? 1 : span;
    return {
      player_norm: mapSigned(player, peak, signedSpan),
      baseline_norm: mapSigned(baseline, peak, signedSpan),
    };
  }

  switch (mode) {
    case "center":
      return normsAvgCenter(player, baseline, peak, span, lower);
    case "avg_outer":
      return normsAvgOuter(player, baseline, peak, span, lower);
    case "full":
      return normsFull(player, baseline, peak, lower);
    case "peak":
    default:
      return normsPeakFloor(player, baseline, peak, span, lower);
  }
}

/** @deprecated Use radarNormsForScale with mode. */
export function radarNormsForThreshold(
  row: RadarScaleRow,
  thresholdPct: number,
): { player_norm: number; baseline_norm: number } {
  return radarNormsForScale(row, "peak", thresholdPct);
}

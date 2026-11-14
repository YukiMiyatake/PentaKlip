/** Radar display scale: expand ±threshold% around the baseline (avg). */

export const RADAR_THRESHOLD_STORAGE_KEY = "pentaklip.radarThresholdPct";
export const RADAR_THRESHOLD_MIN = 5;
export const RADAR_THRESHOLD_MAX = 100;
export const RADAR_THRESHOLD_DEFAULT = 30;
export const RADAR_THRESHOLD_STEP = 5;

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

function asNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n));
}

/**
 * Remap raw radar values so baseline sits at 0.5 and ±thresholdPct of the
 * reference fills the chart. Smaller threshold → more contrast near average.
 */
export function radarNormsForThreshold(
  row: RadarScaleRow,
  thresholdPct: number,
): { player_norm: number; baseline_norm: number } {
  const span = Math.max(
    0.01,
    Math.min(1, clampRadarThresholdPct(thresholdPct) / 100),
  );
  const player = asNumber(row.player);
  const baseline = asNumber(row.baseline);
  const lower = Boolean(row.lower_is_better);
  const signed = Boolean(row.signed);
  const peak = Math.max(asNumber(row.max) ?? 0, 1e-9);

  if (signed) {
    const half = peak * span;
    const mapSigned = (v: number | null): number => {
      if (v == null) return 0.5;
      return clamp01((v + half) / (2 * half));
    };
    return {
      player_norm: mapSigned(player),
      baseline_norm: mapSigned(baseline),
    };
  }

  if (baseline == null) {
    const mapAbs = (v: number | null): number => {
      if (v == null) return 0;
      const ratio = clamp01(Math.abs(v) / (peak * span));
      return lower ? 1 - ratio : ratio;
    };
    return {
      player_norm: mapAbs(player),
      baseline_norm: 0.5,
    };
  }

  const ref = Math.abs(baseline) > 1e-9 ? Math.abs(baseline) : peak;
  const half = Math.max(ref * span, 1e-9);

  const mapAroundBaseline = (v: number | null): number => {
    if (v == null) return 0;
    const delta = lower ? baseline - v : v - baseline;
    return clamp01(0.5 + 0.5 * (delta / half));
  };

  return {
    player_norm: mapAroundBaseline(player),
    baseline_norm: 0.5,
  };
}

import type { ChartSpec, Position } from "./types";

/** Lanes shown in viewer / OBS filters (UNKNOWN omitted). */
export const LANE_FILTER_ORDER: Position[] = [
  "TOP",
  "JUNGLE",
  "MIDDLE",
  "BOTTOM",
  "UTILITY",
];

export const LANE_FILTER_LABELS: Record<Position, string> = {
  TOP: "TOP",
  JUNGLE: "JG",
  MIDDLE: "MID",
  BOTTOM: "BOT",
  UTILITY: "SUP",
  UNKNOWN: "?",
};

export type LaneFilter = "ALL" | Position;

export function normalizeLaneFilter(value: string | null | undefined): LaneFilter {
  if (!value) return "ALL";
  const upper = value.trim().toUpperCase();
  if (!upper || upper === "ALL") return "ALL";
  if (upper === "SUPPORT" || upper === "SUP") return "UTILITY";
  if (upper === "JG" || upper === "JNG") return "JUNGLE";
  if (upper === "MID") return "MIDDLE";
  if (upper === "BOT" || upper === "ADC") return "BOTTOM";
  if ((LANE_FILTER_ORDER as string[]).includes(upper)) {
    return upper as Position;
  }
  return "ALL";
}

export function laneFilterLabel(filter: LaneFilter): string {
  if (filter === "ALL") return "ALL";
  return LANE_FILTER_LABELS[filter] ?? filter;
}

export function chartMatchesLane(chart: ChartSpec, filter: LaneFilter): boolean {
  if (filter === "ALL") return true;
  return (chart.position || "").toUpperCase() === filter;
}

export function filterChartsByLane(
  charts: ChartSpec[],
  filter: LaneFilter,
): ChartSpec[] {
  return charts.filter((chart) => chartMatchesLane(chart, filter));
}

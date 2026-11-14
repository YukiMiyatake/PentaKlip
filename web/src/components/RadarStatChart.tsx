import { memo, useMemo } from "react";
import {
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  RADAR_SCALE_MODE_DEFAULT,
  RADAR_THRESHOLD_DEFAULT,
  radarNormsForScale,
  radarScaleTag,
  type RadarScaleMode,
} from "../radarScale";
import type { ChartSpec } from "../types";

type Props = {
  chart: ChartSpec;
  compact?: boolean;
  scaleMode?: RadarScaleMode;
  /** Display window / contrast; ignored in `full` mode. */
  thresholdPct?: number;
};

export const RadarStatChart = memo(function RadarStatChart({
  chart,
  compact = false,
  scaleMode = RADAR_SCALE_MODE_DEFAULT,
  thresholdPct = RADAR_THRESHOLD_DEFAULT,
}: Props) {
  const player = chart.series.find((s) => s.key === "player") ?? chart.series[0];
  const baseline = chart.series.find((s) => s.key === "baseline") ?? chart.series[1];
  const data = useMemo(
    () =>
      chart.rows.map((row) => {
        const norms = radarNormsForScale(row, scaleMode, thresholdPct);
        return {
          axis: String(row.axis ?? row.stat_key ?? ""),
          player_norm: norms.player_norm,
          baseline_norm: norms.baseline_norm,
          player: row.player,
          baseline: row.baseline,
        };
      }),
    [chart.rows, scaleMode, thresholdPct],
  );

  const height = compact ? 300 : 340;

  return (
    <section className={`chart-card radar-card${compact ? " compact" : ""}`}>
      <h3>{chart.title}</h3>
      <p className="radar-legend-hint">
        <span className="radar-swatch fill" /> {player?.label ?? "Player"}
        <span className="radar-swatch dash" /> {baseline?.label ?? "Baseline"}
        <span className="radar-scale-tag mono">
          {radarScaleTag(scaleMode, thresholdPct)}
        </span>
      </p>
      <ResponsiveContainer width="100%" height={height}>
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="68%">
          <PolarGrid stroke="#3a4a42" />
          <PolarAngleAxis
            dataKey="axis"
            tick={{ fill: "#c5d4cb", fontSize: compact ? 11 : 12 }}
          />
          <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
          <Tooltip
            contentStyle={{
              background: "#171e1b",
              border: "1px solid #2d3b34",
              borderRadius: 8,
            }}
            formatter={(value, name, item) => {
              const row = item?.payload as {
                player?: number | null;
                baseline?: number | null;
              };
              if (name === (player?.label ?? "player")) {
                return [row?.player ?? value, player?.label ?? "player"];
              }
              return [row?.baseline ?? value, baseline?.label ?? "baseline"];
            }}
          />
          <Radar
            name={player?.label ?? "player"}
            dataKey="player_norm"
            stroke="#b7f255"
            fill="#b7f255"
            fillOpacity={0.42}
            strokeWidth={2}
          />
          <Radar
            name={baseline?.label ?? "baseline"}
            dataKey="baseline_norm"
            stroke="#7ec8ff"
            fill="transparent"
            strokeWidth={2}
            strokeDasharray="5 4"
          />
          {!compact ? <Legend /> : null}
        </RadarChart>
      </ResponsiveContainer>
    </section>
  );
});

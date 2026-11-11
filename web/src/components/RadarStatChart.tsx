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
import type { ChartSpec } from "../types";

type Props = {
  chart: ChartSpec;
  compact?: boolean;
};

export function RadarStatChart({ chart, compact = false }: Props) {
  const player = chart.series.find((s) => s.key === "player") ?? chart.series[0];
  const baseline = chart.series.find((s) => s.key === "baseline") ?? chart.series[1];
  const data = chart.rows.map((row) => ({
    axis: String(row.axis ?? row.stat_key ?? ""),
    player_norm: Number(row.player_norm ?? 0),
    baseline_norm: Number(row.baseline_norm ?? 0),
    player: row.player,
    baseline: row.baseline,
  }));

  const height = compact ? 260 : 320;

  return (
    <section className={`chart-card radar-card${compact ? " compact" : ""}`}>
      <h3>{chart.title}</h3>
      <p className="radar-legend-hint">
        <span className="radar-swatch fill" /> {player?.label ?? "Player"}（塗り）
        <span className="radar-swatch dash" /> {baseline?.label ?? "Baseline"}（点線）
      </p>
      <ResponsiveContainer width="100%" height={height}>
        <RadarChart data={data} cx="50%" cy="52%" outerRadius="72%">
          <PolarGrid stroke="#3a4a42" />
          <PolarAngleAxis
            dataKey="axis"
            tick={{ fill: "#c5d4cb", fontSize: compact ? 11 : 12 }}
          />
          <PolarRadiusAxis
            domain={[0, 1]}
            tick={false}
            axisLine={false}
          />
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
}

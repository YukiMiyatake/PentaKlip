import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartSpec } from "../types";

type Props = {
  chart: ChartSpec;
};

export function StatChart({ chart }: Props) {
  const series = chart.series[0];
  const data =
    series?.points.map((point) => ({
      time: Number(point.game_time_sec.toFixed(1)),
      value: point.value,
    })) ?? [];

  return (
    <section className="chart-card">
      <h3>{chart.title}</h3>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#2d3b34" strokeDasharray="3 3" />
          <XAxis
            dataKey="time"
            stroke="#8fa399"
            tick={{ fill: "#8fa399", fontSize: 11 }}
            label={{ value: "sec", position: "insideBottomRight", fill: "#8fa399" }}
          />
          <YAxis stroke="#8fa399" tick={{ fill: "#8fa399", fontSize: 11 }} />
          <Tooltip
            contentStyle={{
              background: "#171e1b",
              border: "1px solid #2d3b34",
              borderRadius: 8,
            }}
          />
          <Line
            type="monotone"
            dataKey="value"
            name={series?.label ?? "value"}
            stroke="#b7f255"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </section>
  );
}

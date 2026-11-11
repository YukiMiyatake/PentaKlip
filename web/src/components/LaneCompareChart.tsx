import type { ChartSpec } from "../types";

type Props = {
  chart: ChartSpec;
};

const TEAM_COLORS = [
  { fill: "#3d9cf0", glow: "rgba(61, 156, 240, 0.35)" }, // ORDER-ish
  { fill: "#e85d4c", glow: "rgba(232, 93, 76, 0.35)" }, // CHAOS-ish
  { fill: "#c4a35a", glow: "rgba(196, 163, 90, 0.35)" },
  { fill: "#5ecf9a", glow: "rgba(94, 207, 154, 0.35)" },
  { fill: "#d97bc7", glow: "rgba(217, 123, 199, 0.28)" },
];

function teamColor(team: unknown, index: number): (typeof TEAM_COLORS)[number] {
  const t = String(team ?? "").toUpperCase();
  if (t === "ORDER" || t === "BLUE") return TEAM_COLORS[0];
  if (t === "CHAOS" || t === "RED" || t === "PURPLE") return TEAM_COLORS[1];
  return TEAM_COLORS[index % TEAM_COLORS.length];
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
  }
  return String(value);
}

type PlayerBar = {
  index: number;
  id: string;
  team: string | null;
  champion: string | null;
  value: number | null;
  color: (typeof TEAM_COLORS)[number];
};

function playersFromRow(row: Record<string, unknown>): PlayerBar[] {
  const count = Number(row.player_count ?? 0);
  const out: PlayerBar[] = [];
  for (let i = 0; i < count; i += 1) {
    const raw = row[`value_${i}`];
    const value = typeof raw === "number" ? raw : raw == null ? null : Number(raw);
    out.push({
      index: i,
      id: String(row[`player_${i}`] ?? `P${i + 1}`),
      team: row[`team_${i}`] != null ? String(row[`team_${i}`]) : null,
      champion: row[`champion_${i}`] != null ? String(row[`champion_${i}`]) : null,
      value: Number.isFinite(value as number) ? (value as number) : null,
      color: teamColor(row[`team_${i}`], i),
    });
  }
  return out;
}

export function LaneCompareChart({ chart }: Props) {
  const legend = chart.series.map((s, i) => ({
    id: s.player_id,
    team: s.value != null ? String(s.value) : null,
    color: teamColor(s.value, i),
  }));

  const twoPlayerMirror =
    legend.length === 2 &&
    legend[0]?.team &&
    legend[1]?.team &&
    legend[0].team.toUpperCase() !== legend[1].team.toUpperCase();

  return (
    <section className="chart-card lane-compare">
      <div className="lane-compare-head">
        <h3>{chart.title}</h3>
        <div className="lane-compare-legend">
          {legend.map((p) => (
            <span key={p.id} className="lane-compare-legend-item">
              <i style={{ background: p.color.fill }} />
              {p.id}
              {p.team ? <em>{p.team}</em> : null}
            </span>
          ))}
        </div>
      </div>

      <div className="lane-compare-rows">
        {chart.rows.map((row) => {
          const stat = String(row.stat ?? row.stat_key ?? "");
          const peak = Math.max(Number(row.max) || 1, 1e-6);
          const players = playersFromRow(row);

          if (twoPlayerMirror && players.length === 2) {
            const [left, right] = players;
            const leftPct = left.value == null ? 0 : (Math.abs(left.value) / peak) * 100;
            const rightPct = right.value == null ? 0 : (Math.abs(right.value) / peak) * 100;
            return (
              <div className="lane-compare-row mirror" key={`${chart.chart_id}-${stat}`}>
                <div className="lane-compare-stat">{stat}</div>
                <div className="lane-compare-mirror">
                  <span className="lane-compare-val left">{formatValue(left.value)}</span>
                  <div className="lane-compare-track mirror-track">
                    <div className="mirror-half left">
                      <div
                        className="lane-compare-fill"
                        style={{
                          width: `${leftPct}%`,
                          background: left.color.fill,
                          boxShadow: `0 0 12px ${left.color.glow}`,
                        }}
                      />
                    </div>
                    <div className="mirror-half right">
                      <div
                        className="lane-compare-fill"
                        style={{
                          width: `${rightPct}%`,
                          background: right.color.fill,
                          boxShadow: `0 0 12px ${right.color.glow}`,
                        }}
                      />
                    </div>
                  </div>
                  <span className="lane-compare-val right">{formatValue(right.value)}</span>
                </div>
              </div>
            );
          }

          return (
            <div className="lane-compare-row" key={`${chart.chart_id}-${stat}`}>
              <div className="lane-compare-stat">{stat}</div>
              <div className="lane-compare-bars">
                {players.map((p) => {
                  const pct = p.value == null ? 0 : (Math.abs(p.value) / peak) * 100;
                  return (
                    <div className="lane-compare-barline" key={`${stat}-${p.id}`}>
                      <span className="lane-compare-name" title={p.champion ?? undefined}>
                        {p.id}
                      </span>
                      <div className="lane-compare-track">
                        <div
                          className="lane-compare-fill"
                          style={{
                            width: `${pct}%`,
                            background: p.color.fill,
                            boxShadow: `0 0 12px ${p.color.glow}`,
                          }}
                        />
                      </div>
                      <span className="lane-compare-val">{formatValue(p.value)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

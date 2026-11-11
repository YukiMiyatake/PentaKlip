import type { ChartSpec } from "../types";

type Props = {
  chart: ChartSpec;
};

export function StatTable({ chart }: Props) {
  const columns = chart.columns.length
    ? chart.columns
    : Object.keys(chart.rows[0] ?? {});

  return (
    <section className="chart-card">
      <h3>{chart.title}</h3>
      <div className="table-wrap">
        <table className="stats">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {chart.rows.map((row, index) => (
              <tr key={`${chart.chart_id}-${index}`}>
                {columns.map((col) => (
                  <td key={col}>{formatCell(row[col])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return String(value);
}

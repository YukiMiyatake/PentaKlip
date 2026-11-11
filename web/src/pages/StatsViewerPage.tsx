import { useState } from "react";
import { buildCharts } from "../api";
import { StatChart } from "../components/StatChart";
import { StatTable } from "../components/StatTable";
import type { AggregatedReplayStats, ChartBundle } from "../types";

export function StatsViewerPage() {
  const [bundle, setBundle] = useState<ChartBundle | null>(null);
  const [meta, setMeta] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onFile(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setBundle(null);
    setMeta(null);
    try {
      const text = await file.text();
      const json = JSON.parse(text) as Record<string, unknown>;
      const aggregated = extractAggregated(json);
      const charts = await buildCharts(aggregated);
      setBundle(charts);
      setMeta(
        [
          aggregated.original_match_id
            ? `match: ${aggregated.original_match_id}`
            : null,
          `duration: ${aggregated.game_duration_sec.toFixed(0)}s`,
          `charts: ${charts.charts.length}`,
        ]
          .filter(Boolean)
          .join(" · "),
      );
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  const tables = bundle?.charts.filter((c) => c.chart_type === "table") ?? [];
  const lines = bundle?.charts.filter((c) => c.chart_type === "line") ?? [];

  return (
    <section className="panel">
      <h2>スタッツ表示</h2>
      <p className="hint">
        finalize / aggregate で得た JSON（`aggregated` オブジェクト、または集計結果そのもの）を読み込み、
        レーン別設定に従って表とグラフを描画します。
      </p>
      <div className="row file-input">
        <input
          type="file"
          accept=".json,application/json"
          disabled={busy}
          onChange={(event) => onFile(event.target.files?.[0] ?? null)}
        />
        {busy ? <span>処理中…</span> : null}
      </div>
      {meta ? <p className="success">{meta}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      {tables.length > 0 ? (
        <div className="chart-grid" style={{ marginTop: 20 }}>
          {tables.map((chart) => (
            <StatTable key={chart.chart_id} chart={chart} />
          ))}
        </div>
      ) : null}

      {lines.length > 0 ? (
        <div className="chart-grid" style={{ marginTop: 16 }}>
          {lines.map((chart) => (
            <StatChart key={chart.chart_id} chart={chart} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function extractAggregated(json: Record<string, unknown>): AggregatedReplayStats {
  if (json.aggregated && typeof json.aggregated === "object") {
    return json.aggregated as AggregatedReplayStats;
  }
  if (typeof json.game_duration_sec === "number" && Array.isArray(json.players)) {
    return json as unknown as AggregatedReplayStats;
  }
  throw new Error(
    "集計 JSON を認識できません。finalize の aggregated、または /api/stats/aggregate の結果を指定してください。",
  );
}

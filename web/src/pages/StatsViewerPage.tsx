import { useEffect, useState } from "react";
import { aggregateStatsFolder, buildCharts, getUiPreferences } from "../api";
import { LaneCompareChart } from "../components/LaneCompareChart";
import { RadarStatChart } from "../components/RadarStatChart";
import { StatChart } from "../components/StatChart";
import { StatTable } from "../components/StatTable";
import type { AggregatedReplayStats, ChartBundle } from "../types";

export function StatsViewerPage() {
  const [directory, setDirectory] = useState("");
  const [bundle, setBundle] = useState<ChartBundle | null>(null);
  const [meta, setMeta] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getUiPreferences()
      .then((p) => {
        if (p.last_output_root) {
          const base = p.last_output_root.replace(/[/\\]+$/, "");
          const sep = p.last_output_root.includes("/") && !p.last_output_root.includes("\\") ? "/" : "\\";
          setDirectory(`${base}${sep}stats`);
        } else if (p.last_events_dir) {
          setDirectory(p.last_events_dir);
        }
      })
      .catch(() => {
        /* optional */
      });
  }, []);

  async function onFolderAggregate() {
    if (!directory.trim()) {
      setError("フォルダパスを入力してください");
      return;
    }
    setBusy(true);
    setError(null);
    setBundle(null);
    setMeta(null);
    try {
      const result = await aggregateStatsFolder({
        directory: directory.trim(),
        apply_roster: true,
      });
      const charts = await buildCharts(result.aggregated);
      setBundle(charts);
      setMeta(
        [
          `folder: ${result.directory}`,
          `games: ${result.game_count}`,
          `files: ${result.file_count}`,
          `duration avg: ${result.aggregated.game_duration_sec.toFixed(0)}s`,
          `charts: ${charts.charts.length}`,
        ].join(" · "),
      );
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

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

  const compares =
    bundle?.charts.filter((c) => c.chart_type === "lane_compare") ?? [];
  const radars = bundle?.charts.filter((c) => c.chart_type === "radar") ?? [];
  const tables = bundle?.charts.filter((c) => c.chart_type === "table") ?? [];
  const lines = bundle?.charts.filter((c) => c.chart_type === "line") ?? [];

  const obsUrl = (() => {
    const u = new URL("/obs", window.location.origin);
    if (directory.trim()) u.searchParams.set("dir", directory.trim());
    u.searchParams.set("refresh", "30");
    return u.toString();
  })();

  return (
    <section className="panel">
      <h2>スタッツ</h2>

      <div className="result-box">
        <div className="row">
          <input
            className="text-input grow"
            placeholder="stats フォルダ"
            value={directory}
            onChange={(e) => setDirectory(e.target.value)}
          />
          <button className="btn primary" disabled={busy} onClick={() => onFolderAggregate()}>
            {busy ? "集計中…" : "集計"}
          </button>
        </div>
        <div className="row actions">
          <input
            type="file"
            accept=".json,application/json"
            disabled={busy}
            onChange={(event) => onFile(event.target.files?.[0] ?? null)}
          />
          <a className="btn ghost" href={obsUrl} target="_blank" rel="noreferrer">
            OBS
          </a>
        </div>
      </div>
      {meta ? <p className="success">{meta}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      {radars.length > 0 ? (
        <div className="radar-grid" style={{ marginTop: 20 }}>
          <h3 className="section-title">レーダー</h3>
          {radars.map((chart) => (
            <RadarStatChart key={chart.chart_id} chart={chart} />
          ))}
        </div>
      ) : null}

      {compares.length > 0 ? (
        <div className="lane-compare-grid" style={{ marginTop: 20 }}>
          <h3 className="section-title">レーン別プレイヤー比較</h3>
          {compares.map((chart) => (
            <LaneCompareChart key={chart.chart_id} chart={chart} />
          ))}
        </div>
      ) : null}

      {tables.length > 0 ? (
        <div className="chart-grid" style={{ marginTop: 20 }}>
          <h3 className="section-title">テーブル</h3>
          {tables.map((chart) => (
            <StatTable key={chart.chart_id} chart={chart} />
          ))}
        </div>
      ) : null}

      {lines.length > 0 ? (
        <div className="chart-grid" style={{ marginTop: 16 }}>
          <h3 className="section-title">時系列</h3>
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

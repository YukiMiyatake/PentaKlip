import { useEffect, useRef, useState } from "react";
import {
  getCatalog,
  getDisplaySettings,
  putDisplaySettings,
  resetDisplaySettings,
} from "../api";
import { notifyDisplaySettingsChanged } from "../sync";
import type { Catalog, DisplaySettings, Position } from "../types";

const POSITION_ORDER: Position[] = [
  "TOP",
  "JUNGLE",
  "MIDDLE",
  "BOTTOM",
  "UTILITY",
  "UNKNOWN",
];

const FALLBACK_POSITION_LABELS: Record<Position, string> = {
  TOP: "TOP",
  JUNGLE: "JUNGLE",
  MIDDLE: "MIDDLE",
  BOTTOM: "BOTTOM",
  UTILITY: "SUPPORT",
  UNKNOWN: "UNKNOWN",
};

const FALLBACK_RADAR_KEYS = [
  "cs_per_min",
  "kda_ratio",
  "kill_participation",
  "csd15",
  "lvld15",
  "dpm",
  "damage_share",
  "vision_per_min",
];

const AUTO_SAVE_MS = 350;

function positionLabel(position: Position, catalog: Catalog | null): string {
  return (
    catalog?.position_labels?.[position] ??
    FALLBACK_POSITION_LABELS[position] ??
    position
  );
}

export function DisplaySettingsPage() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [settings, setSettings] = useState<DisplaySettings | null>(null);
  const [draftNames, setDraftNames] = useState<Partial<Record<Position, string>>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const readyRef = useRef(false);
  const skipAutoSaveRef = useRef(true);
  const saveSeq = useRef(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [cat, disp] = await Promise.all([
          getCatalog(),
          getDisplaySettings(),
        ]);
        if (!cancelled) {
          setCatalog(cat);
          skipAutoSaveRef.current = true;
          setSettings(normalizeSettings(disp, cat));
          readyRef.current = true;
        }
      } catch (err) {
        if (!cancelled) setError(String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!readyRef.current || !settings || !catalog) return;
    if (skipAutoSaveRef.current) {
      skipAutoSaveRef.current = false;
      return;
    }
    const seq = ++saveSeq.current;
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          await putDisplaySettings(settings);
          if (seq !== saveSeq.current) return;
          setMessage("自動保存しました（スタッツ / OBS に反映）");
          setError(null);
          notifyDisplaySettingsChanged();
        } catch (err) {
          if (seq !== saveSeq.current) return;
          setError(String(err));
        }
      })();
    }, AUTO_SAVE_MS);
    return () => window.clearTimeout(timer);
  }, [settings, catalog]);

  function toggle(
    kind: "table_by_position" | "charts_by_position" | "radar_by_position",
    position: Position,
    key: string,
  ) {
    setSettings((prev) => {
      if (!prev) return prev;
      const current = new Set(prev[kind]?.[position] ?? []);
      if (current.has(key)) current.delete(key);
      else current.add(key);
      return {
        ...prev,
        [kind]: {
          ...(prev[kind] ?? {}),
          [position]: Array.from(current),
        },
      };
    });
  }

  function addRosterName(position: Position) {
    const raw = (draftNames[position] ?? "").trim();
    if (!raw || !settings) return;
    const name = raw.includes("#") ? raw.split("#", 1)[0].trim() : raw;
    if (!name) return;
    const existing = settings.roster_by_position?.[position] ?? [];
    if (existing.some((n) => n.toLowerCase() === name.toLowerCase())) {
      setDraftNames((d) => ({ ...d, [position]: "" }));
      return;
    }
    setSettings({
      ...settings,
      roster_by_position: {
        ...(settings.roster_by_position ?? {}),
        [position]: [...existing, name],
      },
    });
    setDraftNames((d) => ({ ...d, [position]: "" }));
  }

  function removeRosterName(position: Position, name: string) {
    if (!settings) return;
    const existing = settings.roster_by_position?.[position] ?? [];
    setSettings({
      ...settings,
      roster_by_position: {
        ...(settings.roster_by_position ?? {}),
        [position]: existing.filter((n) => n !== name),
      },
    });
  }

  async function onSaveNow() {
    if (!settings) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    saveSeq.current += 1;
    try {
      const saved = await putDisplaySettings(settings);
      skipAutoSaveRef.current = true;
      setSettings(normalizeSettings(saved, catalog));
      setMessage("表示設定・ロースターを保存しました");
      notifyDisplaySettingsChanged();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onReset() {
    setBusy(true);
    setError(null);
    setMessage(null);
    saveSeq.current += 1;
    try {
      const saved = await resetDisplaySettings();
      skipAutoSaveRef.current = true;
      setSettings(normalizeSettings(saved, catalog));
      setMessage("デフォルトに戻しました");
      notifyDisplaySettingsChanged();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!catalog || !settings) {
    return (
      <section className="panel">
        <h2>表示設定</h2>
        <p className="hint">{error ?? "読み込み中…"}</p>
      </section>
    );
  }

  const radarKeys = catalog.lck_radar_stat_keys?.length
    ? catalog.lck_radar_stat_keys
    : catalog.table_stat_keys.filter((s) => FALLBACK_RADAR_KEYS.includes(s.key));
  const radarKeySet = new Set(radarKeys.map((s) => s.key));
  const tableOptionalKeys = catalog.table_stat_keys.filter(
    (s) => !radarKeySet.has(s.key) && s.key !== "champion",
  );

  return (
    <section className="panel">
      <h2>表示設定</h2>
      <p className="hint">
        レーダー既定軸: CSM / KDA / KP% / CSD15 / LVLD15 / DPM / DMG% / VSPM。
        DPM・DMG% は OCR が無い試合では自動で軸から外します。CSD15 / LVLD15
        はデータが無くても軸として残ります。変更は自動保存され、スタッツ / OBS
        チャートへ即反映されます。
      </p>
      <div className="row actions">
        <button className="btn primary" disabled={busy} onClick={() => void onSaveNow()}>
          今すぐ保存
        </button>
        <button className="btn" disabled={busy} onClick={() => void onReset()}>
          デフォルトに戻す
        </button>
      </div>
      {message ? <p className="success">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <div className="lane-grid">
        {POSITION_ORDER.filter((p) => catalog.positions.includes(p)).map(
          (position) => (
            <article className="lane-card" key={position}>
              <h3>{positionLabel(position, catalog)}</h3>
              <div className="stat-group" style={{ marginBottom: 12 }}>
                <h4>プレイヤー名</h4>
                <div className="row" style={{ marginBottom: 8 }}>
                  <input
                    className="text-input grow"
                    placeholder="例: Tanaka"
                    value={draftNames[position] ?? ""}
                    onChange={(e) =>
                      setDraftNames((d) => ({ ...d, [position]: e.target.value }))
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addRosterName(position);
                      }
                    }}
                  />
                  <button
                    className="btn"
                    type="button"
                    onClick={() => addRosterName(position)}
                  >
                    追加
                  </button>
                </div>
                <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                  {(settings.roster_by_position?.[position] ?? []).map((name) => (
                    <button
                      key={`${position}-${name}`}
                      type="button"
                      className="btn"
                      onClick={() => removeRosterName(position, name)}
                      title="クリックで削除"
                    >
                      {name} ×
                    </button>
                  ))}
                </div>
              </div>
              <div className="stat-groups">
                <div className="stat-group">
                  <h4>Radar（最大8軸）</h4>
                  <div className="check-grid">
                    {radarKeys.map((stat) => (
                      <label key={`radar-${position}-${stat.key}`}>
                        <input
                          type="checkbox"
                          checked={(
                            settings.radar_by_position?.[position] ?? []
                          ).includes(stat.key)}
                          onChange={() =>
                            toggle("radar_by_position", position, stat.key)
                          }
                        />
                        {stat.label}
                      </label>
                    ))}
                  </div>
                  <div className="check-grid" style={{ marginTop: 8 }}>
                    {tableOptionalKeys
                      .filter((s) =>
                        ["cs_at_15", "ward_score", "objective_score", "tower_kills"].includes(
                          s.key,
                        ),
                      )
                      .map((stat) => (
                        <label key={`radar-opt-${position}-${stat.key}`}>
                          <input
                            type="checkbox"
                            checked={(
                              settings.radar_by_position?.[position] ?? []
                            ).includes(stat.key)}
                            onChange={() =>
                              toggle("radar_by_position", position, stat.key)
                            }
                          />
                          {stat.label}
                          <span className="hint"> opt</span>
                        </label>
                      ))}
                  </div>
                </div>
                <div className="stat-group">
                  <h4>Table / レーン比較</h4>
                  <div className="check-grid">
                    {catalog.table_stat_keys.map((stat) => (
                      <label key={`table-${position}-${stat.key}`}>
                        <input
                          type="checkbox"
                          checked={(
                            settings.table_by_position[position] ?? []
                          ).includes(stat.key)}
                          onChange={() =>
                            toggle("table_by_position", position, stat.key)
                          }
                        />
                        {stat.label}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="stat-group">
                  <h4>時系列 Charts</h4>
                  <div className="check-grid">
                    {catalog.series_stat_keys.map((stat) => (
                      <label key={`chart-${position}-${stat.key}`}>
                        <input
                          type="checkbox"
                          checked={(
                            settings.charts_by_position[position] ?? []
                          ).includes(stat.key)}
                          onChange={() =>
                            toggle("charts_by_position", position, stat.key)
                          }
                        />
                        {stat.label}
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            </article>
          ),
        )}
      </div>
    </section>
  );
}

function normalizeSettings(
  settings: DisplaySettings,
  catalog: Catalog | null,
): DisplaySettings {
  if (!catalog) return settings;
  const positions = catalog.positions;
  const table_by_position: DisplaySettings["table_by_position"] = {};
  const charts_by_position: DisplaySettings["charts_by_position"] = {};
  const radar_by_position: NonNullable<DisplaySettings["radar_by_position"]> = {};
  const roster_by_position: NonNullable<DisplaySettings["roster_by_position"]> = {};
  for (const position of positions) {
    table_by_position[position] = settings.table_by_position[position] ?? [];
    charts_by_position[position] = settings.charts_by_position[position] ?? [];
    radar_by_position[position] =
      settings.radar_by_position?.[position] ??
      catalog.lck_radar_stat_keys?.map((s) => s.key) ??
      FALLBACK_RADAR_KEYS;
    roster_by_position[position] = settings.roster_by_position?.[position] ?? [];
  }
  return {
    table_by_position,
    charts_by_position,
    radar_by_position,
    roster_by_position,
  };
}

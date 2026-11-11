import { useEffect, useState } from "react";
import {
  getCatalog,
  getDisplaySettings,
  putDisplaySettings,
  resetDisplaySettings,
} from "../api";
import type { Catalog, DisplaySettings, Position } from "../types";

const POSITION_ORDER: Position[] = [
  "TOP",
  "JUNGLE",
  "MIDDLE",
  "BOTTOM",
  "UTILITY",
  "UNKNOWN",
];

export function DisplaySettingsPage() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [settings, setSettings] = useState<DisplaySettings | null>(null);
  const [draftNames, setDraftNames] = useState<Partial<Record<Position, string>>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
          setSettings(normalizeSettings(disp, cat.positions));
        }
      } catch (err) {
        if (!cancelled) setError(String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function toggle(
    kind: "table_by_position" | "charts_by_position",
    position: Position,
    key: string,
  ) {
    setSettings((prev) => {
      if (!prev) return prev;
      const current = new Set(prev[kind][position] ?? []);
      if (current.has(key)) current.delete(key);
      else current.add(key);
      return {
        ...prev,
        [kind]: {
          ...prev[kind],
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

  async function onSave() {
    if (!settings) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await putDisplaySettings(settings);
      setSettings(normalizeSettings(saved, catalog?.positions ?? POSITION_ORDER));
      setMessage("表示設定・ロースターを保存しました");
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
    try {
      const saved = await resetDisplaySettings();
      setSettings(normalizeSettings(saved, catalog?.positions ?? POSITION_ORDER));
      setMessage("デフォルトに戻しました");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!catalog || !settings) {
    return (
      <section className="panel">
        <h2>スタッツ設定</h2>
        <p className="hint">{error ?? "読み込み中…"}</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>スタッツ設定</h2>
      <p className="hint">
        レーンごとの表示項目と、あいまい一致用のプレイヤー名（Riot ID のゲームネーム側。タグは無視）を登録します。
        例: <span className="mono">Tanaka</span> → <span className="mono">T1 Tanaka</span> /{" "}
        <span className="mono">T1 Tanakakun</span>
      </p>
      <div className="row" style={{ marginBottom: 16 }}>
        <button className="btn primary" disabled={busy} onClick={onSave}>
          保存
        </button>
        <button className="btn" disabled={busy} onClick={onReset}>
          デフォルトに戻す
        </button>
      </div>
      {message ? <p className="success">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <div className="lane-grid">
        {POSITION_ORDER.filter((p) => catalog.positions.includes(p)).map(
          (position) => (
            <article className="lane-card" key={position}>
              <h3>{position}</h3>
              <div className="stat-group" style={{ marginBottom: 12 }}>
                <h4>プレイヤー名（あいまい一致）</h4>
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
                  <button className="btn" type="button" onClick={() => addRosterName(position)}>
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
                  <h4>Table</h4>
                  <div className="check-grid">
                    {catalog.table_stat_keys.map((stat) => (
                      <label key={`table-${position}-${stat.key}`}>
                        <input
                          type="checkbox"
                          checked={(settings.table_by_position[position] ?? []).includes(
                            stat.key,
                          )}
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
                  <h4>Charts</h4>
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
  positions: Position[],
): DisplaySettings {
  const table_by_position: DisplaySettings["table_by_position"] = {};
  const charts_by_position: DisplaySettings["charts_by_position"] = {};
  const roster_by_position: NonNullable<DisplaySettings["roster_by_position"]> = {};
  for (const position of positions) {
    table_by_position[position] = settings.table_by_position[position] ?? [];
    charts_by_position[position] = settings.charts_by_position[position] ?? [];
    roster_by_position[position] = settings.roster_by_position?.[position] ?? [];
  }
  return { table_by_position, charts_by_position, roster_by_position };
}

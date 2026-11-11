import { useEffect, useState } from "react";
import {
  addFfmpegToPath,
  getFfmpegSettings,
  getFfmpegStatus,
  installFfmpeg,
  putFfmpegSettings,
  resetFfmpegSettings,
} from "../api";
import type { FfmpegQuality, FfmpegSettings, FfmpegStatus } from "../types";

const QUALITY_OPTIONS: Array<{ value: FfmpegQuality; label: string; hint: string }> = [
  { value: "light", label: "軽い", hint: "速い・ファイル小" },
  { value: "standard", label: "標準", hint: "バランス（推奨）" },
  { value: "high", label: "きれい", hint: "遅い・高画質" },
];

export function ToolsPage() {
  const [status, setStatus] = useState<FfmpegStatus | null>(null);
  const [settings, setSettings] = useState<FfmpegSettings | null>(null);
  const [log, setLog] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedNote, setSavedNote] = useState<string | null>(null);

  async function refresh() {
    const [st, cfg] = await Promise.all([getFfmpegStatus(), getFfmpegSettings()]);
    setStatus(st);
    setSettings(cfg);
  }

  useEffect(() => {
    refresh().catch((err) => setError(String(err)));
  }, []);

  async function onInstall() {
    setBusy(true);
    setError(null);
    setLog(null);
    try {
      const result = await installFfmpeg();
      setStatus(result.status);
      const summary = [
        `ok=${String(result.ok ?? result.returncode === 0)}`,
        `winget exit=${result.returncode}`,
        result.stdout || "",
        result.stderr || "",
      ]
        .filter(Boolean)
        .join("\n");
      setLog(summary);
      if (!result.status?.found && result.returncode !== 0) {
        setError(
          "インストールに失敗したか、まだ ffmpeg が見つかりません。ログを確認するか、手動で winget install --id Gyan.FFmpeg -e を実行してください。",
        );
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onAddPath() {
    setBusy(true);
    setError(null);
    try {
      setStatus(await addFfmpegToPath());
      setLog("ユーザー PATH に ffmpeg のディレクトリを追加しました。新しい端末では自動で認識されます。");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onSaveSettings() {
    if (!settings) return;
    setBusy(true);
    setError(null);
    setSavedNote(null);
    try {
      const saved = await putFfmpegSettings({
        ...settings,
        ffmpeg_path: settings.ffmpeg_path?.trim() ? settings.ffmpeg_path.trim() : null,
      });
      setSettings(saved);
      setSavedNote("設定を保存しました。次の変換・切り分けから反映されます。");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onResetSettings() {
    setBusy(true);
    setError(null);
    setSavedNote(null);
    try {
      setSettings(await resetFfmpegSettings());
      setSavedNote("設定を初期値に戻しました。");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  function useDetectedPath() {
    if (!settings || !status?.path) return;
    setSettings({ ...settings, ffmpeg_path: status.path });
  }

  return (
    <section className="panel">
      <h2>ffmpeg セットアップ</h2>
      <p className="hint">
        クリップ自動切り分けに ffmpeg が必要です。未導入なら winget で入れ、PATH
        に追加できます。下の簡易設定で品質と実行パスを変えられます。
      </p>

      <div className="overview-card">
        <h4>状態</h4>
        {status ? (
          <dl>
            <div>
              <dt>検出</dt>
              <dd>{status.found ? "あり" : "なし"}</dd>
            </div>
            <div>
              <dt>PATH</dt>
              <dd>{status.on_path ? "通っている" : "未設定 / 不明"}</dd>
            </div>
            <div>
              <dt>パス</dt>
              <dd className="mono">{status.path ?? "—"}</dd>
            </div>
            <div>
              <dt>バージョン</dt>
              <dd>{status.version_line ?? "—"}</dd>
            </div>
          </dl>
        ) : (
          <p>確認中…</p>
        )}
        {status?.hints?.length ? (
          <ul>
            {status.hints.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        ) : null}
      </div>

      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn" disabled={busy} onClick={() => refresh().catch((e) => setError(String(e)))}>
          再確認
        </button>
        <button className="btn primary" disabled={busy} onClick={onInstall}>
          winget でインストール
        </button>
        <button className="btn" disabled={busy} onClick={onAddPath}>
          PATH に追加
        </button>
      </div>

      <div className="result-box" style={{ marginTop: 16 }}>
        <h3>簡易設定</h3>
        {settings ? (
          <>
            <label className="hint" style={{ display: "block", marginBottom: 6 }}>
              ffmpeg 実行ファイル（空なら自動検出）
            </label>
            <div className="row">
              <input
                className="text-input grow"
                placeholder="C:\...\ffmpeg.exe"
                value={settings.ffmpeg_path ?? ""}
                onChange={(e) =>
                  setSettings({ ...settings, ffmpeg_path: e.target.value || null })
                }
              />
              <button
                className="btn"
                disabled={busy || !status?.path}
                onClick={useDetectedPath}
              >
                検出パスを入れる
              </button>
            </div>

            <label className="hint" style={{ display: "block", marginTop: 12, marginBottom: 6 }}>
              変換・再エンコード品質
            </label>
            <div className="row">
              {QUALITY_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  className={`btn ${settings.quality === opt.value ? "primary" : ""}`}
                  disabled={busy}
                  onClick={() => setSettings({ ...settings, quality: opt.value })}
                >
                  {opt.label}
                  <span className="hint"> · {opt.hint}</span>
                </button>
              ))}
            </div>

            <label className="row" style={{ marginTop: 12 }}>
              <input
                type="checkbox"
                checked={settings.auto_convert_webm}
                disabled={busy}
                onChange={(e) =>
                  setSettings({ ...settings, auto_convert_webm: e.target.checked })
                }
              />
              <span>webm を切り分け前に MP4 へ自動変換する</span>
            </label>

            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn primary" disabled={busy} onClick={onSaveSettings}>
                設定を保存
              </button>
              <button className="btn" disabled={busy} onClick={onResetSettings}>
                初期値に戻す
              </button>
            </div>
            {savedNote ? <p className="success">{savedNote}</p> : null}
          </>
        ) : (
          <p>設定読み込み中…</p>
        )}
      </div>

      {error ? <p className="error">{error}</p> : null}
      {log ? <pre className="log-box">{log}</pre> : null}
    </section>
  );
}

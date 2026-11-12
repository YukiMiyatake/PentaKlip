import { useEffect, useState } from "react";
import {
  addFfmpegToPath,
  getFfmpegSettings,
  getFfmpegStatus,
  installFfmpeg,
  putFfmpegSettings,
  resetFfmpegSettings,
} from "../api";
import type { FfmpegEncoder, FfmpegQuality, FfmpegSettings, FfmpegStatus } from "../types";

const QUALITY_OPTIONS: Array<{ value: FfmpegQuality; label: string; hint: string }> = [
  { value: "light", label: "軽い", hint: "速い・ファイル小" },
  { value: "standard", label: "標準", hint: "バランス（推奨）" },
  { value: "high", label: "きれい", hint: "遅い・高画質" },
];

const ENCODER_OPTIONS: Array<{ value: FfmpegEncoder; label: string; hint: string }> = [
  { value: "auto", label: "自動（GPU優先）", hint: "NVENC → AMF → QSV → CPU" },
  { value: "nvenc", label: "NVIDIA", hint: "h264_nvenc" },
  { value: "amf", label: "AMD", hint: "h264_amf" },
  { value: "qsv", label: "Intel", hint: "h264_qsv" },
  { value: "cpu", label: "CPU", hint: "libx264" },
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
      <h2>ffmpeg</h2>

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
        {!status?.found && status?.hints?.length ? (
          <ul className="hint-list">
            {status.hints.slice(0, 2).map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        ) : null}
      </div>

      <div className="row actions">
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

      <div className="result-box">
        <h3>設定</h3>
        {settings ? (
          <>
            <label className="field-label">実行ファイル</label>
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
                検出を使う
              </button>
            </div>

            <label className="field-label">エンコーダ</label>
            <div className="row wrap">
              {ENCODER_OPTIONS.map((opt) => {
                const listed = settings.available_encoders;
                const unsupported =
                  opt.value !== "auto" &&
                  opt.value !== "cpu" &&
                  Array.isArray(listed) &&
                  !listed.includes(opt.value);
                return (
                  <button
                    key={opt.value}
                    className={`btn ${settings.encoder === opt.value ? "primary" : ""}`}
                    disabled={busy}
                    title={unsupported ? "未対応の可能性あり" : opt.hint}
                    onClick={() => setSettings({ ...settings, encoder: opt.value })}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>

            <label className="field-label">品質</label>
            <div className="row wrap">
              {QUALITY_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  className={`btn ${settings.quality === opt.value ? "primary" : ""}`}
                  disabled={busy}
                  title={opt.hint}
                  onClick={() => setSettings({ ...settings, quality: opt.value })}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            <label className="row check-row">
              <input
                type="checkbox"
                checked={settings.auto_convert_webm}
                disabled={busy}
                onChange={(e) =>
                  setSettings({ ...settings, auto_convert_webm: e.target.checked })
                }
              />
              <span>webm → mp4 自動変換</span>
            </label>

            <div className="row actions">
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

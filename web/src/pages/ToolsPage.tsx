import { useEffect, useState } from "react";
import { addFfmpegToPath, getFfmpegStatus, installFfmpeg } from "../api";
import type { FfmpegStatus } from "../types";

export function ToolsPage() {
  const [status, setStatus] = useState<FfmpegStatus | null>(null);
  const [log, setLog] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setStatus(await getFfmpegStatus());
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

  return (
    <section className="panel">
      <h2>ffmpeg セットアップ</h2>
      <p className="hint">
        クリップ自動切り分けに ffmpeg が必要です。未導入なら winget で入れ、PATH
        に追加できます。
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
        <button className="btn" disabled={busy} onClick={() => refresh()}>
          再確認
        </button>
        <button className="btn primary" disabled={busy} onClick={onInstall}>
          winget でインストール
        </button>
        <button className="btn" disabled={busy} onClick={onAddPath}>
          PATH に追加
        </button>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {log ? <pre className="log-box">{log}</pre> : null}
    </section>
  );
}

import { useEffect, useRef, useState } from "react";
import {
  autoSplitClips,
  exportEvents,
  getLiveEvents,
  getUiPreferences,
  listDir,
  putUiPreferences,
} from "../api";
import type {
  CreateClipsResponse,
  EventsLiveStatus,
  FsEntry,
  UiPreferences,
} from "../types";

export function AutoSplitPage() {
  const [prefs, setPrefs] = useState<UiPreferences | null>(null);
  const [videoDir, setVideoDir] = useState("");
  const [eventsDir, setEventsDir] = useState("");
  const [videos, setVideos] = useState<FsEntry[]>([]);
  const [eventFiles, setEventFiles] = useState<FsEntry[]>([]);
  const [videoPath, setVideoPath] = useState("");
  const [eventsPath, setEventsPath] = useState("");
  const [padding, setPadding] = useState(10);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CreateClipsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [live, setLive] = useState<EventsLiveStatus | null>(null);
  const [watching, setWatching] = useState(false);
  const [exportFilename, setExportFilename] = useState("");
  const [exportNote, setExportNote] = useState<string | null>(null);
  const watchRef = useRef<number | null>(null);

  useEffect(() => {
    getUiPreferences()
      .then(async (p) => {
        setPrefs(p);
        if (p.last_video_dir) {
          setVideoDir(p.last_video_dir);
          const listed = await listDir(p.last_video_dir, [".mp4", ".mkv", ".mov", ".avi"]);
          setVideos(listed.entries.filter((e) => !e.is_dir));
        }
        if (p.last_events_dir) {
          setEventsDir(p.last_events_dir);
          const listed = await listDir(p.last_events_dir, [".json"]);
          setEventFiles(listed.entries.filter((e) => !e.is_dir));
        } else {
          setEventsDir("");
        }
      })
      .catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    if (!watching) {
      if (watchRef.current != null) {
        window.clearInterval(watchRef.current);
        watchRef.current = null;
      }
      return;
    }
    const tick = () => {
      getLiveEvents()
        .then(setLive)
        .catch((err) => setError(String(err)));
    };
    tick();
    watchRef.current = window.setInterval(tick, 2000);
    return () => {
      if (watchRef.current != null) {
        window.clearInterval(watchRef.current);
        watchRef.current = null;
      }
    };
  }, [watching]);

  async function persist(next: UiPreferences) {
    setPrefs(await putUiPreferences(next));
  }

  async function loadVideos() {
    const listed = await listDir(videoDir, [".mp4", ".mkv", ".mov", ".avi"]);
    setVideoDir(listed.directory);
    setVideos(listed.entries.filter((e) => !e.is_dir));
    if (prefs) await persist({ ...prefs, last_video_dir: listed.directory });
  }

  async function loadEvents() {
    const listed = await listDir(eventsDir, [".json"]);
    setEventsDir(listed.directory);
    setEventFiles(listed.entries.filter((e) => !e.is_dir));
    if (prefs) await persist({ ...prefs, last_events_dir: listed.directory });
  }

  async function refreshLive() {
    setError(null);
    try {
      setLive(await getLiveEvents());
    } catch (err) {
      setError(String(err));
    }
  }

  async function saveEventsJson() {
    setBusy(true);
    setError(null);
    setExportNote(null);
    try {
      const response = await exportEvents({
        directory: eventsDir || null,
        filename: exportFilename || null,
      });
      setExportNote(
        `保存しました: ${response.path}（${response.event_count} イベント）`,
      );
      setEventsPath(response.path);
      const parent = response.path.replace(/[/\\][^/\\]+$/, "");
      setEventsDir(parent);
      const listed = await listDir(parent, [".json"]);
      setEventFiles(listed.entries.filter((e) => !e.is_dir));
      if (prefs) await persist({ ...prefs, last_events_dir: parent });
      setLive(await getLiveEvents());
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function run(dryRun: boolean) {
    if (!videoPath) {
      setError("動画を選択してください");
      return;
    }
    if (!eventsPath) {
      setError("イベント JSON を選択してください（下の収集、または既存ファイル）");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const response = await autoSplitClips({
        source_video_path: videoPath,
        events_path: eventsPath,
        padding_before_sec: padding,
        padding_after_sec: padding,
        dry_run: dryRun,
      });
      setResult(response);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  const liveLabel = live?.available
    ? `接続中 · ${live.event_count} イベント` +
      (live.game_time_sec != null ? ` · ゲーム時間 ${live.game_time_sec.toFixed(0)}s` : "")
    : live?.error
      ? `未接続 · ${live.error}`
      : "未取得";

  return (
    <section className="panel">
      <h2>自動クリップ切り分け</h2>
      <p className="hint">
        試合の録画動画とイベント JSON からハイライトを検出し、前後秒で自動的にクリップを書き出します。
        ffmpeg が必要です（ツールタブで導入）。
      </p>

      <div className="result-box" style={{ marginBottom: 16 }}>
        <h3>イベント JSON 作成</h3>
        <p className="hint">
          LoL リプレイ（または対局）中に Live Client（2999）からイベントを取得し、自動切り分け用
          JSON として保存します。イベントは試合開始から累積されるので、終盤に一度保存すれば十分です。
        </p>
        <p className="mono">{liveLabel}</p>
        <div className="row">
          <button className="btn" disabled={busy} onClick={() => refreshLive()}>
            今すぐ取得
          </button>
          <button
            className={`btn ${watching ? "primary" : ""}`}
            disabled={busy}
            onClick={() => setWatching((v) => !v)}
          >
            {watching ? "監視停止" : "2秒ごとに監視"}
          </button>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <input
            className="text-input grow"
            placeholder="保存先フォルダ"
            value={eventsDir}
            onChange={(e) => setEventsDir(e.target.value)}
          />
          <input
            className="text-input"
            style={{ width: 220 }}
            placeholder="ファイル名（空なら自動）"
            value={exportFilename}
            onChange={(e) => setExportFilename(e.target.value)}
          />
          <button className="btn primary" disabled={busy} onClick={() => saveEventsJson()}>
            JSON を保存
          </button>
        </div>
        {exportNote ? <p className="success">{exportNote}</p> : null}
      </div>

      <div className="split-2">
        <div>
          <h3>動画</h3>
          <div className="row">
            <input
              className="text-input grow"
              value={videoDir}
              onChange={(e) => setVideoDir(e.target.value)}
            />
            <button className="btn" onClick={() => loadVideos().catch((e) => setError(String(e)))}>
              一覧
            </button>
          </div>
          <div className="file-list">
            {videos.map((v) => (
              <button
                key={v.path}
                className={`file-item ${videoPath === v.path ? "active" : ""}`}
                onClick={() => setVideoPath(v.path)}
              >
                {v.name}
              </button>
            ))}
          </div>
        </div>
        <div>
          <h3>イベント JSON</h3>
          <div className="row">
            <input
              className="text-input grow"
              value={eventsDir}
              onChange={(e) => setEventsDir(e.target.value)}
            />
            <button className="btn" onClick={() => loadEvents().catch((e) => setError(String(e)))}>
              一覧
            </button>
          </div>
          <div className="file-list">
            {eventFiles.map((v) => (
              <button
                key={v.path}
                className={`file-item ${eventsPath === v.path ? "active" : ""}`}
                onClick={() => setEventsPath(v.path)}
              >
                {v.name}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="row" style={{ marginTop: 12 }}>
        <label>
          前後パディング（秒）{" "}
          <input
            className="text-input narrow"
            type="number"
            min={0}
            value={padding}
            onChange={(e) => setPadding(Number(e.target.value))}
          />
        </label>
        <button className="btn" disabled={busy} onClick={() => run(true)}>
          ドライラン
        </button>
        <button className="btn primary" disabled={busy} onClick={() => run(false)}>
          自動切り分け実行
        </button>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {result ? (
        <div className="result-box">
          <p className="success">
            {result.clip_count} クリップ → {result.output_dir}
          </p>
          <ul>
            {result.clips.map((c) => (
              <li key={c.output_path}>
                <span className="mono">
                  {c.kind} {c.start_sec.toFixed(0)}-{c.end_sec.toFixed(0)}s
                </span>{" "}
                {c.output_path}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

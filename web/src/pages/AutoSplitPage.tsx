import { useEffect, useState } from "react";
import { autoSplitClips, getUiPreferences, listDir, putUiPreferences } from "../api";
import type { CreateClipsResponse, FsEntry, UiPreferences } from "../types";

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
        }
      })
      .catch((err) => setError(String(err)));
  }, []);

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

  async function run(dryRun: boolean) {
    if (!videoPath) {
      setError("動画を選択してください");
      return;
    }
    if (!eventsPath) {
      setError("イベント JSON を選択してください（Live Client eventdata など）");
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

  return (
    <section className="panel">
      <h2>自動クリップ切り分け</h2>
      <p className="hint">
        試合の録画動画とイベント JSON からハイライトを検出し、前後秒で自動的にクリップを書き出します。
        ffmpeg が必要です（ツールタブで導入）。
      </p>

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

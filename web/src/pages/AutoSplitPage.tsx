import { useEffect, useRef, useState } from "react";
import {
  autoSplitClips,
  exportEvents,
  getLiveEvents,
  harvestEvents,
  getUiPreferences,
  listDir,
  pickDirectory,
  putUiPreferences,
} from "../api";
import type {
  CreateClipsResponse,
  EventsLiveStatus,
  FsEntry,
  UiPreferences,
} from "../types";

const GAME_ID_RE = /([A-Za-z0-9]+-\d+)/;
const VIDEO_SUFFIXES = [".mp4", ".mkv", ".mov", ".avi", ".webm"];

function inferGameIdFromName(name: string | null | undefined): string {
  if (!name) return "";
  const match = name.match(GAME_ID_RE);
  return match?.[1] ?? "";
}

function joinOsPath(root: string, ...parts: string[]): string {
  const base = root.replace(/[/\\]+$/, "");
  const sep = root.includes("/") && !root.includes("\\") ? "/" : "\\";
  return [base, ...parts].join(sep);
}

export function AutoSplitPage() {
  const [prefs, setPrefs] = useState<UiPreferences | null>(null);
  const [outputRoot, setOutputRoot] = useState("");
  const [gameId, setGameId] = useState("");
  const [videoDir, setVideoDir] = useState("");
  const [eventsDir, setEventsDir] = useState("");
  const [videos, setVideos] = useState<FsEntry[]>([]);
  const [eventFiles, setEventFiles] = useState<FsEntry[]>([]);
  const [videoPath, setVideoPath] = useState("");
  const [eventsPath, setEventsPath] = useState("");
  const [padding, setPadding] = useState(10);
  const [mergeGap, setMergeGap] = useState(25);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CreateClipsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [live, setLive] = useState<EventsLiveStatus | null>(null);
  const [exportFilename, setExportFilename] = useState("events.json");
  const [includeStats, setIncludeStats] = useState(true);
  const [exportNote, setExportNote] = useState<string | null>(null);
  const [prefsSavedNote, setPrefsSavedNote] = useState<string | null>(null);
  const rememberTimer = useRef<number | null>(null);
  const folderStateRef = useRef({ outputRoot: "", videoDir: "", eventsDir: "" });

  async function listEvents(dir: string) {
    try {
      const listed = await listDir(dir, [".json"]);
      setEventsDir(listed.directory);
      setEventFiles(listed.entries.filter((e) => !e.is_dir));
      return listed.directory;
    } catch {
      setEventsDir(dir);
      setEventFiles([]);
      return dir;
    }
  }

  async function listVideos(dir: string) {
    try {
      const listed = await listDir(dir, VIDEO_SUFFIXES);
      setVideoDir(listed.directory);
      setVideos(listed.entries.filter((e) => !e.is_dir));
      return listed.directory;
    } catch {
      setVideoDir(dir);
      setVideos([]);
      return dir;
    }
  }

  /** Wire Event/ + Replay/ under the output base and refresh lists. */
  async function applyOutputRoot(root: string, opts?: { persist?: boolean }) {
    const persist = opts?.persist !== false;
    const trimmed = root.trim();
    if (!trimmed) return;
    const eventDir = joinOsPath(trimmed, "Event");
    const replayDir = joinOsPath(trimmed, "Replay");
    setOutputRoot(trimmed);
    const [resolvedEvents, resolvedVideos] = await Promise.all([
      listEvents(eventDir),
      listVideos(replayDir),
    ]);
    if (persist) {
      await rememberPrefs({
        last_output_root: trimmed,
        last_events_dir: resolvedEvents,
        last_video_dir: resolvedVideos,
      });
      setPrefsSavedNote("出力を保存しました");
    }
  }

  useEffect(() => {
    getUiPreferences()
      .then(async (p) => {
        setPrefs(p);
        if (p.last_game_id) setGameId(p.last_game_id);
        if (p.last_output_root) {
          await applyOutputRoot(p.last_output_root, { persist: false });
        } else {
          if (p.last_video_dir) await listVideos(p.last_video_dir);
          if (p.last_events_dir) await listEvents(p.last_events_dir);
        }
      })
      .catch((err) => setError(String(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount only
  }, []);

  async function persist(next: UiPreferences) {
    setPrefs(await putUiPreferences(next));
  }

  async function rememberPrefs(partial: Partial<UiPreferences>) {
    const base = prefs ?? (await getUiPreferences());
    const next: UiPreferences = { ...base, ...partial };
    const unchanged =
      next.fixed_target_rofl === base.fixed_target_rofl &&
      next.last_source_dir === base.last_source_dir &&
      next.last_video_dir === base.last_video_dir &&
      next.last_events_dir === base.last_events_dir &&
      next.last_output_root === base.last_output_root &&
      next.last_game_id === base.last_game_id;
    if (unchanged) {
      setPrefs(base);
      return base;
    }
    return persist(next);
  }

  folderStateRef.current = { outputRoot, videoDir, eventsDir };

  async function rememberFoldersFromInputs() {
    const snap = folderStateRef.current;
    const root = snap.outputRoot.trim();
    if (root) {
      await applyOutputRoot(root, { persist: true });
      return;
    }
    const partial: Partial<UiPreferences> = {};
    if (snap.videoDir.trim()) partial.last_video_dir = snap.videoDir.trim();
    if (snap.eventsDir.trim()) partial.last_events_dir = snap.eventsDir.trim();
    if (Object.keys(partial).length === 0) return;
    await rememberPrefs(partial);
    setPrefsSavedNote("フォルダ設定を保存しました");
  }

  function scheduleRememberFolders() {
    if (rememberTimer.current != null) window.clearTimeout(rememberTimer.current);
    rememberTimer.current = window.setTimeout(() => {
      rememberFoldersFromInputs().catch((e) => setError(String(e)));
    }, 400);
  }

  function resolvedGameId(): string {
    return (
      gameId.trim() ||
      live?.game_id?.trim() ||
      prefs?.last_game_id?.trim() ||
      inferGameIdFromName(eventsPath) ||
      inferGameIdFromName(videoPath) ||
      ""
    );
  }

  async function browseOutput() {
    setError(null);
    try {
      const picked = await pickDirectory({
        title: "出力ベースを選択",
        initial: outputRoot || null,
      });
      if (picked.cancelled || !picked.path) return;
      await applyOutputRoot(picked.path, { persist: true });
    } catch (err) {
      setError(String(err));
    }
  }

  async function browseVideoOverride() {
    setError(null);
    try {
      const picked = await pickDirectory({
        title: "動画フォルダを選択",
        initial: videoDir || null,
      });
      if (picked.cancelled || !picked.path) return;
      const resolved = await listVideos(picked.path);
      await rememberPrefs({ last_video_dir: resolved });
      setPrefsSavedNote("動画フォルダを更新しました");
    } catch (err) {
      setError(String(err));
    }
  }

  function selectVideo(path: string, name: string) {
    setVideoPath(path);
    const inferred = inferGameIdFromName(name) || inferGameIdFromName(path);
    if (inferred) {
      setGameId(inferred);
      rememberPrefs({ last_game_id: inferred }).catch(() => {});
    }
  }

  function selectEvents(path: string) {
    setEventsPath(path);
    const inferred = inferGameIdFromName(path);
    if (inferred) {
      setGameId(inferred);
      rememberPrefs({ last_game_id: inferred }).catch(() => {});
    }
  }

  async function refreshLive(opts?: { harvest?: boolean }) {
    const doHarvest = opts?.harvest !== false;
    setBusy(true);
    setError(null);
    try {
      const status = doHarvest ? await harvestEvents(16) : await getLiveEvents();
      setLive(status);
      if (status.game_id) {
        setGameId(status.game_id);
        await rememberPrefs({ last_game_id: status.game_id });
      }
      if (status.warning) setExportNote(status.warning);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function saveEventsJson() {
    const gid = resolvedGameId();
    if (!gid) {
      setError("ゲームIDを特定できません（Live Client / 動画・イベント名 / 前回ID）");
      return;
    }
    if (!outputRoot.trim()) {
      setError("出力ベースを選んでください");
      return;
    }
    setBusy(true);
    setError(null);
    setExportNote(null);
    try {
      await applyOutputRoot(outputRoot.trim(), { persist: true });
      const response = await exportEvents({
        directory: outputRoot.trim(),
        filename: exportFilename || "events.json",
        game_id: gid,
        include_stats: includeStats,
        harvest: true,
        harvest_speed: 16,
      });
      setGameId(response.game_id);
      setExportNote(
        `保存 · ${response.event_count} イベント · ${response.game_id}` +
          (response.stats_aggregated_path ? " · スタッツあり" : ""),
      );
      setEventsPath(response.path);
      setEventsDir(response.game_dir);
      await listEvents(response.game_dir);
      await rememberPrefs({
        last_events_dir: response.game_dir,
        last_output_root: outputRoot.trim(),
        last_game_id: response.game_id,
      });
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
      setError("イベント JSON を選択してください");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const response = await autoSplitClips({
        source_video_path: videoPath,
        events_path: eventsPath,
        original_match_id: resolvedGameId() || null,
        padding_before_sec: padding,
        padding_after_sec: padding,
        merge_gap_sec: mergeGap,
        merge_fights: true,
        dry_run: dryRun,
      });
      setResult(response);
      if (response.game_id) {
        setGameId(response.game_id);
        await rememberPrefs({ last_game_id: response.game_id });
      }
      if (outputRoot.trim()) await listVideos(joinOsPath(outputRoot.trim(), "Replay"));
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  const liveLabel = live?.available
    ? `接続中 · ${live.event_count} 件` +
      (live.game_id ? ` · ${live.game_id}` : "") +
      (live.game_time_sec != null ? ` · ${live.game_time_sec.toFixed(0)}s` : "")
    : live?.error
      ? `未接続 · ${live.error}`
      : "未取得";

  const gid = resolvedGameId() || "…";
  const base = outputRoot.replace(/[/\\]+$/, "") || "…";

  return (
    <section className="panel">
      <h2>自動切り分け</h2>

      <div className="result-box">
        <h3>出力</h3>
        <div className="row">
          <input
            className="text-input grow"
            placeholder="出力ベース"
            value={outputRoot}
            onChange={(e) => {
              const next = e.target.value;
              setOutputRoot(next);
              if (next.trim()) {
                setEventsDir(joinOsPath(next.trim(), "Event"));
                setVideoDir(joinOsPath(next.trim(), "Replay"));
              }
              scheduleRememberFolders();
            }}
            onBlur={() => rememberFoldersFromInputs().catch((e) => setError(String(e)))}
          />
          <button className="btn" disabled={busy} onClick={() => browseOutput()}>
            参照…
          </button>
        </div>
        <p className="path-preview mono">
          {base}\Event · Replay · stats · Clip\{gid}
        </p>
        {prefsSavedNote ? <p className="success">{prefsSavedNote}</p> : null}
      </div>

      <div className="result-box">
        <h3>イベント</h3>
        <p className="status-line mono">{liveLabel}</p>
        {live?.warning ? <p className="error">{live.warning}</p> : null}
        <div className="row">
          <button className="btn primary" disabled={busy} onClick={() => refreshLive({ harvest: true })}>
            {busy ? "走査中…" : "試合を走査"}
          </button>
          <button className="btn" disabled={busy} onClick={() => refreshLive({ harvest: false })}>
            現在位置のみ
          </button>
          <input
            className="text-input"
            style={{ width: 160 }}
            placeholder="ファイル名"
            value={exportFilename}
            onChange={(e) => setExportFilename(e.target.value)}
          />
          <label className="row" style={{ gap: 6, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={includeStats}
              onChange={(e) => setIncludeStats(e.target.checked)}
            />
            スタッツも保存
          </label>
          <button className="btn primary" disabled={busy} onClick={() => saveEventsJson()}>
            JSON を保存
          </button>
        </div>
        {exportNote ? <p className="success">{exportNote}</p> : null}
      </div>

      <div className="split-2">
        <div className="stack">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3>動画（Replay）</h3>
            <button className="btn ghost" disabled={busy} onClick={() => browseVideoOverride()}>
              別フォルダ…
            </button>
          </div>
          <p className="path-preview mono">{videoDir || "—"}</p>
          <div className="file-list">
            {videos.map((v) => (
              <button
                key={v.path}
                className={`file-item ${videoPath === v.path ? "active" : ""}`}
                onClick={() => selectVideo(v.path, v.name)}
              >
                {v.name}
              </button>
            ))}
          </div>
        </div>
        <div className="stack">
          <h3>イベント JSON（Event）</h3>
          <p className="path-preview mono">{eventsDir || "—"}</p>
          <div className="file-list">
            {eventFiles.map((v) => (
              <button
                key={v.path}
                className={`file-item ${eventsPath === v.path ? "active" : ""}`}
                onClick={() => selectEvents(v.path)}
              >
                {v.name}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="row actions">
        <label>
          前後秒{" "}
          <input
            className="text-input narrow"
            type="number"
            min={0}
            value={padding}
            onChange={(e) => setPadding(Number(e.target.value))}
          />
        </label>
        <label>
          マージ秒{" "}
          <input
            className="text-input narrow"
            type="number"
            min={0}
            value={mergeGap}
            onChange={(e) => setMergeGap(Number(e.target.value))}
          />
        </label>
        <button className="btn" disabled={busy} onClick={() => run(true)}>
          ドライラン
        </button>
        <button className="btn primary" disabled={busy} onClick={() => run(false)}>
          実行
        </button>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {result ? (
        <div className="result-box">
          <p className="success">
            {result.clip_count} クリップ
            {result.game_id ? ` · ${result.game_id}` : ""}
            {result.converted ? " · 変換済み" : ""}
          </p>
          <p className="mono path-preview">{result.output_dir}</p>
          <ul className="clip-list">
            {result.clips.map((c) => (
              <li key={c.output_path} className="mono">
                {c.label || c.kind} · {c.start_sec.toFixed(0)}–{c.end_sec.toFixed(0)}s
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

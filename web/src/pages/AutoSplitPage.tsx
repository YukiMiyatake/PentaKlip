import { useEffect, useRef, useState } from "react";
import {
  autoSplitClips,
  exportEvents,
  getLiveEvents,
  harvestEvents,
  getUiPreferences,
  inspectRofl,
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
  const folderStateRef = useRef({ outputRoot: "", videoDir: "", eventsDir: "", gameId: "" });

  async function fillGameIdFromRofl(roflPath: string | null | undefined, fallbackId?: string | null) {
    if (fallbackId) setGameId(fallbackId);
    if (!roflPath) return;
    try {
      const overview = await inspectRofl(roflPath);
      if (!fallbackId && overview.match_id) setGameId(overview.match_id);
    } catch {
      if (!fallbackId) {
        const inferred = inferGameIdFromName(roflPath);
        if (inferred) setGameId(inferred);
      }
    }
  }

  useEffect(() => {
    getUiPreferences()
      .then(async (p) => {
        setPrefs(p);
        if (p.last_output_root) setOutputRoot(p.last_output_root);
        await fillGameIdFromRofl(p.fixed_target_rofl, p.last_game_id);
        if (p.last_video_dir) {
          setVideoDir(p.last_video_dir);
          try {
            const listed = await listDir(p.last_video_dir, [".mp4", ".mkv", ".mov", ".avi", ".webm"]);
            setVideos(listed.entries.filter((e) => !e.is_dir));
          } catch {
            // Keep remembered path even if the folder is temporarily missing.
          }
        }
        const eventDir =
          p.last_events_dir ||
          (p.last_output_root ? joinOsPath(p.last_output_root, "Event") : "");
        if (eventDir) {
          setEventsDir(eventDir);
          try {
            const listed = await listDir(eventDir, [".json"]);
            setEventFiles(listed.entries.filter((e) => !e.is_dir));
          } catch {
            // Keep remembered path even if the folder is temporarily missing.
          }
        }
      })
      .catch((err) => setError(String(err)));
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

  folderStateRef.current = { outputRoot, videoDir, eventsDir, gameId };

  async function rememberFoldersFromInputs() {
    const snap = folderStateRef.current;
    const partial: Partial<UiPreferences> = {};
    const root = snap.outputRoot.trim();
    const video = snap.videoDir.trim();
    const events = snap.eventsDir.trim() || (root ? joinOsPath(root, "Event") : "");
    const gid = snap.gameId.trim();
    if (root) partial.last_output_root = root;
    if (video) partial.last_video_dir = video;
    if (events) partial.last_events_dir = events;
    if (gid) partial.last_game_id = gid;
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

  async function browseFolder(
    kind: "output" | "video" | "events",
  ) {
    setError(null);
    const initial =
      kind === "output" ? outputRoot : kind === "video" ? videoDir : eventsDir;
    const title =
      kind === "output"
        ? "出力ベースを選択"
        : kind === "video"
          ? "動画フォルダを選択"
          : "イベント JSON フォルダを選択";
    try {
      const picked = await pickDirectory({ title, initial: initial || null });
      if (picked.cancelled || !picked.path) return;
      if (kind === "output") {
        setOutputRoot(picked.path);
        const eventDir = joinOsPath(picked.path, "Event");
        setEventsDir(eventDir);
        try {
          const listed = await listDir(eventDir, [".json"]);
          setEventFiles(listed.entries.filter((e) => !e.is_dir));
        } catch {
          setEventFiles([]);
        }
        await rememberPrefs({
          last_output_root: picked.path,
          last_events_dir: eventDir,
        });
        setPrefsSavedNote("出力ベースを保存しました（Event / Replay / stats / Clip）");
        return;
      }
      if (kind === "video") {
        setVideoDir(picked.path);
        const listed = await listDir(picked.path, [".mp4", ".mkv", ".mov", ".avi", ".webm"]);
        setVideoDir(listed.directory);
        setVideos(listed.entries.filter((e) => !e.is_dir));
        await rememberPrefs({ last_video_dir: listed.directory });
        setPrefsSavedNote("動画フォルダを保存しました");
        return;
      }
      setEventsDir(picked.path);
      const listed = await listDir(picked.path, [".json"]);
      setEventsDir(listed.directory);
      setEventFiles(listed.entries.filter((e) => !e.is_dir));
      const inferred = inferGameIdFromName(listed.directory);
      if (inferred && !gameId) setGameId(inferred);
      await rememberPrefs({
        last_events_dir: listed.directory,
        last_game_id: inferred || gameId.trim() || null,
      });
      setPrefsSavedNote("イベントフォルダを保存しました");
    } catch (err) {
      setError(String(err));
    }
  }

  async function loadVideos() {
    const listed = await listDir(videoDir, [".mp4", ".mkv", ".mov", ".avi", ".webm"]);
    setVideoDir(listed.directory);
    setVideos(listed.entries.filter((e) => !e.is_dir));
    await rememberPrefs({ last_video_dir: listed.directory });
  }

  async function loadEvents() {
    const listed = await listDir(eventsDir, [".json"]);
    setEventsDir(listed.directory);
    setEventFiles(listed.entries.filter((e) => !e.is_dir));
    const inferred = inferGameIdFromName(listed.directory);
    if (inferred && !gameId) setGameId(inferred);
    await rememberPrefs({
      last_events_dir: listed.directory,
      last_game_id: inferred || gameId.trim() || null,
    });
  }

  function selectVideo(path: string, name: string) {
    setVideoPath(path);
    const inferred = inferGameIdFromName(name) || inferGameIdFromName(path);
    if (inferred) setGameId(inferred);
  }

  function selectEvents(path: string) {
    setEventsPath(path);
    const inferred = inferGameIdFromName(path);
    if (inferred) setGameId(inferred);
  }

  async function refreshLive(opts?: { harvest?: boolean }) {
    const doHarvest = opts?.harvest !== false;
    setBusy(true);
    setError(null);
    try {
      const status = doHarvest ? await harvestEvents(16) : await getLiveEvents();
      setLive(status);
      if (!gameId && status.game_id) setGameId(status.game_id);
      if (status.warning) setExportNote(status.warning);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function saveEventsJson() {
    if (!gameId.trim()) {
      setError("ゲームIDを入力してください（例: JP1-1234567890）");
      return;
    }
    setBusy(true);
    setError(null);
    setExportNote(null);
    try {
      await rememberFoldersFromInputs();
      const response = await exportEvents({
        directory: outputRoot || null,
        filename: exportFilename || "events.json",
        game_id: gameId.trim(),
        include_stats: includeStats,
        harvest: true,
        harvest_speed: 16,
      });
      const statsBits = [
        response.stats_bundle_path
          ? response.stats_bundle_path.replace(/^.*[/\\]/, "")
          : null,
        response.stats_aggregated_path
          ? response.stats_aggregated_path.replace(/^.*[/\\]/, "")
          : null,
      ].filter(Boolean);
      setExportNote(
        `保存しました: ${response.path}（${response.event_count} イベント / ${response.game_id}）` +
          (statsBits.length
            ? ` + スタッツ（${statsBits.join(", ")}${
                response.player_count != null ? ` / ${response.player_count}人` : ""
              }）`
            : includeStats
              ? "（スタッツは allgamedata 未取得のためスキップ）"
              : ""),
      );
      setEventsPath(response.path);
      setEventsDir(response.game_dir);
      const baseRoot =
        outputRoot.trim() ||
        response.game_dir.replace(/[/\\]Event[/\\]?$/i, "").replace(/[/\\][^/\\]+$/, "");
      if (baseRoot) setOutputRoot(baseRoot);
      const listed = await listDir(response.game_dir, [".json"]);
      setEventFiles(listed.entries.filter((e) => !e.is_dir));
      await rememberPrefs({
        last_events_dir: response.game_dir,
        last_output_root: baseRoot || null,
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
        original_match_id: gameId.trim() || null,
        padding_before_sec: padding,
        padding_after_sec: padding,
        merge_gap_sec: mergeGap,
        merge_fights: true,
        dry_run: dryRun,
      });
      setResult(response);
      if (response.game_id) setGameId(response.game_id);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  const liveLabel = live?.available
    ? `接続中 · ${live.event_count} イベント` +
      (live.game_time_sec != null ? ` · ゲーム時間 ${live.game_time_sec.toFixed(0)}s` : "") +
      (live.player_count != null ? ` · ${live.player_count}人` : "") +
      (live.game_id ? ` · id ${live.game_id}` : "") +
      (live.source ? ` · ${live.source}` : "")
    : live?.error
      ? `未接続 · ${live.error}`
      : "未取得";

  const base = outputRoot.replace(/[/\\]+$/, "") || "{出力ベース}";
  const gid = gameId.trim() || "{ゲームID}";
  const outputPreview = `${base}\\Event|Replay|stats|Clip\\${gid}`;

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
              if (next.trim()) setEventsDir(joinOsPath(next.trim(), "Event"));
              scheduleRememberFolders();
            }}
            onBlur={() => rememberFoldersFromInputs().catch((e) => setError(String(e)))}
          />
          <button className="btn" disabled={busy} onClick={() => browseFolder("output")}>
            参照…
          </button>
          <input
            className="text-input"
            style={{ width: 220 }}
            placeholder="ゲームID"
            value={gameId}
            onChange={(e) => {
              setGameId(e.target.value);
              scheduleRememberFolders();
            }}
            onBlur={() => rememberFoldersFromInputs().catch((e) => setError(String(e)))}
          />
          <button
            className="btn"
            disabled={busy || !prefs?.fixed_target_rofl}
            onClick={() =>
              fillGameIdFromRofl(prefs?.fixed_target_rofl, null).catch((e) => setError(String(e)))
            }
          >
            ROFLからID
          </button>
        </div>
        <p className="path-preview mono">{outputPreview}</p>
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
            style={{ width: 180 }}
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
        <div>
          <h3>動画</h3>
          <div className="row">
            <input
              className="text-input grow"
              value={videoDir}
              onChange={(e) => {
                setVideoDir(e.target.value);
                scheduleRememberFolders();
              }}
              onBlur={() => rememberFoldersFromInputs().catch((e) => setError(String(e)))}
            />
            <button className="btn" disabled={busy} onClick={() => browseFolder("video")}>
              参照…
            </button>
            <button className="btn" onClick={() => loadVideos().catch((e) => setError(String(e)))}>
              一覧
            </button>
          </div>
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
        <div>
          <h3>イベント JSON</h3>
          <div className="row">
            <input
              className="text-input grow"
              value={eventsDir}
              onChange={(e) => {
                setEventsDir(e.target.value);
                scheduleRememberFolders();
              }}
              onBlur={() => rememberFoldersFromInputs().catch((e) => setError(String(e)))}
            />
            <button className="btn" disabled={busy} onClick={() => browseFolder("events")}>
              参照…
            </button>
            <button className="btn" onClick={() => loadEvents().catch((e) => setError(String(e)))}>
              一覧
            </button>
          </div>
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

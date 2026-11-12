import { useEffect, useRef, useState } from "react";
import {
  autoSplitClips,
  exportEvents,
  getLiveEvents,
  harvestEvents,
  getUiPreferences,
  inspectRofl,
  listDir,
  listLocalHighlights,
  listLocalReplays,
  pickDirectory,
  putUiPreferences,
} from "../api";
import type {
  CreateClipsResponse,
  EventsLiveStatus,
  FsEntry,
  LocalReplayItem,
  UiPreferences,
} from "../types";

function joinOsPath(root: string, ...parts: string[]): string {
  const base = root.replace(/[/\\]+$/, "");
  const sep = root.includes("/") && !root.includes("\\") ? "/" : "\\";
  return [base, ...parts].join(sep);
}

function eventMatchesGameId(name: string, gameId: string): boolean {
  const gid = gameId.trim().toLowerCase();
  if (!gid) return true;
  return name.toLowerCase().startsWith(`${gid}_`) || name.toLowerCase().includes(gid);
}

export function AutoSplitPage() {
  const [prefs, setPrefs] = useState<UiPreferences | null>(null);
  const [outputRoot, setOutputRoot] = useState("");
  const [gameId, setGameId] = useState("");
  const [roflPath, setRoflPath] = useState("");
  const [replays, setReplays] = useState<LocalReplayItem[]>([]);
  const [replaysDir, setReplaysDir] = useState("");
  const [highlightsDir, setHighlightsDir] = useState("");
  const [highlights, setHighlights] = useState<FsEntry[]>([]);
  const [eventsDir, setEventsDir] = useState("");
  const [eventFiles, setEventFiles] = useState<FsEntry[]>([]);
  const [videoPath, setVideoPath] = useState("");
  const [eventsPath, setEventsPath] = useState("");
  const [padding, setPadding] = useState(10);
  const [mergeGap, setMergeGap] = useState(25);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CreateClipsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [live, setLive] = useState<EventsLiveStatus | null>(null);
  const [exportNote, setExportNote] = useState<string | null>(null);
  const [prefsSavedNote, setPrefsSavedNote] = useState<string | null>(null);
  const rememberTimer = useRef<number | null>(null);
  const folderStateRef = useRef({ outputRoot: "", highlightsDir: "" });

  async function listEvents(dir: string, preferredGameId?: string) {
    try {
      const listed = await listDir(dir, [".json"]);
      setEventsDir(listed.directory);
      const files = listed.entries.filter((e) => !e.is_dir);
      setEventFiles(files);
      const gid = (preferredGameId ?? gameId).trim();
      if (gid) {
        const match = files.find((f) => eventMatchesGameId(f.name, gid));
        if (match) setEventsPath(match.path);
      }
      return listed.directory;
    } catch {
      setEventsDir(dir);
      setEventFiles([]);
      return dir;
    }
  }

  async function loadHighlights(directory?: string | null) {
    const listed = await listLocalHighlights(directory ?? null);
    setHighlightsDir(listed.directory);
    setHighlights(listed.entries);
    return listed.directory;
  }

  async function loadReplays(directory?: string | null) {
    const listed = await listLocalReplays(directory ?? null);
    setReplaysDir(listed.directory);
    setReplays(listed.items);
    return listed;
  }

  async function applyOutputRoot(root: string, opts?: { persist?: boolean; gameId?: string }) {
    const persist = opts?.persist !== false;
    const trimmed = root.trim();
    if (!trimmed) return;
    const eventDir = joinOsPath(trimmed, "Event");
    setOutputRoot(trimmed);
    const resolvedEvents = await listEvents(eventDir, opts?.gameId);
    if (persist) {
      await rememberPrefs({
        last_output_root: trimmed,
        last_events_dir: resolvedEvents,
      });
      setPrefsSavedNote("出力を保存しました");
    }
  }

  async function selectRofl(path: string, matchId?: string | null) {
    setRoflPath(path);
    setError(null);
    let gid = matchId?.trim() || "";
    try {
      const overview = await inspectRofl(path);
      if (overview.match_id) gid = overview.match_id;
    } catch {
      // filename match_id from list is enough as fallback
    }
    if (gid) {
      setGameId(gid);
      await rememberPrefs({
        fixed_target_rofl: path,
        last_game_id: gid,
      });
      if (eventsDir) await listEvents(eventsDir, gid);
    } else {
      await rememberPrefs({ fixed_target_rofl: path });
    }
  }

  useEffect(() => {
    getUiPreferences()
      .then(async (p) => {
        setPrefs(p);
        if (p.last_game_id) setGameId(p.last_game_id);
        if (p.fixed_target_rofl) setRoflPath(p.fixed_target_rofl);
        if (p.last_output_root) {
          await applyOutputRoot(p.last_output_root, {
            persist: false,
            gameId: p.last_game_id || undefined,
          });
        } else if (p.last_events_dir) {
          await listEvents(p.last_events_dir, p.last_game_id || undefined);
        }
        const replayList = await loadReplays(p.last_replays_dir ?? null);
        if (p.fixed_target_rofl) {
          const found = replayList.items.find((i) => i.path === p.fixed_target_rofl);
          if (found?.match_id && !p.last_game_id) setGameId(found.match_id);
        }
        await loadHighlights(p.last_highlights_dir ?? null);
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
      next.last_replays_dir === base.last_replays_dir &&
      next.last_video_dir === base.last_video_dir &&
      next.last_highlights_dir === base.last_highlights_dir &&
      next.last_events_dir === base.last_events_dir &&
      next.last_output_root === base.last_output_root &&
      next.last_game_id === base.last_game_id;
    if (unchanged) {
      setPrefs(base);
      return base;
    }
    return persist(next);
  }

  folderStateRef.current = { outputRoot, highlightsDir };

  async function rememberFoldersFromInputs() {
    const snap = folderStateRef.current;
    const root = snap.outputRoot.trim();
    if (root) {
      await applyOutputRoot(root, { persist: true, gameId });
      return;
    }
  }

  function scheduleRememberFolders() {
    if (rememberTimer.current != null) window.clearTimeout(rememberTimer.current);
    rememberTimer.current = window.setTimeout(() => {
      rememberFoldersFromInputs().catch((e) => setError(String(e)));
    }, 400);
  }

  async function browseOutput() {
    setError(null);
    try {
      const picked = await pickDirectory({
        title: "出力ベースを選択",
        initial: outputRoot || null,
      });
      if (picked.cancelled || !picked.path) return;
      await applyOutputRoot(picked.path, { persist: true, gameId });
    } catch (err) {
      setError(String(err));
    }
  }

  async function browseReplays() {
    setError(null);
    try {
      const picked = await pickDirectory({
        title: "LoL Replays フォルダを選択",
        initial: replaysDir || null,
      });
      if (picked.cancelled || !picked.path) return;
      const listed = await loadReplays(picked.path);
      await rememberPrefs({ last_replays_dir: listed.directory });
      setPrefsSavedNote("Replays フォルダを保存しました");
    } catch (err) {
      setError(String(err));
    }
  }

  async function browseHighlights() {
    setError(null);
    try {
      const picked = await pickDirectory({
        title: "LoL Highlights フォルダを選択",
        initial: highlightsDir || null,
      });
      if (picked.cancelled || !picked.path) return;
      const resolved = await loadHighlights(picked.path);
      await rememberPrefs({ last_highlights_dir: resolved });
      setPrefsSavedNote("Highlights フォルダを保存しました");
    } catch (err) {
      setError(String(err));
    }
  }

  async function refreshLive(opts?: { harvest?: boolean }) {
    const doHarvest = opts?.harvest !== false;
    setBusy(true);
    setError(null);
    setExportNote(null);
    try {
      if (!doHarvest) {
        const status = await getLiveEvents();
        setLive(status);
        if (status.warning) setExportNote(status.warning);
        return;
      }

      const root = outputRoot.trim();
      const gid = gameId.trim();
      if (!root) {
        const status = await harvestEvents(16);
        setLive(status);
        setExportNote(
          status.warning
            ? status.warning
            : "出力ベース未設定のためイベント/スタッツは未保存",
        );
        return;
      }
      if (!gid) {
        setError("先に ROFL を選んでゲーム ID を取得してください");
        return;
      }

      await applyOutputRoot(root, { persist: true, gameId: gid });
      const response = await exportEvents({
        directory: root,
        filename: "events.json",
        game_id: gid,
        include_stats: true,
        harvest: true,
        harvest_speed: 16,
      });
      const status = await getLiveEvents();
      setLive(status);
      setGameId(response.game_id);
      setExportNote(
        `保存 · ${response.event_count} イベント · スタッツ · ${response.game_id}_events.json`,
      );
      setEventsPath(response.path);
      setEventsDir(response.game_dir);
      await listEvents(response.game_dir, response.game_id);
      await rememberPrefs({
        last_events_dir: response.game_dir,
        last_output_root: root,
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
      setError("Highlights から webm（または動画）を選択してください");
      return;
    }
    if (!eventsPath) {
      setError("イベント JSON を選択してください（試合を走査して保存）");
      return;
    }
    if (!gameId.trim()) {
      setError("先に ROFL を選んでゲーム ID を取得してください");
      return;
    }
    if (!outputRoot.trim()) {
      setError("出力ベースを選んでください");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      await applyOutputRoot(outputRoot.trim(), { persist: true, gameId });
      await rememberPrefs({
        last_highlights_dir: highlightsDir || null,
        last_game_id: gameId.trim(),
        fixed_target_rofl: roflPath || null,
      });
      const response = await autoSplitClips({
        source_video_path: videoPath,
        events_path: eventsPath,
        original_match_id: gameId.trim(),
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

  const gid = gameId.trim() || "…";
  const base = outputRoot.replace(/[/\\]+$/, "") || "…";
  const visibleEvents = gameId.trim()
    ? eventFiles.filter((f) => eventMatchesGameId(f.name, gameId))
    : eventFiles;
  const visibleHighlights = gameId.trim()
    ? highlights.filter((f) => eventMatchesGameId(f.name, gameId))
    : highlights;

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
          <button className="btn" disabled={busy} onClick={() => browseOutput()}>
            参照…
          </button>
        </div>
        <p className="path-preview mono">
          {base}\Event · Replay · stats · Clip\{gid}
        </p>
        <p className="path-preview mono">
          Event/{gid}_events.json · stats/{gid}_stats_*.json
        </p>
        {prefsSavedNote ? <p className="success">{prefsSavedNote}</p> : null}
      </div>

      <div className="result-box">
        <h3>リプレイ（ROFL）</h3>
        <p className="path-preview mono">{roflPath || replaysDir || "—"}</p>
        <p className="status-line mono">ゲーム ID · {gid}</p>
        <div className="row" style={{ marginBottom: 8 }}>
          <button className="btn" disabled={busy} onClick={() => browseReplays()}>
            Replays 参照…
          </button>
          <button
            className="btn"
            disabled={busy}
            onClick={() => loadReplays(replaysDir || null).catch((e) => setError(String(e)))}
          >
            再読込
          </button>
        </div>
        <div className="file-list">
          {replays.map((r) => (
            <button
              key={r.path}
              className={`file-item ${roflPath === r.path ? "active" : ""}`}
              onClick={() => selectRofl(r.path, r.match_id)}
            >
              {r.filename}
              {r.match_id ? ` · ${r.match_id}` : ""}
            </button>
          ))}
        </div>
      </div>

      <div className="result-box">
        <h3>イベント</h3>
        <p className="status-line mono">{liveLabel}</p>
        {live?.warning ? <p className="error">{live.warning}</p> : null}
        <div className="row">
          <button className="btn primary" disabled={busy} onClick={() => refreshLive({ harvest: true })}>
            {busy ? "走査中…" : "試合を走査して保存"}
          </button>
          <button className="btn" disabled={busy} onClick={() => refreshLive({ harvest: false })}>
            現在位置のみ
          </button>
        </div>
        {exportNote ? <p className="success">{exportNote}</p> : null}
      </div>

      <div className="split-2">
        <div className="stack">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3>Highlights（webm）</h3>
            <button className="btn ghost" disabled={busy} onClick={() => browseHighlights()}>
              参照…
            </button>
          </div>
          <p className="path-preview mono">{highlightsDir || "—"}</p>
          <p className="hint">選択した webm は実行時に {base}\Replay へ mp4 変換します</p>
          <div className="file-list">
            {visibleHighlights.map((v) => (
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
        <div className="stack">
          <h3>イベント JSON（Event）</h3>
          <p className="path-preview mono">{eventsDir || "—"}</p>
          <div className="file-list">
            {visibleEvents.map((v) => (
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
            {result.converted ? " · Highlights→Replay mp4 変換済み" : ""}
          </p>
          <p className="mono path-preview">{result.output_dir}</p>
          {result.source_video ? (
            <p className="mono path-preview">{result.source_video}</p>
          ) : null}
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

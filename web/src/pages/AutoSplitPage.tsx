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
  patchUiPreferences,
  pickDirectory,
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

function matchesGameId(name: string, gameId: string): boolean {
  const gid = gameId.trim().toLowerCase();
  if (!gid) return false;
  const lower = name.toLowerCase();
  return lower.startsWith(`${gid}_`) || lower.includes(gid.toLowerCase());
}

function pickBestEvent(files: FsEntry[], gameId: string): FsEntry | null {
  const gid = gameId.trim().toLowerCase();
  if (!gid) return null;
  const matches = files.filter((f) => matchesGameId(f.name, gid));
  if (!matches.length) return null;
  const exact = matches.find((f) => f.name.toLowerCase() === `${gid}_events.json`);
  return exact ?? matches[0];
}

/** Prefer already-converted Replay mp4, else largest Highlights match (full-match webm). */
function pickBestVideo(
  highlights: FsEntry[],
  replayVideos: FsEntry[],
  gameId: string,
): { path: string; label: string; source: "replay" | "highlights" } | null {
  const gid = gameId.trim();
  if (!gid) return null;
  const replayMatches = replayVideos.filter((f) => matchesGameId(f.name, gid));
  if (replayMatches.length) {
    const best = [...replayMatches].sort(
      (a, b) => (b.size_bytes ?? 0) - (a.size_bytes ?? 0) || b.name.localeCompare(a.name),
    )[0];
    return { path: best.path, label: best.name, source: "replay" };
  }
  const hlMatches = highlights.filter((f) => matchesGameId(f.name, gid));
  if (!hlMatches.length) return null;
  const best = [...hlMatches].sort(
    (a, b) => (b.size_bytes ?? 0) - (a.size_bytes ?? 0) || b.name.localeCompare(a.name),
  )[0];
  return { path: best.path, label: best.name, source: "highlights" };
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
  const [replayVideos, setReplayVideos] = useState<FsEntry[]>([]);
  const [eventsDir, setEventsDir] = useState("");
  const [eventFiles, setEventFiles] = useState<FsEntry[]>([]);
  const [videoPath, setVideoPath] = useState("");
  const [videoSource, setVideoSource] = useState<"replay" | "highlights" | "">("");
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
  const folderStateRef = useRef({ outputRoot: "" });

  function applyResolvedPaths(
    gid: string,
    events: FsEntry[],
    hl: FsEntry[],
    replayVids: FsEntry[],
  ) {
    const event = pickBestEvent(events, gid);
    setEventsPath(event?.path ?? "");
    const video = pickBestVideo(hl, replayVids, gid);
    setVideoPath(video?.path ?? "");
    setVideoSource(video?.source ?? "");
  }

  async function listEvents(dir: string): Promise<FsEntry[]> {
    try {
      const listed = await listDir(dir, [".json"]);
      setEventsDir(listed.directory);
      const files = listed.entries.filter((e) => !e.is_dir);
      setEventFiles(files);
      return files;
    } catch {
      setEventsDir(dir);
      setEventFiles([]);
      return [];
    }
  }

  async function listReplayVideos(dir: string): Promise<FsEntry[]> {
    try {
      const listed = await listDir(dir, [".mp4", ".mkv", ".mov", ".avi", ".webm"]);
      const files = listed.entries.filter((e) => !e.is_dir);
      setReplayVideos(files);
      return files;
    } catch {
      setReplayVideos([]);
      return [];
    }
  }

  async function loadHighlights(directory?: string | null): Promise<FsEntry[]> {
    const listed = await listLocalHighlights(directory ?? null);
    setHighlightsDir(listed.directory);
    setHighlights(listed.entries);
    return listed.entries;
  }

  async function loadReplays(directory?: string | null) {
    const listed = await listLocalReplays(directory ?? null);
    setReplaysDir(listed.directory);
    setReplays(listed.items);
    return listed;
  }

  async function rememberPrefs(partial: Partial<UiPreferences>) {
    const saved = await patchUiPreferences(partial);
    setPrefs(saved);
    return saved;
  }

  async function refreshMatchedFiles(gid: string, root?: string) {
    const base = (root ?? outputRoot).trim();
    const eventDir = base ? joinOsPath(base, "Event") : eventsDir;
    const replayDir = base ? joinOsPath(base, "Replay") : "";
    const [events, hl, replayVids] = await Promise.all([
      eventDir ? listEvents(eventDir) : Promise.resolve(eventFiles),
      loadHighlights(highlightsDir || null),
      replayDir ? listReplayVideos(replayDir) : Promise.resolve(replayVideos),
    ]);
    if (gid.trim()) applyResolvedPaths(gid, events, hl, replayVids);
    return {
      event: pickBestEvent(events, gid),
      video: pickBestVideo(hl, replayVids, gid),
    };
  }

  async function applyOutputRoot(root: string, opts?: { persist?: boolean; gameId?: string }) {
    const persist = opts?.persist !== false;
    const trimmed = root.trim();
    if (!trimmed) return;
    setOutputRoot(trimmed);
    const eventDir = joinOsPath(trimmed, "Event");
    const replayDir = joinOsPath(trimmed, "Replay");
    const [events, replayVids] = await Promise.all([
      listEvents(eventDir),
      listReplayVideos(replayDir),
    ]);
    const gid = (opts?.gameId ?? gameId).trim();
    if (gid) applyResolvedPaths(gid, events, highlights, replayVids);
    if (persist) {
      await rememberPrefs({
        last_output_root: trimmed,
        last_events_dir: eventDir,
      });
      setPrefsSavedNote("出力を保存しました");
    }
  }

  async function selectRofl(path: string, matchId?: string | null) {
    setRoflPath(path);
    setError(null);
    setResult(null);
    let gid = matchId?.trim() || "";
    try {
      const overview = await inspectRofl(path);
      if (overview.match_id) gid = overview.match_id;
    } catch {
      // filename match_id from list is enough as fallback
    }
    if (!gid) {
      await rememberPrefs({ fixed_target_rofl: path });
      setError("この ROFL からゲーム ID を取得できませんでした");
      return;
    }
    setGameId(gid);
    await rememberPrefs({
      fixed_target_rofl: path,
      last_game_id: gid,
    });
    await refreshMatchedFiles(gid);
  }

  useEffect(() => {
    getUiPreferences()
      .then(async (p) => {
        setPrefs(p);
        const gid = p.last_game_id || "";
        if (gid) setGameId(gid);
        if (p.fixed_target_rofl) setRoflPath(p.fixed_target_rofl);
        if (p.last_output_root) {
          await applyOutputRoot(p.last_output_root, { persist: false, gameId: gid });
        } else if (p.last_events_dir) {
          await listEvents(p.last_events_dir);
        }
        const replayList = await loadReplays(p.last_replays_dir ?? null);
        if (p.fixed_target_rofl) {
          const found = replayList.items.find((i) => i.path === p.fixed_target_rofl);
          if (found?.match_id && !gid) setGameId(found.match_id);
        }
        const hl = await loadHighlights(p.last_highlights_dir ?? null);
        const resolvedGid = gid || p.last_game_id || "";
        if (resolvedGid) {
          const events = p.last_output_root
            ? await listEvents(joinOsPath(p.last_output_root, "Event"))
            : eventFiles;
          const replayVids = p.last_output_root
            ? await listReplayVideos(joinOsPath(p.last_output_root, "Replay"))
            : [];
          applyResolvedPaths(resolvedGid, events, hl, replayVids);
        }
      })
      .catch((err) => setError(String(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount only
  }, []);

  folderStateRef.current = { outputRoot };

  async function rememberFoldersFromInputs() {
    const root = folderStateRef.current.outputRoot.trim();
    if (root) await applyOutputRoot(root, { persist: true, gameId });
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
      const hl = await loadHighlights(picked.path);
      await rememberPrefs({ last_highlights_dir: picked.path });
      setPrefsSavedNote("Highlights フォルダを保存しました");
      if (gameId.trim()) {
        applyResolvedPaths(gameId, eventFiles, hl, replayVideos);
      }
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
        setError("先に ROFL を選んでください");
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
      await rememberPrefs({
        last_events_dir: response.game_dir,
        last_output_root: root,
        last_game_id: response.game_id,
      });
      await refreshMatchedFiles(response.game_id, root);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function run(dryRun: boolean) {
    const gid = gameId.trim();
    if (!gid) {
      setError("先に ROFL を選んでください");
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
      const matched = await refreshMatchedFiles(gid);
      const resolvedEventsPath = matched.event?.path || "";
      const resolvedVideoPath = matched.video?.path || "";

      if (!resolvedVideoPath) {
        setError(`ゲーム ID ${gid} に合う Highlights / Replay 動画が見つかりません`);
        return;
      }
      if (!resolvedEventsPath) {
        setError(`ゲーム ID ${gid} のイベント JSON がありません（試合を走査して保存）`);
        return;
      }

      await applyOutputRoot(outputRoot.trim(), { persist: true, gameId: gid });
      await rememberPrefs({
        last_highlights_dir: highlightsDir || null,
        last_game_id: gid,
        fixed_target_rofl: roflPath || null,
      });
      const response = await autoSplitClips({
        source_video_path: resolvedVideoPath,
        events_path: resolvedEventsPath,
        original_match_id: gid,
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
      await refreshMatchedFiles(response.game_id || gid);
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
  const hlMatchCount = gameId.trim()
    ? highlights.filter((f) => matchesGameId(f.name, gameId)).length
    : 0;

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
        {prefs?.settings_path ? (
          <p className="path-preview mono">設定 · {prefs.settings_path}</p>
        ) : null}
        {prefsSavedNote ? <p className="success">{prefsSavedNote}</p> : null}
      </div>

      <div className="result-box">
        <h3>リプレイ（ROFL）</h3>
        <p className="hint">ROFL を選ぶとゲーム ID から Event / 動画を自動で確定します</p>
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

      <div className="result-box overview-card">
        <h3>自動マッチ</h3>
        <dl>
          <div>
            <dt>Event</dt>
            <dd className="mono">
              {eventsPath
                ? eventsPath
                : gameId.trim()
                  ? "未作成（下で走査して保存）"
                  : "—"}
            </dd>
          </div>
          <div>
            <dt>動画</dt>
            <dd className="mono">
              {videoPath
                ? `${videoPath}${videoSource === "replay" ? " · Replay" : " · Highlights"}`
                : gameId.trim()
                  ? "該当ファイルなし"
                  : "—"}
            </dd>
          </div>
        </dl>
        {hlMatchCount > 1 ? (
          <p className="hint">Highlights 候補 {hlMatchCount} 件 → サイズ最大を採用</p>
        ) : null}
        <div className="row" style={{ marginTop: 8 }}>
          <button className="btn ghost" disabled={busy} onClick={() => browseHighlights()}>
            Highlights フォルダ…
          </button>
          <button
            className="btn ghost"
            disabled={busy || !gameId.trim()}
            onClick={() => refreshMatchedFiles(gameId).catch((e) => setError(String(e)))}
          >
            再マッチ
          </button>
        </div>
      </div>

      <div className="result-box">
        <h3>イベント取得</h3>
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

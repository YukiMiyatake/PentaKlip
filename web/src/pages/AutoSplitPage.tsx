import { useEffect, useState } from "react";
import {
  autoSplitClips,
  exportEvents,
  getLiveEvents,
  harvestEvents,
  getUiPreferences,
  inspectRofl,
  listDir,
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
  const [gameIdSource, setGameIdSource] = useState<string | null>(null);

  async function fillGameIdFromRofl(roflPath: string | null | undefined, fallbackId?: string | null) {
    if (fallbackId) {
      setGameId(fallbackId);
      setGameIdSource("prefs/db original");
    }
    if (!roflPath) return;
    try {
      const overview = await inspectRofl(roflPath);
      // Prefer DB/prefs original id when present; otherwise ROFL meta/fingerprint.
      if (!fallbackId && overview.match_id) {
        setGameId(overview.match_id);
        setGameIdSource(overview.match_id_source ?? "rofl");
      } else if (fallbackId) {
        // keep fallback, but show that ROFL meta is available
        if (overview.match_id_source && overview.match_id_source !== "filename") {
          setGameIdSource(`prefs/db original (rofl ${overview.match_id_source}: ${overview.match_id})`);
        }
      }
    } catch {
      if (!fallbackId) {
        const inferred = inferGameIdFromName(roflPath);
        if (inferred) {
          setGameId(inferred);
          setGameIdSource("filename");
        }
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
        if (p.last_events_dir) {
          setEventsDir(p.last_events_dir);
          try {
            const listed = await listDir(p.last_events_dir, [".json"]);
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

  async function rememberFoldersFromInputs() {
    const partial: Partial<UiPreferences> = {};
    const root = outputRoot.trim();
    const video = videoDir.trim();
    const events = eventsDir.trim();
    const gid = gameId.trim();
    if (root) partial.last_output_root = root;
    if (video) partial.last_video_dir = video;
    if (events) partial.last_events_dir = events;
    if (gid) partial.last_game_id = gid;
    if (Object.keys(partial).length === 0) return;
    await rememberPrefs(partial);
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
      setOutputRoot(response.game_dir.replace(/[/\\][^/\\]+$/, ""));
      const listed = await listDir(response.game_dir, [".json"]);
      setEventFiles(listed.entries.filter((e) => !e.is_dir));
      await rememberPrefs({
        last_events_dir: response.game_dir,
        last_output_root: response.game_dir.replace(/[/\\][^/\\]+$/, ""),
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

  const previewDir =
    outputRoot && gameId.trim()
      ? `${outputRoot.replace(/[/\\]+$/, "")}\\${gameId.trim()}`
      : gameId.trim()
        ? `{出力ルート}\\${gameId.trim()}`
        : "（ゲームID未設定）";

  return (
    <section className="panel">
      <h2>自動クリップ切り分け</h2>
      <p className="hint">
        イベント JSON と切り出しクリップは、出力ルート配下の <span className="mono">ゲームID</span>{" "}
        フォルダにまとめて保存します。ffmpeg が必要です（ツールタブで導入）。
        <span className="mono">.webm</span> は切り分け前に自動で MP4 変換します（ゲームフォルダにキャッシュ）。
      </p>

      <div className="result-box" style={{ marginBottom: 16 }}>
        <h3>出力先（ゲームIDフォルダ）</h3>
        <div className="row">
          <input
            className="text-input grow"
            placeholder="出力ルート（例: D:\\PentaKlip\\matches）"
            value={outputRoot}
            onChange={(e) => setOutputRoot(e.target.value)}
            onBlur={() => rememberFoldersFromInputs().catch((e) => setError(String(e)))}
          />
          <input
            className="text-input"
            style={{ width: 260 }}
            placeholder="ゲームID（ROFL meta / 元マッチID）"
            value={gameId}
            onChange={(e) => {
              setGameId(e.target.value);
              setGameIdSource("manual");
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
            固定ROFLから取得
          </button>
        </div>
        <p className="mono hint">保存先プレビュー: {previewDir}</p>
        {gameIdSource ? <p className="hint">ゲームID出典: {gameIdSource}</p> : null}
        <p className="hint">
          ROFL の gameId（数だけなら <span className="mono">JP1-</span> を付与）やファイル名、DB
          の元マッチIDから自動取得します。フォルダ名が衝突すると{" "}
          <span className="mono">ID-1</span> のように連番します。
        </p>
      </div>

      <div className="result-box" style={{ marginBottom: 16 }}>
        <h3>イベント JSON 作成</h3>
        <p className="hint">
          「試合を走査して取得」はリプレイを先頭から高速再生し、序盤〜終盤のイベントを蓄積します（終端 Seek
          だけでは Live Client に序盤が入らないことがあります）。Replay API が必要です（
          <span className="mono">game.cfg</span> の <span className="mono">[General]</span> に{" "}
          <span className="mono">EnableReplayApi=1</span>）。JSON は生データのまま、戦闘統合は切り分け時です。
        </p>
        <p className="mono">{liveLabel}</p>
        {live?.warning ? <p className="hint">{live.warning}</p> : null}
        <div className="row">
          <button className="btn primary" disabled={busy} onClick={() => refreshLive({ harvest: true })}>
            {busy ? "走査中…" : "試合を走査して取得"}
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
              onChange={(e) => setVideoDir(e.target.value)}
              onBlur={() => rememberFoldersFromInputs().catch((e) => setError(String(e)))}
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
              onChange={(e) => setEventsDir(e.target.value)}
              onBlur={() => rememberFoldersFromInputs().catch((e) => setError(String(e)))}
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
                onClick={() => selectEvents(v.path)}
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
        <label>
          戦闘マージ間隔（秒）{" "}
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
          自動切り分け実行
        </button>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {result ? (
        <div className="result-box">
          <p className="success">
            {result.clip_count} クリップ
            {result.game_id ? ` · ${result.game_id}` : ""}
            {result.converted ? " · webm→mp4 変換済み" : ""} → {result.output_dir}
          </p>
          <ul>
            {result.clips.map((c) => (
              <li key={c.output_path}>
                <span className="mono">
                  {c.kind} {c.start_sec.toFixed(0)}-{c.end_sec.toFixed(0)}s
                  {c.label ? ` (${c.label})` : ""}
                </span>{" "}
                {c.output_path}
              </li>
            ))}
          </ul>
          {result.event_coverage ? (
            <div className="hint" style={{ marginTop: 8 }}>
              <p>
                イベント JSON: {result.event_coverage.total_events ?? 0} 件 / クリップ対象{" "}
                {JSON.stringify(result.event_coverage.used_for_clips ?? {})}
              </p>
              {result.event_coverage.ignored &&
              Object.keys(result.event_coverage.ignored).length > 0 ? (
                <p>
                  未使用（GameStart 等）: {JSON.stringify(result.event_coverage.ignored)}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

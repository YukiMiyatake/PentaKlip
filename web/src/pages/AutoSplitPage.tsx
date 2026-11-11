import { useEffect, useRef, useState } from "react";
import {
  autoSplitClips,
  exportEvents,
  getLiveEvents,
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
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CreateClipsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [live, setLive] = useState<EventsLiveStatus | null>(null);
  const [watching, setWatching] = useState(false);
  const [exportFilename, setExportFilename] = useState("events.json");
  const [exportNote, setExportNote] = useState<string | null>(null);
  const [gameIdSource, setGameIdSource] = useState<string | null>(null);
  const watchRef = useRef<number | null>(null);

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
          const listed = await listDir(p.last_video_dir, [".mp4", ".mkv", ".mov", ".avi", ".webm"]);
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
        .then((status) => {
          setLive(status);
          if (!gameId && status.game_id) setGameId(status.game_id);
        })
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
  }, [watching, gameId]);

  async function persist(next: UiPreferences) {
    setPrefs(await putUiPreferences(next));
  }

  async function loadVideos() {
    const listed = await listDir(videoDir, [".mp4", ".mkv", ".mov", ".avi", ".webm"]);
    setVideoDir(listed.directory);
    setVideos(listed.entries.filter((e) => !e.is_dir));
    if (prefs) await persist({ ...prefs, last_video_dir: listed.directory });
  }

  async function loadEvents() {
    const listed = await listDir(eventsDir, [".json"]);
    setEventsDir(listed.directory);
    setEventFiles(listed.entries.filter((e) => !e.is_dir));
    const inferred = inferGameIdFromName(listed.directory);
    if (inferred && !gameId) setGameId(inferred);
    if (prefs) {
      await persist({
        ...prefs,
        last_events_dir: listed.directory,
        last_game_id: inferred || prefs.last_game_id,
      });
    }
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

  async function refreshLive() {
    setError(null);
    try {
      const status = await getLiveEvents();
      setLive(status);
      if (!gameId && status.game_id) setGameId(status.game_id);
    } catch (err) {
      setError(String(err));
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
      });
      setExportNote(
        `保存しました: ${response.path}（${response.event_count} イベント / ${response.game_id}）`,
      );
      setEventsPath(response.path);
      setEventsDir(response.game_dir);
      setOutputRoot(response.game_dir.replace(/[/\\][^/\\]+$/, ""));
      const listed = await listDir(response.game_dir, [".json"]);
      setEventFiles(listed.entries.filter((e) => !e.is_dir));
      if (prefs) {
        await persist({
          ...prefs,
          last_events_dir: response.game_dir,
          last_output_root: response.game_dir.replace(/[/\\][^/\\]+$/, ""),
          last_game_id: response.game_id,
        });
      }
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
        original_match_id: gameId.trim() || null,
        padding_before_sec: padding,
        padding_after_sec: padding,
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
      (live.game_id ? ` · id ${live.game_id}` : "")
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
          置き換え後も安定するよう、ROFL メタ（無い場合は指紋）や DB の元マッチIDを優先します。
          フォルダ名が衝突すると <span className="mono">ID-1</span> のように連番します。
        </p>
      </div>

      <div className="result-box" style={{ marginBottom: 16 }}>
        <h3>イベント JSON 作成</h3>
        <p className="hint">
          LoL リプレイ再生中に Live Client（2999）から取得し、
          <span className="mono">{"{出力ルート}/{ゲームID}/events.json"}</span> に保存します。
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
          <input
            className="text-input"
            style={{ width: 180 }}
            placeholder="ファイル名"
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

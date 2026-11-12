import { useEffect, useState } from "react";
import {
  getUiPreferences,
  inspectRofl,
  installReplay,
  listDir,
  listLocalReplays,
  pickDirectory,
  putUiPreferences,
} from "../api";
import { RoflOverviewCard } from "../components/RoflOverviewCard";
import type { FsEntry, LocalReplayItem, RoflOverview, UiPreferences } from "../types";

function normPath(path: string | null | undefined): string {
  return (path || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
}

function fileNameOf(path: string | null | undefined): string {
  if (!path) return "";
  const parts = path.replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || "";
}

function findRememberedTarget(
  items: LocalReplayItem[],
  remembered: string | null | undefined,
): LocalReplayItem | null {
  if (!remembered) return null;
  const exact = items.find((item) => normPath(item.path) === normPath(remembered));
  if (exact) return exact;
  const name = fileNameOf(remembered).toLowerCase();
  if (!name) return null;
  return items.find((item) => item.filename.toLowerCase() === name) ?? null;
}

export function ReplacePage() {
  const [prefs, setPrefs] = useState<UiPreferences | null>(null);
  const [replaysDir, setReplaysDir] = useState("");
  const [defaultReplaysDir, setDefaultReplaysDir] = useState("");
  const [locals, setLocals] = useState<LocalReplayItem[]>([]);
  const [targetPath, setTargetPath] = useState<string>("");
  const [targetOverview, setTargetOverview] = useState<RoflOverview | null>(null);
  const [sourceDir, setSourceDir] = useState<string>("");
  const [entries, setEntries] = useState<FsEntry[]>([]);
  const [sourcePath, setSourcePath] = useState<string>("");
  const [sourceOverview, setSourceOverview] = useState<RoflOverview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadLocalReplays(directory?: string | null) {
    const listed = await listLocalReplays(directory ?? null);
    setReplaysDir(listed.directory);
    setDefaultReplaysDir(listed.default_directory);
    setLocals(listed.items);
    return listed;
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = await getUiPreferences();
        if (cancelled) return;
        setPrefs(p);
        const listed = await loadLocalReplays(p.last_replays_dir ?? null);
        if (cancelled) return;
        if (p.fixed_target_rofl) {
          const match = findRememberedTarget(listed.items, p.fixed_target_rofl);
          const pathToUse = match?.path ?? p.fixed_target_rofl;
          try {
            const overview = await inspectRofl(pathToUse);
            if (cancelled) return;
            setTargetPath(pathToUse);
            setTargetOverview(overview);
            // Normalize remembered path when the file still exists under a different spelling.
            if (pathToUse !== p.fixed_target_rofl) {
              await rememberPrefs({
                fixed_target_rofl: pathToUse,
                last_replays_dir: listed.directory,
              });
            }
          } catch {
            // Remembered file missing — keep preference until user picks another.
          }
        }
        const dir = p.last_source_dir || "";
        if (dir) {
          setSourceDir(dir);
          try {
            const sourceListed = await listDir(dir, [".rofl"]);
            if (!cancelled) {
              setEntries(sourceListed.entries);
              setSourceDir(sourceListed.directory);
            }
          } catch {
            // Keep remembered path even if the folder is temporarily missing.
          }
        }
      } catch (err) {
        if (!cancelled) setError(String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function persist(next: UiPreferences) {
    const saved = await putUiPreferences(next);
    setPrefs(saved);
  }

  async function rememberPrefs(partial: Partial<UiPreferences>) {
    const base = prefs ?? (await getUiPreferences());
    const next: UiPreferences = { ...base, ...partial };
    const unchanged =
      next.fixed_target_rofl === base.fixed_target_rofl &&
      next.last_source_dir === base.last_source_dir &&
      next.last_replays_dir === base.last_replays_dir &&
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

  async function onSelectTarget(path: string) {
    setError(null);
    setTargetPath(path);
    if (!path) {
      setTargetOverview(null);
      await rememberPrefs({ fixed_target_rofl: null });
      return;
    }
    try {
      const overview = await inspectRofl(path);
      setTargetOverview(overview);
      await rememberPrefs({
        fixed_target_rofl: path,
        last_replays_dir: replaysDir || null,
      });
      setMessage("置き換え先を保存しました");
    } catch (err) {
      setError(String(err));
    }
  }

  async function onBrowseReplaysDir() {
    setError(null);
    try {
      const picked = await pickDirectory({
        title: "LoL リプレイフォルダを選択",
        initial: replaysDir || defaultReplaysDir || null,
      });
      if (picked.cancelled || !picked.path) return;
      const listed = await loadLocalReplays(picked.path);
      const remembered = prefs?.fixed_target_rofl || targetPath;
      const match = findRememberedTarget(listed.items, remembered);
      if (match) {
        setTargetPath(match.path);
        try {
          setTargetOverview(await inspectRofl(match.path));
        } catch {
          setTargetOverview(null);
        }
        await rememberPrefs({
          last_replays_dir: listed.directory,
          fixed_target_rofl: match.path,
        });
        setMessage(`フォルダ更新 · ${match.filename}`);
      } else {
        await rememberPrefs({ last_replays_dir: listed.directory });
        setMessage("フォルダを更新しました");
      }
    } catch (err) {
      setError(String(err));
    }
  }

  async function onUseDefaultReplaysDir() {
    setError(null);
    try {
      const listed = await loadLocalReplays(defaultReplaysDir || null);
      const remembered = prefs?.fixed_target_rofl || targetPath;
      const match = findRememberedTarget(listed.items, remembered);
      if (match) {
        setTargetPath(match.path);
        try {
          setTargetOverview(await inspectRofl(match.path));
        } catch {
          setTargetOverview(null);
        }
        await rememberPrefs({
          last_replays_dir: listed.directory,
          fixed_target_rofl: match.path,
        });
      } else {
        await rememberPrefs({ last_replays_dir: listed.directory });
      }
      setMessage("既定フォルダに戻しました");
    } catch (err) {
      setError(String(err));
    }
  }

  async function onLoadSourceDir() {
    if (!sourceDir.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const listed = await listDir(sourceDir.trim(), [".rofl"]);
      setEntries(listed.entries);
      setSourceDir(listed.directory);
      await rememberPrefs({ last_source_dir: listed.directory });
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onSelectSource(path: string) {
    setSourcePath(path);
    setError(null);
    try {
      setSourceOverview(await inspectRofl(path));
    } catch (err) {
      setError(String(err));
    }
  }

  async function onCopy() {
    if (!targetPath || !sourcePath || !targetOverview) {
      setError("置き換え先とコピー元を選択してください");
      return;
    }
    const localId = targetOverview.match_id;
    if (!localId) {
      setError("置き換え先のマッチ ID をファイル名から取得できません");
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await installReplay({
        source_path: sourcePath,
        local_replay_id: localId,
        mode: "copy",
        dry_run: false,
        replays_dir: replaysDir || null,
      });
      setMessage(
        `コピー完了: 元ID ${result.original_match_id} → ${result.local_replay_id}` +
          (result.overwritten ? "（上書き）" : ""),
      );
      await loadLocalReplays(replaysDir || null);
      setTargetPath(result.installed_path);
      setTargetOverview(await inspectRofl(result.installed_path));
      await rememberPrefs({
        fixed_target_rofl: result.installed_path,
        last_replays_dir: replaysDir || null,
        last_game_id: result.original_match_id,
      });
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <h2>置き換え</h2>

      <div className="split-2">
        <div className="stack">
          <h3>置き換え先</h3>
          <div className="row">
            <input
              className="text-input grow mono"
              value={replaysDir}
              onChange={(e) => setReplaysDir(e.target.value)}
              onBlur={() => {
                const dir = replaysDir.trim();
                if (!dir) return;
                loadLocalReplays(dir)
                  .then((listed) =>
                    rememberPrefs({ last_replays_dir: listed.directory }),
                  )
                  .catch((err) => setError(String(err)));
              }}
              placeholder="Documents\League of Legends\Replays"
            />
            <button className="btn" disabled={busy} onClick={onBrowseReplaysDir}>
              参照…
            </button>
            <button
              className="btn"
              disabled={busy || !defaultReplaysDir}
              title={defaultReplaysDir || undefined}
              onClick={onUseDefaultReplaysDir}
            >
              既定に戻す
            </button>
          </div>
          <label className="field-label">.rofl</label>
          <select
            className="select"
            value={
              locals.find((item) => normPath(item.path) === normPath(targetPath))?.path ??
              targetPath
            }
            onChange={(e) => onSelectTarget(e.target.value)}
          >
            <option value="">選択…</option>
            {targetPath &&
            !locals.some((item) => normPath(item.path) === normPath(targetPath)) ? (
              <option value={targetPath}>{fileNameOf(targetPath)}（記憶中）</option>
            ) : null}
            {locals.map((item) => (
              <option key={item.path} value={item.path}>
                {item.filename}
              </option>
            ))}
          </select>
          <RoflOverviewCard overview={targetOverview} title="概要" />
        </div>

        <div className="stack">
          <h3>コピー元</h3>
          <div className="row">
            <input
              className="text-input grow"
              value={sourceDir}
              onChange={(e) => setSourceDir(e.target.value)}
              onBlur={() => {
                const dir = sourceDir.trim();
                if (!dir) return;
                rememberPrefs({ last_source_dir: dir }).catch((err) => setError(String(err)));
              }}
              placeholder="Downloads など"
            />
            <button
              className="btn"
              disabled={busy}
              onClick={() => {
                pickDirectory({
                  title: "コピー元（ダウンロードフォルダなど）を選択",
                  initial: sourceDir || null,
                })
                  .then(async (picked) => {
                    if (picked.cancelled || !picked.path) return;
                    setSourceDir(picked.path);
                    await rememberPrefs({ last_source_dir: picked.path });
                    const listed = await listDir(picked.path, [".rofl"]);
                    setEntries(listed.entries);
                    setSourceDir(listed.directory);
                    await rememberPrefs({ last_source_dir: listed.directory });
                  })
                  .catch((err) => setError(String(err)));
              }}
            >
              参照…
            </button>
            <button className="btn" disabled={busy} onClick={onLoadSourceDir}>
              一覧
            </button>
          </div>
          <div className="file-list">
            {entries
              .filter((e) => !e.is_dir)
              .map((entry) => (
                <button
                  key={entry.path}
                  className={`file-item ${sourcePath === entry.path ? "active" : ""}`}
                  onClick={() => onSelectSource(entry.path)}
                >
                  {entry.name}
                </button>
              ))}
          </div>
          <RoflOverviewCard overview={sourceOverview} title="概要" />
        </div>
      </div>

      <div className="row actions">
        <button className="btn primary" disabled={busy} onClick={onCopy}>
          コピー
        </button>
      </div>
      {message ? <p className="success">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}

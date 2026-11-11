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

export function ReplacePage() {
  const [prefs, setPrefs] = useState<UiPreferences | null>(null);
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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [p, local] = await Promise.all([getUiPreferences(), listLocalReplays()]);
        if (cancelled) return;
        setPrefs(p);
        setLocals(local);
        if (p.fixed_target_rofl) {
          setTargetPath(p.fixed_target_rofl);
          setTargetOverview(await inspectRofl(p.fixed_target_rofl));
        }
        const dir =
          p.last_source_dir ||
          (local[0] ? local[0].path.replace(/[^\\/]+$/, "") : "");
        if (dir) {
          setSourceDir(dir);
          try {
            const listed = await listDir(dir, [".rofl"]);
            if (!cancelled) setEntries(listed.entries);
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
    try {
      const overview = await inspectRofl(path);
      setTargetOverview(overview);
      await rememberPrefs({ fixed_target_rofl: path });
      setMessage("置き換え先を固定しました（選び直すまで維持）");
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
      });
      setMessage(
        `コピー完了: 元ID ${result.original_match_id} → ${result.local_replay_id}` +
          (result.overwritten ? "（上書き）" : ""),
      );
      setLocals(await listLocalReplays());
      setTargetOverview(await inspectRofl(result.installed_path));
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <h2>リプレイ置き換え</h2>
      <p className="hint">
        LoL フォルダのローカルリプレイを置き換え先として固定し、ダウンロードした
        .rofl をその ID 名でコピーします。元のゲーム ID はサーバ側 DB に保存されます。
      </p>

      <div className="split-2">
        <div>
          <h3>1. 置き換え先（LoL Replays・固定）</h3>
          <select
            className="select"
            value={targetPath}
            onChange={(e) => onSelectTarget(e.target.value)}
          >
            <option value="">選択…</option>
            {locals.map((item) => (
              <option key={item.path} value={item.path}>
                {item.filename}
              </option>
            ))}
          </select>
          <RoflOverviewCard overview={targetOverview} title="置き換え先の概要" />
        </div>

        <div>
          <h3>2. コピー元（前回フォルダを維持）</h3>
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
              placeholder="C:\Users\...\Downloads"
            />
            <button
              className="btn"
              disabled={busy}
              onClick={() => {
                pickDirectory({ title: "コピー元フォルダを選択", initial: sourceDir || null })
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
          <RoflOverviewCard overview={sourceOverview} title="コピー元の概要" />
        </div>
      </div>

      <div className="row" style={{ marginTop: 16 }}>
        <button className="btn primary" disabled={busy} onClick={onCopy}>
          コピーして貼り付け
        </button>
      </div>
      {message ? <p className="success">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}

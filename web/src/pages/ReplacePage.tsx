import { useEffect, useState } from "react";
import {
  getUiPreferences,
  inspectRofl,
  installReplay,
  listDir,
  listLocalReplays,
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
          const listed = await listDir(dir, [".rofl"]);
          if (!cancelled) setEntries(listed.entries);
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

  async function onSelectTarget(path: string) {
    setError(null);
    setTargetPath(path);
    try {
      const overview = await inspectRofl(path);
      setTargetOverview(overview);
      if (prefs) {
        await persist({ ...prefs, fixed_target_rofl: path });
      }
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
      if (prefs) {
        await persist({ ...prefs, last_source_dir: listed.directory });
      }
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
              placeholder="C:\Users\...\Downloads"
            />
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

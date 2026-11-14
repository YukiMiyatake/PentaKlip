import type { RoflOverview } from "../types";

type Props = {
  overview: RoflOverview | null;
  title: string;
};

export function RoflOverviewCard({ overview, title }: Props) {
  if (!overview) {
    return (
      <div className="overview-card empty">
        <h4>{title}</h4>
        <p>未選択</p>
      </div>
    );
  }

  const duration =
    overview.game_length_sec != null
      ? `${Math.floor(overview.game_length_sec / 60)}分 ${Math.round(overview.game_length_sec % 60)}秒`
      : "不明";

  return (
    <div className="overview-card">
      <h4>{title}</h4>
      <dl>
        <div>
          <dt>ファイル</dt>
          <dd>{overview.filename}</dd>
        </div>
        <div>
          <dt>マッチ ID</dt>
          <dd className="mono">
            {overview.match_id ?? "—"}
            {overview.match_id_source ? ` · ${overview.match_id_source}` : ""}
          </dd>
        </div>
        <div>
          <dt>形式</dt>
          <dd>{overview.format ?? "—"}</dd>
        </div>
        <div>
          <dt>バージョン</dt>
          <dd>{overview.game_version ?? "—"}</dd>
        </div>
        <div>
          <dt>試合時間</dt>
          <dd>{duration}</dd>
        </div>
        <div>
          <dt>モード</dt>
          <dd>{overview.game_mode ?? "—"}</dd>
        </div>
        <div>
          <dt>プラクティス</dt>
          <dd>
            {overview.is_practice_tool == null
              ? "不明"
              : overview.is_practice_tool
                ? "はい"
                : "いいえ"}
          </dd>
        </div>
        <div>
          <dt>人数</dt>
          <dd>{overview.player_count ?? "—"}</dd>
        </div>
      </dl>
      {overview.players.length > 0 ? (
        <p className="players">{overview.players.join(" · ")}</p>
      ) : null}
      {overview.note ? <p className="hint">{overview.note}</p> : null}
    </div>
  );
}

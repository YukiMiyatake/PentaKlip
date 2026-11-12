import { LANE_FILTER_LABELS } from "../lanes";
import {
  playerKey,
  type PlayerRef,
} from "../playerVisibility";

type Props = {
  players: PlayerRef[];
  hidden: ReadonlySet<string>;
  onChange: (next: Set<string>) => void;
  compact?: boolean;
};

export function PlayerVisibilityBar({
  players,
  hidden,
  onChange,
  compact = false,
}: Props) {
  if (players.length === 0) return null;

  function toggle(ref: PlayerRef) {
    const key = playerKey(ref.position, ref.player_id);
    const next = new Set(hidden);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onChange(next);
  }

  function showAll() {
    onChange(new Set());
  }

  const byLane = new Map<string, PlayerRef[]>();
  for (const ref of players) {
    const list = byLane.get(ref.position) ?? [];
    list.push(ref);
    byLane.set(ref.position, list);
  }

  return (
    <div
      className={`player-visibility${compact ? " compact" : ""}`}
      role="group"
      aria-label="プレイヤー表示"
    >
      <div className="player-visibility-head">
        <span className="hint">プレイヤー（スタッツ）</span>
        {hidden.size > 0 ? (
          <button type="button" className="btn ghost" onClick={showAll}>
            すべて表示
          </button>
        ) : null}
      </div>
      {[...byLane.entries()].map(([position, refs]) => (
        <div className="player-visibility-lane" key={position}>
          <span className="player-visibility-lane-label">
            {LANE_FILTER_LABELS[position as keyof typeof LANE_FILTER_LABELS] ??
              position}
          </span>
          <div className="player-visibility-chips">
            {refs.map((ref) => {
              const key = playerKey(ref.position, ref.player_id);
              const visible = !hidden.has(key);
              return (
                <button
                  key={key}
                  type="button"
                  className={`player-visibility-chip${visible ? " active" : ""}`}
                  aria-pressed={visible}
                  title={
                    visible
                      ? "クリックでスタッツ非表示"
                      : "クリックでスタッツ表示"
                  }
                  onClick={() => toggle(ref)}
                >
                  {ref.player_id}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

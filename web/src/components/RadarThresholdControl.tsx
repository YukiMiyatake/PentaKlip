import {
  RADAR_THRESHOLD_MAX,
  RADAR_THRESHOLD_MIN,
  RADAR_THRESHOLD_STEP,
} from "../radarScale";

type Props = {
  value: number;
  onChange: (next: number) => void;
  compact?: boolean;
  className?: string;
};

export function RadarThresholdControl({
  value,
  onChange,
  compact = false,
  className = "",
}: Props) {
  return (
    <label
      className={`radar-threshold${compact ? " compact" : ""}${className ? ` ${className}` : ""}`}
    >
      <span className="radar-threshold-label">
        スレッショルド
        <span className="mono"> {value}%</span>
      </span>
      <input
        type="range"
        min={RADAR_THRESHOLD_MIN}
        max={RADAR_THRESHOLD_MAX}
        step={RADAR_THRESHOLD_STEP}
        value={value}
        aria-label="レーダースレッショルド（最大値の上側何％を表示するか）"
        onChange={(e) => onChange(Number(e.target.value))}
      />
      {!compact ? (
        <span className="hint radar-threshold-hint">
          最大値の上側 N% をチャート全体に拡大（小さいほど差が見やすい / 100%
          で従来スケール）
        </span>
      ) : null}
    </label>
  );
}

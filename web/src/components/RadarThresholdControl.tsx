import {
  RADAR_SCALE_MODE_HINTS,
  RADAR_SCALE_MODE_LABELS,
  RADAR_SCALE_MODE_ORDER,
  RADAR_THRESHOLD_MAX,
  RADAR_THRESHOLD_MIN,
  RADAR_THRESHOLD_STEP,
  radarScaleUsesThreshold,
  type RadarScaleMode,
} from "../radarScale";

type Props = {
  mode: RadarScaleMode;
  thresholdPct: number;
  onModeChange: (next: RadarScaleMode) => void;
  onThresholdChange: (next: number) => void;
  compact?: boolean;
  className?: string;
};

export function RadarThresholdControl({
  mode,
  thresholdPct,
  onModeChange,
  onThresholdChange,
  compact = false,
  className = "",
}: Props) {
  const usesThreshold = radarScaleUsesThreshold(mode);
  const thresholdSuffix =
    mode === "center" || mode === "avg_outer"
      ? ` ±${thresholdPct}%`
      : ` ${thresholdPct}%`;

  return (
    <div
      className={`radar-scale-controls${compact ? " compact" : ""}${className ? ` ${className}` : ""}`}
    >
      <div
        className="radar-scale-mode-bar"
        role="toolbar"
        aria-label="レーダースケール方式"
      >
        {RADAR_SCALE_MODE_ORDER.map((option) => {
          const active = mode === option;
          return (
            <button
              key={option}
              type="button"
              className={`radar-scale-mode-btn${active ? " active" : ""}`}
              aria-pressed={active}
              title={RADAR_SCALE_MODE_HINTS[option]}
              onClick={() => onModeChange(option)}
            >
              {RADAR_SCALE_MODE_LABELS[option]}
            </button>
          );
        })}
      </div>

      {usesThreshold ? (
        <label className="radar-threshold">
          <span className="radar-threshold-label">
            スレッショルド
            <span className="mono">{thresholdSuffix}</span>
          </span>
          <input
            type="range"
            min={RADAR_THRESHOLD_MIN}
            max={RADAR_THRESHOLD_MAX}
            step={RADAR_THRESHOLD_STEP}
            value={thresholdPct}
            aria-label="レーダースレッショルド"
            onChange={(e) => onThresholdChange(Number(e.target.value))}
          />
        </label>
      ) : null}

      {!compact ? (
        <span className="hint radar-threshold-hint">
          {RADAR_SCALE_MODE_HINTS[mode]}
        </span>
      ) : null}
    </div>
  );
}

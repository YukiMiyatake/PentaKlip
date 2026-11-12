import {
  LANE_FILTER_ORDER,
  laneFilterLabel,
  type LaneFilter,
} from "../lanes";

type Props = {
  value: LaneFilter;
  onChange: (next: LaneFilter) => void;
  className?: string;
  /** Compact styling for OBS toolbar. */
  compact?: boolean;
};

export function LaneFilterBar({
  value,
  onChange,
  className = "",
  compact = false,
}: Props) {
  const options: LaneFilter[] = ["ALL", ...LANE_FILTER_ORDER];
  return (
    <div
      className={`lane-filter-bar${compact ? " compact" : ""}${className ? ` ${className}` : ""}`}
      role="toolbar"
      aria-label="レーン絞り込み"
    >
      {options.map((option) => {
        const active = value === option;
        return (
          <button
            key={option}
            type="button"
            className={`lane-filter-btn${active ? " active" : ""}`}
            aria-pressed={active}
            onClick={() => onChange(option)}
          >
            {laneFilterLabel(option)}
          </button>
        );
      })}
    </div>
  );
}

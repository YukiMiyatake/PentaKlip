import {
  RADAR_LAYOUT_MAX_COLS,
  RADAR_LAYOUT_MAX_ROWS,
  RADAR_LAYOUT_MIN_COLS,
  RADAR_LAYOUT_MIN_ROWS,
  type RadarLayoutState,
} from "../radarLayout";

type Props = {
  layout: RadarLayoutState;
  onColsChange: (cols: number) => void;
  onRowsChange: (rows: number) => void;
  onReset: () => void;
  compact?: boolean;
};

export function RadarLayoutControls({
  layout,
  onColsChange,
  onRowsChange,
  onReset,
  compact = false,
}: Props) {
  return (
    <div
      className={`radar-layout-controls${compact ? " compact" : ""}`}
      role="group"
      aria-label="レーダーグリッド"
    >
      <label className="radar-layout-dim">
        列
        <input
          type="number"
          min={RADAR_LAYOUT_MIN_COLS}
          max={RADAR_LAYOUT_MAX_COLS}
          value={layout.cols}
          onChange={(e) => onColsChange(Number(e.target.value))}
        />
      </label>
      <label className="radar-layout-dim">
        行
        <input
          type="number"
          min={RADAR_LAYOUT_MIN_ROWS}
          max={RADAR_LAYOUT_MAX_ROWS}
          value={layout.rows}
          onChange={(e) => onRowsChange(Number(e.target.value))}
        />
      </label>
      <button type="button" className="btn ghost" onClick={onReset}>
        配置リセット
      </button>
      {!compact ? (
        <span className="hint">ドラッグで移動・空きマス可</span>
      ) : null}
    </div>
  );
}

import {
  useMemo,
  useState,
  type DragEvent,
  type ReactNode,
} from "react";
import {
  RADAR_CELL_HEIGHT,
  RADAR_CELL_HEIGHT_COMPACT,
  RADAR_CELL_WIDTH,
  RADAR_CELL_WIDTH_COMPACT,
  ensureRadarLayout,
  type RadarLayoutState,
} from "../radarLayout";
import type { ChartSpec } from "../types";

type Props = {
  charts: ChartSpec[];
  layout: RadarLayoutState;
  onMove: (chartId: string, toSlot: number) => void;
  renderChart: (chart: ChartSpec) => ReactNode;
  editable?: boolean;
  compact?: boolean;
  className?: string;
};

export function RadarLayoutGrid({
  charts,
  layout,
  onMove,
  renderChart,
  editable = true,
  compact = false,
  className = "",
}: Props) {
  const chartIds = useMemo(() => charts.map((c) => c.chart_id), [charts]);
  const ensured = useMemo(
    () => ensureRadarLayout(layout, chartIds),
    [layout, chartIds],
  );
  const byId = useMemo(() => {
    const map = new Map<string, ChartSpec>();
    for (const c of charts) map.set(c.chart_id, c);
    return map;
  }, [charts]);
  const slotToId = useMemo(() => {
    const map = new Map<number, string>();
    for (const [id, slot] of Object.entries(ensured.positions)) {
      map.set(slot, id);
    }
    return map;
  }, [ensured.positions]);

  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [overSlot, setOverSlot] = useState<number | null>(null);

  const cellW = compact ? RADAR_CELL_WIDTH_COMPACT : RADAR_CELL_WIDTH;
  const cellH = compact ? RADAR_CELL_HEIGHT_COMPACT : RADAR_CELL_HEIGHT;
  const capacity = ensured.cols * ensured.rows;

  function onDragStart(chartId: string, ev: DragEvent) {
    if (!editable) return;
    setDraggingId(chartId);
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/pentaklip-radar-id", chartId);
    ev.dataTransfer.setData("text/plain", chartId);
  }

  function onDragEnd() {
    setDraggingId(null);
    setOverSlot(null);
  }

  function onDragOverSlot(slot: number, ev: DragEvent) {
    if (!editable || draggingId == null) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "move";
    if (overSlot !== slot) setOverSlot(slot);
  }

  function onDropSlot(slot: number, ev: DragEvent) {
    if (!editable) return;
    ev.preventDefault();
    const id =
      ev.dataTransfer.getData("text/pentaklip-radar-id") ||
      ev.dataTransfer.getData("text/plain") ||
      draggingId;
    setDraggingId(null);
    setOverSlot(null);
    if (!id) return;
    onMove(id, slot);
  }

  const cells: ReactNode[] = [];
  for (let slot = 0; slot < capacity; slot += 1) {
    const chartId = slotToId.get(slot);
    const chart = chartId ? byId.get(chartId) : undefined;
    const isOver = overSlot === slot && draggingId != null;
    const isDragging = chartId != null && draggingId === chartId;

    cells.push(
      <div
        key={`slot-${slot}`}
        className={[
          "radar-layout-cell",
          chart ? "filled" : "empty",
          isOver ? "drop-target" : "",
          isDragging ? "dragging" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        style={{ width: cellW, height: cellH }}
        onDragOver={(ev) => onDragOverSlot(slot, ev)}
        onDragLeave={() => {
          if (overSlot === slot) setOverSlot(null);
        }}
        onDrop={(ev) => onDropSlot(slot, ev)}
        data-slot={slot}
      >
        {chart ? (
          <div
            className="radar-layout-item"
            draggable={editable}
            onDragStart={(ev) => onDragStart(chart.chart_id, ev)}
            onDragEnd={onDragEnd}
          >
            {editable ? (
              <div className="radar-layout-handle" title="ドラッグで移動">
                ⋮⋮
              </div>
            ) : null}
            {renderChart(chart)}
          </div>
        ) : (
          <div className="radar-layout-placeholder" aria-hidden="true">
            {editable ? "空き" : ""}
          </div>
        )}
      </div>,
    );
  }

  return (
    <div
      className={`radar-layout-grid${compact ? " compact" : ""}${className ? ` ${className}` : ""}`}
      style={{
        gridTemplateColumns: `repeat(${ensured.cols}, ${cellW}px)`,
        gridTemplateRows: `repeat(${ensured.rows}, ${cellH}px)`,
      }}
    >
      {cells}
    </div>
  );
}

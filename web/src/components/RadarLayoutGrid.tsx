import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
} from "react";
import {
  RADAR_CELL_HEIGHT,
  RADAR_CELL_HEIGHT_COMPACT,
  RADAR_CELL_WIDTH,
  RADAR_CELL_WIDTH_COMPACT,
  RADAR_HEADER_MAX_LEN,
  ensureRadarLayout,
  normalizeColumnHeaders,
  type RadarLayoutState,
} from "../radarLayout";
import type { ChartSpec } from "../types";

type Props = {
  charts: ChartSpec[];
  layout: RadarLayoutState;
  onMove: (chartId: string, toSlot: number) => void;
  onColumnHeaderChange?: (col: number, text: string) => void;
  renderChart: (chart: ChartSpec) => ReactNode;
  editable?: boolean;
  compact?: boolean;
  className?: string;
};

const HEADER_PERSIST_MS = 400;

export function RadarLayoutGrid({
  charts,
  layout,
  onMove,
  onColumnHeaderChange,
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

  // Draft headers so typing does not re-render / remount radar charts each key.
  const [draftHeaders, setDraftHeaders] = useState(() =>
    normalizeColumnHeaders(ensured.columnHeaders, ensured.cols),
  );
  const focusedColRef = useRef<number | null>(null);
  const persistTimerRef = useRef<number | null>(null);
  const draftHeadersRef = useRef(draftHeaders);
  draftHeadersRef.current = draftHeaders;
  const onColumnHeaderChangeRef = useRef(onColumnHeaderChange);
  onColumnHeaderChangeRef.current = onColumnHeaderChange;

  const headersKey = ensured.columnHeaders.join("\u0001");
  useEffect(() => {
    if (focusedColRef.current != null) return;
    setDraftHeaders(normalizeColumnHeaders(ensured.columnHeaders, ensured.cols));
  }, [ensured.cols, headersKey, ensured.columnHeaders]);

  useEffect(() => {
    return () => {
      if (persistTimerRef.current != null) {
        window.clearTimeout(persistTimerRef.current);
      }
    };
  }, []);

  function flushHeader(col: number, text: string) {
    onColumnHeaderChangeRef.current?.(col, text);
  }

  function scheduleHeaderPersist(col: number, text: string) {
    if (persistTimerRef.current != null) {
      window.clearTimeout(persistTimerRef.current);
    }
    persistTimerRef.current = window.setTimeout(() => {
      persistTimerRef.current = null;
      flushHeader(col, text);
    }, HEADER_PERSIST_MS);
  }

  const cellW = compact ? RADAR_CELL_WIDTH_COMPACT : RADAR_CELL_WIDTH;
  const cellH = compact ? RADAR_CELL_HEIGHT_COMPACT : RADAR_CELL_HEIGHT;
  const capacity = ensured.cols * ensured.rows;
  const canEditHeader =
    editable && typeof onColumnHeaderChange === "function";

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
      className={`radar-layout-board${compact ? " compact" : ""}${className ? ` ${className}` : ""}`}
      style={{
        gridTemplateColumns: `repeat(${ensured.cols}, ${cellW}px)`,
        gridTemplateRows: `auto repeat(${ensured.rows}, ${cellH}px)`,
      }}
    >
      {Array.from({ length: ensured.cols }, (_, col) => (
        <div key={`header-${col}`} className="radar-layout-header-cell">
          {canEditHeader ? (
            <input
              className="radar-layout-header-input"
              type="text"
              value={draftHeaders[col] ?? ""}
              maxLength={RADAR_HEADER_MAX_LEN}
              placeholder={`チーム名 ${col + 1}`}
              aria-label={`列 ${col + 1} のチーム名`}
              onFocus={() => {
                focusedColRef.current = col;
              }}
              onChange={(e) => {
                const text = e.target.value;
                setDraftHeaders((prev) => {
                  const next = normalizeColumnHeaders(prev, ensured.cols);
                  next[col] = text;
                  return next;
                });
                scheduleHeaderPersist(col, text);
              }}
              onBlur={() => {
                focusedColRef.current = null;
                if (persistTimerRef.current != null) {
                  window.clearTimeout(persistTimerRef.current);
                  persistTimerRef.current = null;
                }
                flushHeader(col, draftHeadersRef.current[col] ?? "");
              }}
            />
          ) : (
            <div className="radar-layout-header-text">
              {draftHeaders[col] || ensured.columnHeaders[col] || "\u00a0"}
            </div>
          )}
        </div>
      ))}
      {cells}
    </div>
  );
}

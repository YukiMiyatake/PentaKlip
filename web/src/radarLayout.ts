/** Persistable fixed-size radar grid (gaps allowed). */

export const RADAR_LAYOUT_STORAGE_KEY = "pentaklip.radarLayout";

export const RADAR_LAYOUT_MIN_COLS = 1;
export const RADAR_LAYOUT_MAX_COLS = 8;
export const RADAR_LAYOUT_MIN_ROWS = 1;
export const RADAR_LAYOUT_MAX_ROWS = 12;
export const RADAR_LAYOUT_DEFAULT_COLS = 3;
export const RADAR_LAYOUT_DEFAULT_ROWS = 3;

/** Fixed cell size (px) shared by Stats / OBS. */
export const RADAR_CELL_WIDTH = 340;
export const RADAR_CELL_HEIGHT = 400;
export const RADAR_CELL_WIDTH_COMPACT = 320;
export const RADAR_CELL_HEIGHT_COMPACT = 380;
export const RADAR_HEADER_MAX_LEN = 80;

export type RadarLayoutState = {
  cols: number;
  rows: number;
  /** Per-column one-line team names (top header row). */
  columnHeaders: string[];
  /**
   * chart_id → linear slot index (row-major: row * cols + col).
   * Missing ids are auto-placed; empty slots = gaps.
   */
  positions: Record<string, number>;
};

export function defaultRadarLayout(): RadarLayoutState {
  return {
    cols: RADAR_LAYOUT_DEFAULT_COLS,
    rows: RADAR_LAYOUT_DEFAULT_ROWS,
    columnHeaders: Array(RADAR_LAYOUT_DEFAULT_COLS).fill(""),
    positions: {},
  };
}

export function normalizeRadarHeaderText(value: unknown): string {
  if (typeof value !== "string") return "";
  const oneLine = value.replace(/[\r\n]+/g, " ").trimStart();
  return oneLine.slice(0, RADAR_HEADER_MAX_LEN);
}

/** Resize / pad column header list to match `cols`. */
export function normalizeColumnHeaders(
  headers: unknown,
  cols: number,
  legacyHeaderText?: unknown,
): string[] {
  const out = Array.from({ length: cols }, () => "");
  if (Array.isArray(headers)) {
    for (let i = 0; i < cols; i += 1) {
      out[i] = normalizeRadarHeaderText(headers[i]);
    }
    return out;
  }
  // Migrate older single headerText into column 0.
  const legacy = normalizeRadarHeaderText(legacyHeaderText);
  if (legacy) out[0] = legacy;
  return out;
}

function clampInt(n: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, Math.round(n)));
}

export function normalizeRadarLayout(raw: unknown): RadarLayoutState {
  const base = defaultRadarLayout();
  if (!raw || typeof raw !== "object") return base;
  const obj = raw as Partial<RadarLayoutState>;
  const cols = clampInt(
    Number(obj.cols),
    RADAR_LAYOUT_MIN_COLS,
    RADAR_LAYOUT_MAX_COLS,
    base.cols,
  );
  const rows = clampInt(
    Number(obj.rows),
    RADAR_LAYOUT_MIN_ROWS,
    RADAR_LAYOUT_MAX_ROWS,
    base.rows,
  );
  const positions: Record<string, number> = {};
  const capacity = cols * rows;
  if (obj.positions && typeof obj.positions === "object") {
    for (const [id, slot] of Object.entries(obj.positions)) {
      const s = Number(slot);
      if (!id || !Number.isFinite(s)) continue;
      const idx = Math.round(s);
      if (idx < 0 || idx >= capacity) continue;
      positions[id] = idx;
    }
  }
  return {
    cols,
    rows,
    columnHeaders: normalizeColumnHeaders(
      (obj as { columnHeaders?: unknown }).columnHeaders,
      cols,
      (obj as { headerText?: unknown }).headerText,
    ),
    positions,
  };
}

export function loadRadarLayout(): RadarLayoutState {
  try {
    const raw = localStorage.getItem(RADAR_LAYOUT_STORAGE_KEY);
    if (!raw) return defaultRadarLayout();
    return normalizeRadarLayout(JSON.parse(raw));
  } catch {
    return defaultRadarLayout();
  }
}

export function saveRadarLayout(layout: RadarLayoutState): void {
  try {
    localStorage.setItem(
      RADAR_LAYOUT_STORAGE_KEY,
      JSON.stringify(normalizeRadarLayout(layout)),
    );
  } catch {
    /* ignore */
  }
}

function occupiedSlots(
  positions: Record<string, number>,
  exceptId?: string,
): Set<number> {
  const used = new Set<number>();
  for (const [id, slot] of Object.entries(positions)) {
    if (exceptId && id === exceptId) continue;
    used.add(slot);
  }
  return used;
}

/** Place any chart missing a valid slot into the first free cell; grow rows if needed. */
export function ensureRadarLayout(
  layout: RadarLayoutState,
  chartIds: string[],
): RadarLayoutState {
  const cols = clampInt(
    layout.cols,
    RADAR_LAYOUT_MIN_COLS,
    RADAR_LAYOUT_MAX_COLS,
    RADAR_LAYOUT_DEFAULT_COLS,
  );
  let rows = clampInt(
    layout.rows,
    RADAR_LAYOUT_MIN_ROWS,
    RADAR_LAYOUT_MAX_ROWS,
    RADAR_LAYOUT_DEFAULT_ROWS,
  );
  const idSet = new Set(chartIds);
  const positions: Record<string, number> = {};

  // Keep saved positions that still exist and fit.
  for (const [id, slot] of Object.entries(layout.positions)) {
    if (!idSet.has(id)) continue;
    if (slot < 0) continue;
    positions[id] = slot;
  }

  const placeOne = (id: string) => {
    if (positions[id] != null && positions[id]! < cols * rows) {
      const used = occupiedSlots(positions, id);
      if (!used.has(positions[id]!)) return;
    }
    let used = occupiedSlots(positions, id);
    let slot = 0;
    const capacity = () => cols * rows;
    while (slot < capacity() && used.has(slot)) slot += 1;
    while (slot >= capacity()) {
      if (rows >= RADAR_LAYOUT_MAX_ROWS) {
        // Over capacity: stack onto last cell (rare).
        positions[id] = Math.max(0, capacity() - 1);
        return;
      }
      rows += 1;
      used = occupiedSlots(positions, id);
    }
    positions[id] = slot;
  };

  // Resolve collisions (two charts saved to same slot).
  const bySlot = new Map<number, string>();
  const collided: string[] = [];
  for (const id of chartIds) {
    const slot = positions[id];
    if (slot == null || slot < 0 || slot >= cols * rows) {
      collided.push(id);
      delete positions[id];
      continue;
    }
    const prev = bySlot.get(slot);
    if (prev != null) {
      collided.push(id);
      delete positions[id];
    } else {
      bySlot.set(slot, id);
    }
  }
  for (const id of collided) placeOne(id);
  for (const id of chartIds) {
    if (positions[id] == null) placeOne(id);
  }

  return {
    cols,
    rows,
    columnHeaders: normalizeColumnHeaders(layout.columnHeaders, cols),
    positions,
  };
}

export function resizeRadarLayout(
  layout: RadarLayoutState,
  cols: number,
  rows: number,
  chartIds: string[],
): RadarLayoutState {
  const next = normalizeRadarLayout({
    ...layout,
    cols,
    rows,
  });
  // Drop out-of-range slots then re-place.
  const positions: Record<string, number> = {};
  const capacity = next.cols * next.rows;
  for (const [id, slot] of Object.entries(next.positions)) {
    if (slot >= 0 && slot < capacity) positions[id] = slot;
  }
  return ensureRadarLayout({ ...next, positions }, chartIds);
}

/** Move chart to target slot; swap if occupied. */
export function moveRadarChart(
  layout: RadarLayoutState,
  chartId: string,
  toSlot: number,
  chartIds: string[],
): RadarLayoutState {
  const ensured = ensureRadarLayout(layout, chartIds);
  const capacity = ensured.cols * ensured.rows;
  if (toSlot < 0 || toSlot >= capacity) return ensured;
  const fromSlot = ensured.positions[chartId];
  if (fromSlot == null || fromSlot === toSlot) return ensured;

  const positions = { ...ensured.positions };
  const occupant = Object.entries(positions).find(
    ([id, slot]) => id !== chartId && slot === toSlot,
  );
  if (occupant) {
    positions[occupant[0]] = fromSlot;
  }
  positions[chartId] = toSlot;
  return { ...ensured, positions };
}

export function resetRadarLayout(
  chartIds: string[],
  columnHeaders: string[] = [],
): RadarLayoutState {
  const base = defaultRadarLayout();
  return ensureRadarLayout(
    {
      ...base,
      columnHeaders: normalizeColumnHeaders(columnHeaders, base.cols),
    },
    chartIds,
  );
}

export function setRadarColumnHeader(
  layout: RadarLayoutState,
  col: number,
  text: string,
): RadarLayoutState {
  const cols = layout.cols;
  if (col < 0 || col >= cols) return layout;
  const columnHeaders = normalizeColumnHeaders(layout.columnHeaders, cols);
  columnHeaders[col] = normalizeRadarHeaderText(text);
  return { ...layout, columnHeaders };
}

export function slotToCell(
  slot: number,
  cols: number,
): { col: number; row: number } {
  return { col: slot % cols, row: Math.floor(slot / cols) };
}

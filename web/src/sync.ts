/** Cross-tab / same-window sync for Stats ↔ 表示設定 ↔ OBS. */

const CHANNEL = "pentaklip-sync";

export const DISPLAY_SETTINGS_CHANGED = "pentaklip:display-settings-changed";
export const VIEW_FILTERS_CHANGED = "pentaklip:view-filters-changed";
export const OUTPUT_ROOT_CHANGED = "pentaklip:output-root-changed";

type SyncPayload =
  | { type: typeof DISPLAY_SETTINGS_CHANGED }
  | { type: typeof VIEW_FILTERS_CHANGED }
  | { type: typeof OUTPUT_ROOT_CHANGED };

function post(payload: SyncPayload) {
  try {
    const bc = new BroadcastChannel(CHANNEL);
    bc.postMessage(payload);
    bc.close();
  } catch {
    /* BroadcastChannel unavailable */
  }
}

export function notifyDisplaySettingsChanged() {
  window.dispatchEvent(new Event(DISPLAY_SETTINGS_CHANGED));
  post({ type: DISPLAY_SETTINGS_CHANGED });
}

export function notifyViewFiltersChanged() {
  window.dispatchEvent(new Event(VIEW_FILTERS_CHANGED));
  post({ type: VIEW_FILTERS_CHANGED });
}

export function notifyOutputRootChanged() {
  window.dispatchEvent(new Event(OUTPUT_ROOT_CHANGED));
  post({ type: OUTPUT_ROOT_CHANGED });
}

function subscribe(
  eventName: string,
  messageType: SyncPayload["type"],
  cb: () => void,
): () => void {
  const onLocal = () => cb();
  window.addEventListener(eventName, onLocal);
  let bc: BroadcastChannel | null = null;
  try {
    bc = new BroadcastChannel(CHANNEL);
    bc.onmessage = (ev: MessageEvent<SyncPayload>) => {
      if (ev.data?.type === messageType) cb();
    };
  } catch {
    /* optional */
  }
  return () => {
    window.removeEventListener(eventName, onLocal);
    bc?.close();
  };
}

export function subscribeDisplaySettingsChanged(cb: () => void): () => void {
  return subscribe(DISPLAY_SETTINGS_CHANGED, DISPLAY_SETTINGS_CHANGED, cb);
}

export function subscribeViewFiltersChanged(cb: () => void): () => void {
  return subscribe(VIEW_FILTERS_CHANGED, VIEW_FILTERS_CHANGED, cb);
}

export function subscribeOutputRootChanged(cb: () => void): () => void {
  return subscribe(OUTPUT_ROOT_CHANGED, OUTPUT_ROOT_CHANGED, cb);
}

/** Persist Stats 「デバッグ」 so OBS re-aggregates with the same flag. */

export const DEBUG_BOOST_STORAGE_KEY = "pentaklip.debugBoost";

export function loadDebugBoost(): boolean {
  try {
    return localStorage.getItem(DEBUG_BOOST_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function saveDebugBoost(enabled: boolean): void {
  try {
    if (enabled) localStorage.setItem(DEBUG_BOOST_STORAGE_KEY, "1");
    else localStorage.removeItem(DEBUG_BOOST_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

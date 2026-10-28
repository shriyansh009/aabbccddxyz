async function get(path, params = {}) {
  const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== ""));
  const qs = new URLSearchParams(clean).toString();
  const res = await fetch(`/api${path}${qs ? `?${qs}` : ""}`);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const getMeta = () => get("/meta");
export const getForecast = (deliveryDay, cutoffHour) =>
  get("/forecast", { delivery_day: deliveryDay, cutoff_hour: cutoffHour });
export const getAccuracy = (start, end, cutoffHour) =>
  get("/accuracy", { start, end, cutoff_hour: cutoffHour });
export const getProcurement = (params) => get("/procurement", params);

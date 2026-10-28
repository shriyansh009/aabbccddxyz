export const mw = (v) => (v == null ? "–" : `${Math.round(v).toLocaleString("en-GB")} MW`);
export const mwh = (v) => (v == null ? "–" : `${Math.round(v).toLocaleString("en-GB")} MWh`);
export const pct = (v) => (v == null ? "–" : `${v.toFixed(1)}%`);

const LONDON = "Europe/London";
export const hhmm = (iso) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: LONDON });
export const dayTime = (iso) =>
  new Date(iso).toLocaleString("en-GB", {
    weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: LONDON,
  });
export const shortDay = (d) =>
  new Date(`${d}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

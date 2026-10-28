import React, { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getAccuracy } from "../api.js";
import { mw, pct, shortDay } from "../format.js";
import Kpi from "./Kpi.jsx";

const tip = (v) => (v == null ? "–" : `${Math.round(v).toLocaleString("en-GB")} MW`);

export default function AccuracyView({ meta, cutoff }) {
  const [start, setStart] = useState(meta.delivery_start);
  const [end, setEnd] = useState(meta.delivery_end);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (end < start) return;
    let live = true;
    setLoading(true);
    setError(null);
    getAccuracy(start, end, cutoff)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [start, end, cutoff]);

  const o = data?.overall;
  const daily = (data?.daily || []).filter((d) => d.n > 0).map((d) => ({ ...d, label: shortDay(d.day) }));
  const hourly = (data?.by_hour_of_day || []).map((h) => ({ ...h, label: `${String(h.hour).padStart(2, "0")}h` }));
  const horizon = (data?.horizon || []).filter((h) => h.n > 0);
  const hist = (data?.histogram || []).map((b) => ({ ...b, label: `${b.bin_start}` }));

  return (
    <section>
      <div className="controls">
        <label>From <input type="date" value={start} min={meta.delivery_start} max={end} onChange={(e) => e.target.value && setStart(e.target.value)} /></label>
        <label>To <input type="date" value={end} min={start} max={meta.delivery_end} onChange={(e) => e.target.value && setEnd(e.target.value)} /></label>
        {loading && <span className="muted">Calculating…</span>}
      </div>
      {error && <div className="banner error">{error}</div>}

      {data && o?.n > 0 && (
        <>
          <p className="callout">
            Accuracy of the forecast <b>actually available at the {String(cutoff).padStart(2, "0")}:00 cut-off on D-1</b>,
            over {o.n.toLocaleString("en-GB")} half-hours of delivery between {data.start} and {data.end}.
          </p>

          <div className="kpis">
            <Kpi label="Mean absolute error" value={mw(o.mae_mw)} hint={`${pct(o.nmae_pct)} of mean wind output`} />
            <Kpi label="RMSE" value={mw(o.rmse_mw)} hint="penalises large misses" />
            <Kpi label="Bias" value={`${o.bias_mw > 0 ? "+" : ""}${mw(o.bias_mw)}`} hint={o.bias_mw > 0 ? "forecast tends to be too high" : "forecast tends to be too low"} />
            <Kpi label="95% of the time, wind is over-forecast by no more than" value={mw(o.p95_over_forecast_mw)} hint="size a buffer for the risk of under-buying" />
            <Kpi label="95% of the time, wind is under-forecast by no more than" value={mw(o.p95_under_forecast_mw)} hint="risk of over-buying" />
            <Kpi label="Largest miss" value={mw(o.max_abs_error_mw)} />
          </div>

          <div className="grid2">
            <div className="card">
              <h3>Error by lead time</h3>
              <p className="muted">Mean and 90th-percentile absolute error vs. how far ahead the forecast was issued.</p>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={horizon} margin={{ top: 8, right: 16, left: 8, bottom: 16 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="horizon_hours" label={{ value: "hours before delivery", position: "insideBottom", offset: -8 }} />
                  <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(1)}k`} />
                  <Tooltip formatter={tip} labelFormatter={(h) => `${h}h ahead`} />
                  <Legend verticalAlign="top" />
                  <Line dataKey="mae_mw" name="MAE" stroke="#2563eb" strokeWidth={2} />
                  <Line dataKey="p90_abs_error_mw" name="P90 abs error" stroke="#f59e0b" strokeWidth={2} strokeDasharray="5 4" />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="card">
              <h3>Error by day</h3>
              <p className="muted">MAE of the day-ahead forecast for each delivery day.</p>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={daily} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" interval={Math.ceil(daily.length / 10) - 1} />
                  <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(1)}k`} />
                  <Tooltip formatter={tip} />
                  <Bar dataKey="mae_mw" name="MAE" fill="#2563eb" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="card">
              <h3>Error by time of day</h3>
              <p className="muted">Bias (forecast − actual) per UK hour, positive means over-forecast.</p>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={hourly} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" interval={2} />
                  <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(1)}k`} />
                  <Tooltip formatter={tip} />
                  <ReferenceLine y={0} stroke="#64748b" />
                  <Legend verticalAlign="top" />
                  <Bar dataKey="mae_mw" name="MAE" fill="#2563eb" />
                  <Bar dataKey="bias_mw" name="Bias" fill="#f59e0b" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="card">
              <h3>Distribution of errors</h3>
              <p className="muted">Number of half-hours by error size (MW, 500 MW bins; negative = under-forecast).</p>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={hist} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" interval={Math.ceil(hist.length / 10) - 1} />
                  <YAxis />
                  <Tooltip labelFormatter={(l) => `${l} to ${Number(l) + 500} MW`} />
                  <ReferenceLine x="0" stroke="#64748b" />
                  <Bar dataKey="count" name="Half-hours" fill="#16a34a" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
      {data && o?.n === 0 && <div className="banner">No overlapping forecast and actual data in this range.</div>}
    </section>
  );
}

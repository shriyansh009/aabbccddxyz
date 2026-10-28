import React, { useEffect, useState } from "react";
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getForecast } from "../api.js";
import { dayTime, hhmm, mw, mwh } from "../format.js";
import Kpi from "./Kpi.jsx";

export default function ForecastView({ meta, cutoff }) {
  const [day, setDay] = useState(meta.delivery_start);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    getForecast(day, cutoff)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [day, cutoff]);

  const shift = (n) => {
    const d = new Date(`${day}T12:00:00Z`);
    d.setUTCDate(d.getUTCDate() + n);
    const next = d.toISOString().slice(0, 10);
    if (next >= meta.delivery_start && next <= meta.delivery_end) setDay(next);
  };

  const rows = (data?.rows || []).map((r) => ({ ...r, label: hhmm(r.time) }));
  const s = data?.summary;

  return (
    <section>
      <div className="controls">
        <button onClick={() => shift(-1)} aria-label="Previous day">←</button>
        <label>
          Delivery day
          <input type="date" value={day} min={meta.delivery_start} max={meta.delivery_end}
                 onChange={(e) => e.target.value && setDay(e.target.value)} />
        </label>
        <button onClick={() => shift(1)} aria-label="Next day">→</button>
        {loading && <span className="muted">Loading…</span>}
      </div>

      {error && <div className="banner error">{error}</div>}

      {data && (
        <>
          <p className="callout">
            Decision for <b>{day}</b> is made on <b>{dayTime(data.decision_cutoff)}</b>. The chart shows the
            latest forecast published before that moment
            {data.forecast_published_range[1] && <> (most recent issue: <b>{dayTime(data.forecast_published_range[1])}</b>)</>}.
          </p>

          <div className="kpis">
            <Kpi label="Average forecast wind" value={mw(s.avg_forecast_mw)} />
            <Kpi label="Lowest half-hour" value={mw(s.min_forecast_mw)} hint="when thermal must fill the most" />
            <Kpi label="Highest half-hour" value={mw(s.max_forecast_mw)} />
            <Kpi label="Forecast energy" value={mwh(s.total_forecast_mwh)} hint={`${s.periods_with_forecast}/${s.periods} periods`} />
          </div>

          <div className="card">
            <h3>Forecast vs actual wind generation</h3>
            <ResponsiveContainer width="100%" height={360}>
              <LineChart data={rows} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" interval={5} />
                <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} label={{ value: "MW", angle: -90, position: "insideLeft" }} />
                <Tooltip formatter={(v) => (v == null ? "–" : `${Math.round(v).toLocaleString("en-GB")} MW`)} />
                <Legend />
                <Line type="monotone" dataKey="forecast_mw" name="Forecast (latest at cut-off)" stroke="#2563eb" strokeWidth={2} dot={false} connectNulls />
                <Line type="monotone" dataKey="actual_mw" name="Actual" stroke="#16a34a" strokeWidth={2} dot={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
            <p className="muted">Times are UK local. Actuals appear once Elexon has published them for that period.</p>
          </div>

          <div className="card">
            <h3>Half-hourly detail</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Time</th><th>Forecast</th><th>Actual</th><th>Error</th><th>Forecast issued</th></tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.time}>
                      <td>{r.label}</td>
                      <td>{mw(r.forecast_mw)}</td>
                      <td>{mw(r.actual_mw)}</td>
                      <td className={r.error_mw > 0 ? "over" : r.error_mw < 0 ? "under" : ""}>
                        {r.error_mw == null ? "–" : `${r.error_mw > 0 ? "+" : ""}${Math.round(r.error_mw).toLocaleString("en-GB")} MW`}
                      </td>
                      <td>{r.published_at ? dayTime(r.published_at) : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

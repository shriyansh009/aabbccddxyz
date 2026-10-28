import React, { useEffect, useState } from "react";
import {
  Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getProcurement } from "../api.js";
import { dayTime, hhmm, mw, mwh } from "../format.js";
import Kpi from "./Kpi.jsx";

const CONF = [0.9, 0.95, 0.99];

export default function ProcurementView({ meta, cutoff }) {
  const [day, setDay] = useState(meta.delivery_end);
  const [mode, setMode] = useState("flat");
  const [flat, setFlat] = useState("");
  const [profile, setProfile] = useState("");
  const [confidence, setConfidence] = useState(0.95);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const demandParams = mode === "flat" ? { demand_mw: flat } : { demand_profile: profile.replace(/\s+/g, "") };
  const ready = mode === "flat" ? flat !== "" && Number(flat) >= 0 : profile.trim() !== "";

  useEffect(() => {
    if (!ready) { setData(null); setError(null); return; }
    let live = true;
    const t = setTimeout(() => {
      setLoading(true);
      setError(null);
      getProcurement({ delivery_day: day, cutoff_hour: cutoff, confidence, ...demandParams })
        .then((d) => live && setData(d))
        .catch((e) => { if (live) { setData(null); setError(e.message); } })
        .finally(() => live && setLoading(false));
    }, 350); // debounce typing
    return () => { live = false; clearTimeout(t); };
  }, [day, cutoff, confidence, mode, flat, profile]); // eslint-disable-line react-hooks/exhaustive-deps

  const rows = (data?.rows || []).map((r) => ({ ...r, label: hhmm(r.time) }));
  const t = data?.totals_mwh;
  const bt = data?.backtest;

  return (
    <section>
      <div className="card">
        <h3>How much should we buy for the delivery day?</h3>
        <p className="muted">
          Buy = expected demand − forecast wind (what thermal / the market must cover) + a safety buffer for the
          risk that wind under-delivers. Demand is not in the Elexon wind data, so enter your own estimate.
        </p>
        <div className="controls">
          <label>
            Delivery day
            <input type="date" value={day} min={meta.delivery_start} max={meta.delivery_end}
                   onChange={(e) => e.target.value && setDay(e.target.value)} />
          </label>
          <label>
            Demand input
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="flat">Flat average (MW)</option>
              <option value="profile">Half-hourly profile</option>
            </select>
          </label>
          {mode === "flat" ? (
            <label>
              Expected demand (MW)
              <input type="number" min="0" step="100" placeholder="e.g. 25000" value={flat}
                     onChange={(e) => setFlat(e.target.value)} />
            </label>
          ) : (
            <label className="wide">
              48 comma-separated MW values (00:00–24:00 UK time)
              <textarea rows={2} value={profile} onChange={(e) => setProfile(e.target.value)}
                        placeholder="22000, 21500, 21000, …" />
            </label>
          )}
          <label>
            Wind-miss risk covered
            <select value={confidence} onChange={(e) => setConfidence(Number(e.target.value))}>
              {CONF.map((c) => <option key={c} value={c}>{Math.round(c * 100)}% of the time</option>)}
            </select>
          </label>
          {loading && <span className="muted">Calculating…</span>}
        </div>
      </div>

      {!ready && <div className="banner">Enter your expected demand to see how much to buy.</div>}
      {error && <div className="banner error">{error}</div>}

      {data && (
        <>
          <p className="callout">
            Plan for <b>{day}</b>, decided on <b>{dayTime(data.decision_cutoff)}</b> using the latest wind forecast issued
            before then{data.forecast_published_range[1] && <> ({dayTime(data.forecast_published_range[1])})</>}.
            The buffer is the {Math.round(data.confidence * 100)}th-percentile wind over-forecast,{" "}
            <b>{mw(data.buffer.over_mw)}</b>, learned from {data.buffer.n.toLocaleString("en-GB")} earlier half-hours.
            {data.buffer.in_sample && (
              <> <b>Note:</b> too little earlier history for this day, so the buffer uses the whole month (in-sample).</>
            )}
          </p>

          <div className="kpis">
            <Kpi label="Recommended purchase" value={mwh(t.recommended_buy)} hint="energy to buy day-ahead" />
            <Kpi label="Base need (no safety margin)" value={mwh(t.base_buy)} hint="demand − forecast wind" />
            <Kpi label="Risk buffer" value={mwh(t.buffer)} hint={`${mw(data.buffer.over_mw)} per half-hour`} />
            <Kpi label="Peak purchase" value={mw(data.peak_recommended_buy_mw)} hint="largest half-hour block" />
            <Kpi label="Demand covered by wind" value={mwh(t.wind_covered)}
                 hint={`${t.demand ? Math.round((100 * t.wind_covered) / t.demand) : 0}% of demand`} />
          </div>
          {data.periods_missing_forecast > 0 && (
            <div className="banner">{data.periods_missing_forecast} half-hours have no forecast published before the cut-off and are excluded.</div>
          )}

          <div className="card">
            <h3>Half-hourly purchase profile</h3>
            <ResponsiveContainer width="100%" height={360}>
              <ComposedChart data={rows} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" interval={5} />
                <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} label={{ value: "MW", angle: -90, position: "insideLeft" }} />
                <Tooltip formatter={(v) => (v == null ? "–" : `${Math.round(v).toLocaleString("en-GB")} MW`)} />
                <Legend />
                <Bar dataKey="base_buy_mw" stackId="buy" name="Base buy" fill="#2563eb" />
                <Bar dataKey="buffer_mw" stackId="buy" name="Risk buffer" fill="#f59e0b" />
                <Line dataKey="demand_mw" name="Demand" stroke="#0f172a" strokeWidth={2} dot={false} />
                <Line dataKey="forecast_mw" name="Forecast wind" stroke="#16a34a" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {bt?.available && (
            <div className="card">
              <h3>What actually happened (back-test)</h3>
              <p className="muted">
                Actual wind is known for this day, so we can check the plan. Actual need was{" "}
                <b>{mwh(bt.actual_need_mwh)}</b>. Shortfall = under-bought (must be covered later, usually at worse prices);
                surplus = over-bought.
              </p>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Plan</th><th>Shortfall</th><th>Surplus</th></tr></thead>
                  <tbody>
                    <tr><td>Base need only</td><td className="over">{mwh(bt.base.shortfall_mwh)}</td><td>{mwh(bt.base.surplus_mwh)}</td></tr>
                    <tr><td>Recommended (with buffer)</td><td className="over">{mwh(bt.recommended.shortfall_mwh)}</td><td>{mwh(bt.recommended.surplus_mwh)}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="card">
            <h3>Half-hourly detail</h3>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Time</th><th>Demand</th><th>Forecast wind</th><th>Base buy</th><th>Buffer</th><th>Buy</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.time}>
                      <td>{r.label}</td><td>{mw(r.demand_mw)}</td><td>{mw(r.forecast_mw)}</td>
                      <td>{mw(r.base_buy_mw)}</td><td>{mw(r.buffer_mw)}</td><td><b>{mw(r.recommended_buy_mw)}</b></td>
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

import React, { useEffect, useState } from "react";
import { getMeta } from "./api.js";
import ForecastView from "./components/ForecastView.jsx";
import AccuracyView from "./components/AccuracyView.jsx";
import ProcurementView from "./components/ProcurementView.jsx";

const TABS = [
  { id: "buy", label: "Buy for tomorrow" },
  { id: "forecast", label: "Day-ahead forecast" },
  { id: "accuracy", label: "Forecast accuracy" },
];

export default function App() {
  const [tab, setTab] = useState("buy");
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState(null);
  const [cutoff, setCutoff] = useState(9);

  useEffect(() => {
    getMeta()
      .then((m) => {
        setMeta(m);
        setCutoff(m.default_cutoff_hour);
      })
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>GB Wind Forecast Portal</h1>
          <p className="sub">
            National wind generation · Elexon BMRS (FUELHH actuals, WINDFOR forecasts) · decisions made January 2026
          </p>
        </div>
        <label className="cutoff">
          Decision cut-off (D-1, UK time)
          <select value={cutoff} onChange={(e) => setCutoff(Number(e.target.value))}>
            {[6, 7, 8, 9, 10, 11, 12].map((h) => (
              <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>
            ))}
          </select>
        </label>
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? "tab active" : "tab"} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      {error && <div className="banner error">Could not reach the API: {error}</div>}
      {!meta && !error && <div className="banner">Loading data from Elexon… the first request can take a minute.</div>}

      {meta && tab === "buy" && <ProcurementView meta={meta} cutoff={cutoff} />}
      {meta && tab === "forecast" && <ForecastView meta={meta} cutoff={cutoff} />}
      {meta && tab === "accuracy" && <AccuracyView meta={meta} cutoff={cutoff} />}

      <footer className="footer">
        Contains BMRS data © Elexon Limited. Forecast error = forecast − actual (positive = wind over-forecast, i.e. risk
        of buying too little day-ahead).
      </footer>
    </div>
  );
}

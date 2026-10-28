# GB Wind Forecast Portal

A web application that helps a UK energy utility's day-ahead power buying team understand **how much wind
generation to expect** and **how far they can trust that forecast**, using real data from the Elexon BMRS
(Insights) API.

| | |
|---|---|
| **Live app** | `<add your Heroku / Render URL here after deploying>` |
| **Demo video** | `<add unlisted YouTube link here>` |
| **Stack** | React (Vite, Recharts) · Python (FastAPI) · Docker |
| **Data** | Elexon BMRS `FUELHH` (actuals) and `WINDFOR` (forecasts), national GB wind only |

---

## AI tool disclosure

As required by the challenge brief, this project was built with the assistance of an AI tool:

- **Tool:** Claude (model **Claude Sonnet 5.5**, by Anthropic), used through the Claude app in agentic mode
  (file, shell and web-search tools).
- **What it was used for:** reading the challenge document, researching the Elexon API, designing the
  architecture, and writing the backend, frontend, unit tests, Dockerfile, deployment configs and this README.
- **Human responsibility:** the author is responsible for reviewing, running and deploying the code and for the
  analysis decisions described below. Prompting history and generated code were reviewed before submission.

---

## 1. Problem and approach

The client buys electricity on the **UK day-ahead market**. Decisions for delivery day *D* must be made on
*D-1*, so the amount of power to procure from thermal plants depends on a **wind generation forecast**, and the
quality of that forecast.

The portal answers two questions:

1. **What is the latest wind forecast available when the decision has to be made?**
2. **How accurate has that forecast been, quantitatively?**

The central design decision is to avoid hindsight bias. For every half-hour of delivery day *D* the app uses
**the latest forecast whose `publishTime` is at or before the decision cut-off on D-1** (default 09:00 UK
time, adjustable in the UI). Accuracy is then measured on exactly those forecasts, i.e. what the buyer
genuinely had in hand, rather than on the most recent forecast ever published for that half-hour.

### Scope (from the brief)

- National-level **wind** only, from Elexon only.
- Actuals: `FUELHH` filtered to `fuelType = WIND` (`startTime`, `generation`).
- Forecasts: `WINDFOR` (`startTime`, `publishTime`, `generation`).
- Purchase decisions made in **January 2026** → delivery days **2 January – 1 February 2026**.

---

## 2. Features

### Day-ahead forecast tab
- Pick a delivery day (with previous/next navigation) and a decision cut-off.
- Shows the exact cut-off timestamp and when the forecast used was issued.
- KPIs: average, minimum and maximum forecast wind, total forecast energy (MWh).
- Chart of forecast vs actual wind (actuals appear once Elexon has published them).
- Half-hourly table: forecast, actual, error and the forecast issue time.

### Forecast accuracy tab
- Date-range selector over the January 2026 decision window.
- KPIs: mean absolute error (MAE), RMSE, bias, normalised MAE, 95th-percentile over- and under-forecast,
  largest miss.
- Charts: **error by lead time** (1–48 h before delivery), **error by day**, **error by time of day**,
  **error distribution**.

---

## 3. Architecture

```
                         ┌────────────────────────────────────────────┐
                         │                Docker container            │
┌──────────────┐  HTTPS  │  ┌──────────────┐      ┌────────────────┐  │      ┌────────────────────┐
│   Browser    │◄───────►│  │   FastAPI    │─────►│ analysis.py    │  │      │  Elexon Insights   │
│ React (SPA)  │  /api/* │  │   main.py    │      │ (pure logic)   │  │      │  API (BMRS)        │
└──────────────┘         │  └──────┬───────┘      └────────────────┘  │      │  FUELHH / WINDFOR  │
                         │         │ first request / refresh          │      └─────────▲──────────┘
                         │  ┌──────▼───────┐   HTTPS  ┌─────────────┐ │                │
                         │  │  Store       │─────────►│ elexon.py   │─┼────────────────┘
                         │  │ memory + JSON│◄─────────│ client      │ │
                         │  │ disk cache   │          └─────────────┘ │
                         │  └──────────────┘                          │
                         │   static/  ← built React app served by API │
                         └────────────────────────────────────────────┘
```

**Request flow**

1. The browser loads the React app, served by FastAPI as static files (single container, single origin).
2. The app calls `/api/meta`. On the first call the backend downloads January 2026 actuals and forecasts
   from Elexon, writes them to a JSON cache and builds an in-memory index.
3. Later calls (`/api/forecast`, `/api/accuracy`) are computed from memory in milliseconds.

**Why this design**

- **Pure analysis module.** `analysis.py` has no I/O, so the logic that matters (forecast selection and error
  metrics) is trivially unit-testable.
- **Download once, cache.** The bounded January 2026 window is small and historical, so one download plus a disk
  cache avoids hitting Elexon on every request and keeps the UI fast.
- **Single container.** The React build is copied into the Python image, which simplifies Docker and
  Heroku/Render deployment (one service, no CORS or proxy setup).

---

## 4. Methodology

### Forecast selection
For a target half-hour `t` on delivery day *D* and cut-off `c = (D-1) at cutoff_hour, Europe/London`:

```
forecast(t) = generation of the WINDFOR row with startTime = t and the latest publishTime <= c
```

Implemented with a sorted list of publish times per target and binary search (`bisect`) in
`Dataset.latest_before`. Cut-off times are converted from UK local time to UTC, so BST is handled correctly.

### Error definition
`error = forecast − actual` (MW). **Positive = wind was over-forecast**, which creates the commercially
dangerous situation of buying too little day-ahead and having to cover the shortfall later.

### Metrics

| Metric | Meaning |
|---|---|
| MAE | average size of the error |
| RMSE | like MAE but penalises large misses more |
| Bias | average signed error (systematic over/under-forecasting) |
| nMAE % | MAE as a percentage of mean actual wind output |
| P50 / P90 / P95 absolute error | typical and tail error sizes |
| P95 over-forecast | wind is over-forecast by no more than this 95 % of the time, a basis for sizing a buffer |
| P95 under-forecast | same, for the risk of over-buying |

### Lead-time analysis
For horizons *h* ∈ {1, 2, 4, 6, 8, 12, 16, 20, 24, 28, 32, 36, 42, 48} hours, the app takes, for each target
half-hour, the latest forecast published at least *h* hours before it and computes the metrics. This shows how
quickly forecast quality changes with lead time. Settlement periods are 30 minutes, so energy in MWh = MW × 0.5.

---

## 5. Repository layout

```
.
├── backend/
│   ├── app/
│   │   ├── config.py        constants: window dates, default cut-off, horizons (env-overridable)
│   │   ├── elexon.py        Elexon client: retries, chunked downloads, JSON disk cache
│   │   ├── analysis.py      forecast selection + all error metrics (pure functions/classes)
│   │   └── main.py          FastAPI app: /api/* endpoints and static React serving
│   ├── tests/
│   │   └── test_analysis.py pytest unit tests for the analysis logic
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                       layout, tabs, global cut-off selector
│   │   ├── components/ForecastView.jsx   day-ahead forecast tab
│   │   ├── components/AccuracyView.jsx   accuracy tab and charts
│   │   ├── components/Kpi.jsx            KPI tile
│   │   ├── api.js                        fetch helpers
│   │   ├── format.js                     number/date formatting (UK time)
│   │   └── styles.css
│   ├── index.html, vite.config.js, package.json
├── Dockerfile               multi-stage build: React build → Python image serving API + static files
├── docker-compose.yml       local run with a volume for the data cache
├── heroku.yml               Heroku container deployment
├── render.yaml              Render deployment (alternative)
├── .dockerignore, .gitignore
└── README.md
```

---

## 6. Getting started

### Option A: Docker (recommended)

Prerequisite: Docker.

```bash
docker compose up --build
```

Open <http://localhost:8000>. The first page load downloads the data from Elexon, which can take about a minute;
afterwards it is cached in the `wind-data` volume.

Without compose:

```bash
docker build -t wind-forecast-portal .
docker run --rm -p 8000:8000 wind-forecast-portal
```

### Option B: local development

Prerequisites: Python 3.12+, Node 20+.

```bash
# Terminal 1: backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload                         # http://localhost:8000

# Terminal 2: frontend (proxies /api to port 8000)
cd frontend
npm install
npm run dev                                           # http://localhost:5173
```

### Tests

```bash
cd backend
python -m pytest
```

The tests cover: cut-off calculation (including BST), selection of the latest forecast before the cut-off and
exclusion of later ones, missing forecasts, metric values on known inputs, and the accuracy/lead-time pipeline.

### Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `ELEXON_BASE_URL` | `https://data.elexon.co.uk/bmrs/api/v1` | Elexon API base URL |
| `DATA_DIR` | `backend/data` (`/srv/data` in Docker) | where the JSON cache is stored |
| `STATIC_DIR` | `backend/static` (`/srv/static` in Docker) | built React app to serve |
| `PORT` | `8000` | port (set automatically by Heroku/Render) |

---

## 7. API reference

Interactive docs are available at `/docs` (Swagger UI) when the server is running.

### `GET /api/health`
Liveness check → `{"status": "ok"}`

### `GET /api/meta`
Date limits, default cut-off and information about the loaded data (timestamp, number of points).

### `GET /api/forecast`

| Parameter | Description |
|---|---|
| `delivery_day` | `YYYY-MM-DD`, between 2026-01-02 and 2026-02-01 |
| `cutoff_hour` | decision cut-off on D-1, UK local hour (default 9) |

Returns the decision cut-off timestamp, the range of forecast issue times used, a summary, and 48 half-hourly
rows of `time`, `forecast_mw`, `published_at`, `actual_mw`, `error_mw`.

### `GET /api/accuracy`

| Parameter | Description |
|---|---|
| `start`, `end` | delivery-day range (defaults to the full window) |
| `cutoff_hour` | as above |

Returns `overall` metrics, `daily`, `by_hour_of_day`, `histogram` and `horizon` (error by lead time).

### `POST /api/refresh`
Re-downloads all data from Elexon and replaces the cache.

Errors: `422` for out-of-range or inconsistent dates, `502` if Elexon cannot be reached.

---

## 8. Deployment

This project Frontend is deployed with **Vercel** 
Live Link : https://aabbccddxyz.vercel.app/

### Render (For Backend)

Create a new *Blueprint* from the repository; `render.yaml` defines a Docker web service with a `/api/health`
health check.

> Free-tier file systems are ephemeral, so after a restart the first request re-downloads the data from Elexon
> (around a minute). A paid plan with a persistent disk, or pre-seeding `elexon_cache.json`, avoids this.

---

## 9. Key development practices

- **Separation of concerns:** I/O (`elexon.py`), pure logic (`analysis.py`), HTTP layer (`main.py`), UI
  components.
- **Testable core:** analysis logic has no network or framework dependencies and is covered by unit tests.
- **Resilience:** Elexon calls use retries with back-off, chunked date windows and parallel downloads; the API
  returns clear errors (`502`) when the upstream is unavailable.
- **Input validation:** date ranges and cut-off hours are validated server-side.
- **Reproducible builds:** pinned Python dependencies, lockfile for the frontend, multi-stage Docker build.
- **Time-zone correctness:** all timestamps are UTC internally; cut-offs and displays use Europe/London.

---

## 10. Assumptions and limitations

- The day-ahead cut-off defaults to **09:00 UK time on D-1**, close to the auction gate closure; it is
  configurable in the UI.
- "Decisions made in January 2026" is interpreted as delivery days **2 Jan – 1 Feb 2026**.
- Only national wind from Elexon is used; no demand, price or other fuel types.
- A forecast with no publication before the cut-off for a half-hour is shown as missing and excluded from
  accuracy metrics.
- Error metrics are calculated over a single month, which is a small sample with one weather regime; they
  should be read as indicative, not as a long-run forecast skill estimate.
- The Elexon client uses the published query parameters for the `FUELHH` and `WINDFOR` stream endpoints. If the
  `FUELHH` settlement-date parameters are rejected it falls back to publish-time windows. If Elexon changes its
  API, update `backend/app/elexon.py`.

## 11. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| "Could not reach the API" in the UI | backend not running, or (dev) not on port 8000 |
| First load is slow | initial Elexon download; subsequent loads use the cache |
| `502 Could not load data from Elexon` | no outbound internet or Elexon unavailable; retry or call `POST /api/refresh` |
| Stale or incomplete data | `POST /api/refresh`, or delete `backend/data/elexon_cache.json` |

## 12. Data licence

Contains BMRS data © Elexon Limited copyright and database right. Use of the Insights Solution APIs is governed by
the BMRS Data Licence Terms and API Terms of Use.

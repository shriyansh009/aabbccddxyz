# Understanding the Wind Forecast Portal

This document explains what each main component does and how they work together. The application displays
Great Britain wind forecasts and actual generation, measures forecast accuracy, and estimates day-ahead
electricity purchases using demand supplied by the user.

## Application flow

1. The browser loads the React application.
2. The frontend calls the FastAPI backend under `/api`.
3. On the first data request, the backend loads Elexon BMRS data or reads its JSON cache, then builds an
   in-memory dataset.
4. The backend selects forecasts that were published by the chosen decision cut-off and calculates the
   requested summaries.
5. The frontend displays the response as charts, KPIs, and tables.

## Frontend components

| Component | Purpose |
|---|---|
| `frontend/src/main.jsx` | Browser entry point. Finds the page's `root` element, loads the global stylesheet, and renders `App`. |
| `frontend/src/App.jsx` | Main page shell. Loads metadata, lets the user choose a decision cut-off, switches between the three dashboard tabs, and displays loading or API errors. |
| `frontend/src/components/ProcurementView.jsx` | "Buy for tomorrow" view. Accepts flat or half-hourly demand and a confidence level, then displays estimated purchases, the risk buffer, the half-hour profile, and a back-test when actual data is available. |
| `frontend/src/components/ForecastView.jsx` | "Day-ahead forecast" view. Selects a delivery day and displays forecast and actual wind, summary KPIs, and half-hourly forecast details. |
| `frontend/src/components/AccuracyView.jsx` | "Forecast accuracy" view. Selects a date range and shows accuracy metrics and charts grouped by forecast lead time, delivery day, time of day, and error range. |
| `frontend/src/components/Kpi.jsx` | Reusable display for one key performance indicator: its label, value, and optional explanatory hint. |
| `frontend/src/api.js` | Frontend API client. Calls the backend endpoints, adds query parameters, parses JSON responses, and reports unsuccessful responses as errors. |
| `frontend/src/format.js` | Shared presentation helpers for formatting MW, MWh, percentages, and timestamps in UK local time. |
| `frontend/src/styles.css` | Global layout, typography, colours, and styling for dashboard controls, cards, charts, tables, and messages. |
| `frontend/index.html` | HTML page used by Vite as the React app entry document. |
| `frontend/vite.config.js` | Configures Vite and the React plugin. During development, it forwards `/api` requests to the FastAPI server. |
| `frontend/package.json` | Lists the frontend scripts and JavaScript dependencies, including React and Recharts. |

## Backend components

| Component | Purpose |
|---|---|
| `backend/app/main.py` | Creates the FastAPI application, defines API routes, validates request parameters, coordinates the data store, and serves the built frontend. |
| `backend/app/elexon.py` | Retrieves actuals and forecasts from Elexon's BMRS API, handles retries and date windows, and reads or writes the JSON data cache. |
| `backend/app/analysis.py` | Pure analysis logic: handles UK time and delivery periods, chooses the latest forecast available by the cut-off, and computes forecast and accuracy metrics. It does not perform network or file I/O. |
| `backend/app/procurement.py` | Calculates the half-hourly purchase plan from user-provided demand and forecast wind. It estimates a wind-risk buffer from historical forecast errors and reports a back-test when actuals exist. |
| `backend/app/config.py` | Central settings for the Elexon URL, cache and static-file locations, delivery date range, default cut-off, timezone, and lead-time horizons. Environment variables can override selected paths and the Elexon URL. |
| `backend/app/__init__.py` | Marks `app` as a Python package so its modules can be imported together. |
| `backend/requirements.txt` | Lists Python dependencies: FastAPI for the API, Uvicorn for serving it, HTTPX for Elexon requests, `tzdata` for timezone data, and pytest for tests. |
| `backend/tests/test_analysis.py` | Unit tests for key analysis behavior, including time-zone conversion, cut-off forecast selection, missing forecasts, and accuracy metrics. |
| `backend/data/elexon_cache.json` | Local cached Elexon data, used to avoid downloading it again when the cache is present. In deployments, the configured data directory can be backed by persistent storage. |

### API routes

| Route | Purpose |
|---|---|
| `GET /api/health` | Health check used to confirm that the backend is responding. |
| `GET /api/meta` | Returns the delivery date range, default cut-off, timezone, and loaded data information. |
| `GET /api/forecast` | Returns forecast and actual values for a delivery day and cut-off. |
| `GET /api/accuracy` | Returns forecast-error metrics and breakdowns for a date range and cut-off. |
| `GET /api/procurement` | Returns a purchase plan for a delivery day, based on the submitted demand and confidence level. |
| `POST /api/refresh` | Reloads Elexon data and updates the cache and in-memory dataset. |

## Build and deployment files

| Component | Purpose |
|---|---|
| `Dockerfile` | Builds the React frontend, installs the Python dependencies, copies both app parts into a runtime image, and starts Uvicorn. |
| `docker-compose.yml` | Runs the container locally and mounts a named volume for persistent downloaded data. |
| `render.yaml` | Describes the Render web service and its health-check path. |
| `heroku.yml` | Tells Heroku to build the web application from the Dockerfile. |

## Important terms

- **Delivery day (D):** The day the electricity is needed.
- **Decision cut-off (D-1):** The time on the previous day when the buying decision is made. The app only uses forecasts published at or before this point.
- **Actual:** Elexon's recorded wind generation for a half-hour settlement period.
- **Forecast error:** Forecast MW minus actual MW. A positive error means wind was over-forecast; a negative error means it was under-forecast.
- **MW and MWh:** MW measures power at a point in time. A half-hour's energy is MW multiplied by 0.5 hours, resulting in MWh.
- **Risk buffer:** Additional purchase allowance based on historical wind over-forecast errors at the selected confidence level. Demand is user-provided; it is not included in the Elexon wind datasets.

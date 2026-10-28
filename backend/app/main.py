"""FastAPI application: JSON API under /api plus the built React app served as static files."""
from __future__ import annotations

import logging
import os
import threading
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import analysis, config, elexon, procurement

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Wind Forecast Portal", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


class Store:
    """Holds the dataset in memory, backed by a JSON cache on disk."""

    def __init__(self):
        self._lock = threading.Lock()
        self._raw: dict | None = None
        self._ds: analysis.Dataset | None = None

    def _build(self, raw: dict):
        self._raw = raw
        self._ds = analysis.Dataset(raw["actuals"], raw["forecasts"])

    def get(self) -> analysis.Dataset:
        with self._lock:
            if self._ds is None:
                raw = elexon.read_cache()
                if raw is None:
                    raw = elexon.load_all()  # live call to Elexon
                    elexon.save_cache(raw)
                self._build(raw)
            return self._ds

    def refresh(self) -> dict:
        with self._lock:
            raw = elexon.load_all()
            elexon.save_cache(raw)
            self._build(raw)
            return self.info()

    def info(self) -> dict:
        raw = self._raw or {}
        return {
            "fetched_at": raw.get("fetched_at"),
            "actual_points": len(raw.get("actuals", [])),
            "forecast_points": len(raw.get("forecasts", [])),
        }


store = Store()


def _dataset() -> analysis.Dataset:
    try:
        return store.get()
    except elexon.ElexonError as exc:
        raise HTTPException(status_code=502, detail=f"Could not load data from Elexon: {exc}")


def _check_day(d: date):
    if not (config.DELIVERY_START <= d <= config.DELIVERY_END):
        raise HTTPException(
            status_code=422,
            detail=f"Delivery day must be between {config.DELIVERY_START} and {config.DELIVERY_END} "
                   "(decisions made in January 2026).")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta():
    _dataset()
    return {
        "delivery_start": config.DELIVERY_START.isoformat(),
        "delivery_end": config.DELIVERY_END.isoformat(),
        "default_cutoff_hour": config.DEFAULT_CUTOFF_HOUR,
        "timezone": config.TIMEZONE,
        "data": store.info(),
    }


@app.get("/api/forecast")
def forecast(delivery_day: date, cutoff_hour: float = Query(config.DEFAULT_CUTOFF_HOUR, ge=0, le=23.99)):
    _check_day(delivery_day)
    return analysis.forecast_for_day(_dataset(), delivery_day, cutoff_hour)


@app.get("/api/accuracy")
def accuracy(start: date = config.DELIVERY_START, end: date = config.DELIVERY_END,
             cutoff_hour: float = Query(config.DEFAULT_CUTOFF_HOUR, ge=0, le=23.99)):
    _check_day(start)
    _check_day(end)
    if end < start:
        raise HTTPException(status_code=422, detail="end must not be before start")
    return analysis.accuracy(_dataset(), start, end, cutoff_hour)


@app.get("/api/procurement")
def procurement_plan(delivery_day: date,
                     demand_mw: float | None = Query(None, ge=0),
                     demand_profile: str | None = None,
                     cutoff_hour: float = Query(config.DEFAULT_CUTOFF_HOUR, ge=0, le=23.99),
                     confidence: float = Query(0.95, ge=0.5, le=0.999)):
    """Power to buy day-ahead = (demand - forecast wind) + buffer for wind over-forecast risk.
    Demand is user supplied: a flat `demand_mw`, or `demand_profile` = comma-separated MW per half-hour."""
    _check_day(delivery_day)
    if demand_profile:
        try:
            demand = [float(x) for x in demand_profile.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=422, detail="demand_profile must be comma-separated numbers")
        if any(x < 0 for x in demand):
            raise HTTPException(status_code=422, detail="demand values must be >= 0")
    elif demand_mw is not None:
        demand = [demand_mw]
    else:
        raise HTTPException(status_code=422, detail="Provide demand_mw or demand_profile")
    try:
        return procurement.plan(_dataset(), delivery_day, cutoff_hour, demand, confidence)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/refresh")
def refresh():
    try:
        return store.refresh()
    except elexon.ElexonError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ---- static frontend (present in the Docker image after the React build) ----
_static = os.path.abspath(config.STATIC_DIR)
if os.path.isdir(_static):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = os.path.join(_static, path)
        if path and os.path.isfile(candidate) and os.path.abspath(candidate).startswith(_static):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_static, "index.html"))

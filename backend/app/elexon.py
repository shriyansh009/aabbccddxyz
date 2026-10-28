"""Thin client for the Elexon Insights (BMRS) API. No API key is required.

Endpoints used (stream variants return a plain JSON array):
  GET /datasets/FUELHH/stream  -> actual half-hourly generation by fuel type (we keep WIND)
  GET /datasets/WINDFOR/stream -> wind generation forecasts (publishTime, startTime, generation)
"""
from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import httpx

from . import config

log = logging.getLogger("elexon")


class ElexonError(RuntimeError):
    pass


def _get(client: httpx.Client, path: str, params: dict, retries: int = 3):
    url = f"{config.ELEXON_BASE_URL}{path}"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = client.get(url, params=params, timeout=60)
            if r.status_code == 400:
                raise ElexonError(f"400 from Elexon for {path} {params}: {r.text[:200]}")
            if r.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            body = r.json()
            return body["data"] if isinstance(body, dict) and "data" in body else body
        except ElexonError:
            raise
        except Exception as exc:  # noqa: BLE001 - retry on any transport problem
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise ElexonError(f"Elexon request failed after {retries} attempts: {path} {params}: {last}")


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _chunks(start: datetime, end: datetime, step: timedelta):
    cur = start
    while cur < end:
        nxt = min(cur + step, end)
        yield cur, nxt
        cur = nxt


def fetch_actuals(client: httpx.Client, start: date, end: date) -> list[tuple[str, float]]:
    """Wind actuals (startTime, MW). Dates are settlement dates, inclusive."""

    def one(window):
        a, b = window
        base = {"fuelType": "WIND"}
        try:
            rows = _get(client, "/datasets/FUELHH/stream",
                        {**base, "settlementDateFrom": a.date().isoformat(),
                         "settlementDateTo": b.date().isoformat()})
        except ElexonError:
            # Fallback in case the stream endpoint only accepts publish-time windows.
            rows = _get(client, "/datasets/FUELHH/stream",
                        {**base, "publishDateTimeFrom": _iso(a), "publishDateTimeTo": _iso(b)})
        return rows

    s = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    e = datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
    windows = list(_chunks(s, e, timedelta(days=6)))
    out: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for rows in pool.map(one, windows):
            for r in rows:
                if r.get("fuelType", "WIND") != "WIND" or r.get("generation") is None:
                    continue
                out[r["startTime"]] = float(r["generation"])
    return sorted(out.items())


def fetch_forecasts(client: httpx.Client, publish_from: datetime, publish_to: datetime
                    ) -> list[tuple[str, str, float]]:
    """Wind forecasts (publishTime, startTime, MW) published in the given window."""

    def one(window):
        a, b = window
        return _get(client, "/datasets/WINDFOR/stream",
                    {"publishDateTimeFrom": _iso(a), "publishDateTimeTo": _iso(b)})

    windows = list(_chunks(publish_from, publish_to, timedelta(days=2)))
    out: dict[tuple[str, str], float] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for rows in pool.map(one, windows):
            for r in rows:
                if r.get("generation") is None:
                    continue
                out[(r["publishTime"], r["startTime"])] = float(r["generation"])
    return sorted((p, s, g) for (p, s), g in out.items())


def load_all() -> dict:
    """Download everything needed for the January 2026 decision window."""
    with httpx.Client(headers={"Accept": "application/json"}) as client:
        actuals = fetch_actuals(client, config.DELIVERY_START, config.DELIVERY_END)
        # Forecasts for 2 Jan - 1 Feb delivery can be published a couple of days earlier
        # than the first decision, and we never need anything published after 1 Feb.
        pf = datetime.combine(config.DECISION_MONTH_START, datetime.min.time(),
                              tzinfo=timezone.utc) - timedelta(days=3)
        pt = datetime.combine(config.DELIVERY_END, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
        forecasts = fetch_forecasts(client, pf, pt)
    lo = f"{config.DELIVERY_START.isoformat()}T00:00:00Z"
    hi = f"{(config.DELIVERY_END + timedelta(days=1)).isoformat()}T00:00:00Z"
    forecasts = [f for f in forecasts if lo <= f[1].replace("+00:00", "Z") < hi]
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "actuals": actuals,
        "forecasts": forecasts,
    }


def save_cache(data: dict) -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    tmp = config.CACHE_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh)
    os.replace(tmp, config.CACHE_FILE)


def read_cache() -> dict | None:
    try:
        with open(config.CACHE_FILE) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

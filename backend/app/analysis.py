"""Pure analysis logic: forecast selection and error metrics. No I/O, easy to unit test.

Key idea: a day-ahead buyer standing at the cut-off on D-1 can only use forecasts that
were *published before that moment*. For every half-hour of delivery day D we therefore
take the latest forecast with publishTime <= cut-off(D-1). Accuracy is measured on exactly
those forecasts, so the numbers reflect what the buyer really had in hand.
"""
from __future__ import annotations

import bisect
import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config

LONDON = ZoneInfo(config.TIMEZONE)


def parse_dt(s: str) -> datetime:
    s = s.replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def decision_cutoff(delivery_day: date, cutoff_hour: float) -> datetime:
    """Cut-off = D-1 at `cutoff_hour` London local time, returned in UTC."""
    prev = delivery_day - timedelta(days=1)
    hours = int(cutoff_hour)
    minutes = int(round((cutoff_hour - hours) * 60))
    local = datetime.combine(prev, time(hours, minutes), tzinfo=LONDON)
    return local.astimezone(timezone.utc)


def delivery_window(delivery_day: date) -> tuple[datetime, datetime]:
    """UK settlement day boundaries expressed in UTC."""
    start = datetime.combine(delivery_day, time(0, 0), tzinfo=LONDON).astimezone(timezone.utc)
    end = datetime.combine(delivery_day + timedelta(days=1), time(0, 0), tzinfo=LONDON).astimezone(timezone.utc)
    return start, end


class Dataset:
    def __init__(self, actuals, forecasts):
        self.actuals: dict[datetime, float] = {parse_dt(t): g for t, g in actuals}
        by_target: dict[datetime, list[tuple[datetime, float]]] = defaultdict(list)
        for pub, start, gen in forecasts:
            by_target[parse_dt(start)].append((parse_dt(pub), gen))
        self.forecasts = {t: sorted(v) for t, v in by_target.items()}
        self._pub_index = {t: [p for p, _ in v] for t, v in self.forecasts.items()}

    def latest_before(self, target: datetime, limit: datetime):
        """Latest forecast for `target` published at or before `limit` -> (publish, MW) or None."""
        pubs = self._pub_index.get(target)
        if not pubs:
            return None
        i = bisect.bisect_right(pubs, limit)
        return self.forecasts[target][i - 1] if i else None

    def targets_between(self, start: datetime, end: datetime):
        ts = set(self.actuals) | set(self.forecasts)
        return sorted(t for t in ts if start <= t < end)


def forecast_for_day(ds: Dataset, delivery_day: date, cutoff_hour: float) -> dict:
    cutoff = decision_cutoff(delivery_day, cutoff_hour)
    start, end = delivery_window(delivery_day)
    rows = []
    for t in ds.targets_between(start, end):
        f = ds.latest_before(t, cutoff)
        a = ds.actuals.get(t)
        rows.append({
            "time": iso(t),
            "forecast_mw": f[1] if f else None,
            "published_at": iso(f[0]) if f else None,
            "actual_mw": a,
            "error_mw": (f[1] - a) if (f and a is not None) else None,
        })
    with_f = [r for r in rows if r["forecast_mw"] is not None]
    latest_pub = max((r["published_at"] for r in with_f), default=None)
    earliest_pub = min((r["published_at"] for r in with_f), default=None)
    return {
        "delivery_day": delivery_day.isoformat(),
        "decision_cutoff": iso(cutoff),
        "forecast_published_range": [earliest_pub, latest_pub],
        "summary": {
            "periods": len(rows),
            "periods_with_forecast": len(with_f),
            "avg_forecast_mw": _mean([r["forecast_mw"] for r in with_f]),
            "min_forecast_mw": min((r["forecast_mw"] for r in with_f), default=None),
            "max_forecast_mw": max((r["forecast_mw"] for r in with_f), default=None),
            # MWh = MW * 0.5h per settlement period
            "total_forecast_mwh": sum(r["forecast_mw"] for r in with_f) * 0.5 if with_f else None,
        },
        "rows": rows,
    }


# ---------------------------------------------------------------- metrics
def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def _pct(sorted_xs, p):
    if not sorted_xs:
        return None
    k = (len(sorted_xs) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (k - lo)


def metrics(pairs: list[tuple[float, float]]) -> dict:
    """pairs = [(forecast, actual)]. Error = forecast - actual (positive = over-forecast)."""
    if not pairs:
        return {"n": 0}
    errs = [f - a for f, a in pairs]
    abs_errs = sorted(abs(e) for e in errs)
    mean_actual = _mean(a for _, a in pairs)
    mae = _mean(abs_errs)
    rmse = math.sqrt(_mean(e * e for e in errs))
    signed = sorted(errs)
    return {
        "n": len(pairs),
        "mean_actual_mw": mean_actual,
        "mae_mw": mae,
        "rmse_mw": rmse,
        "bias_mw": _mean(errs),
        "nmae_pct": 100 * mae / mean_actual if mean_actual else None,
        "p50_abs_error_mw": _pct(abs_errs, 0.5),
        "p90_abs_error_mw": _pct(abs_errs, 0.9),
        "p95_abs_error_mw": _pct(abs_errs, 0.95),
        "max_abs_error_mw": abs_errs[-1],
        # Risk view for a buyer: wind is over-forecast -> too little bought day-ahead.
        "p95_over_forecast_mw": max(0.0, _pct(signed, 0.95)),
        "p95_under_forecast_mw": max(0.0, -_pct(signed, 0.05)),
    }


def _day_pairs(ds: Dataset, day: date, cutoff_hour: float):
    cutoff = decision_cutoff(day, cutoff_hour)
    start, end = delivery_window(day)
    out = []
    for t in ds.targets_between(start, end):
        a = ds.actuals.get(t)
        f = ds.latest_before(t, cutoff)
        if a is not None and f is not None:
            out.append((t, f[1], a))
    return out


def accuracy(ds: Dataset, start_day: date, end_day: date, cutoff_hour: float) -> dict:
    all_rows, daily = [], []
    day = start_day
    while day <= end_day:
        rows = _day_pairs(ds, day, cutoff_hour)
        all_rows.extend(rows)
        m = metrics([(f, a) for _, f, a in rows])
        daily.append({"day": day.isoformat(), **m})
        day += timedelta(days=1)

    pairs = [(f, a) for _, f, a in all_rows]

    by_hour = defaultdict(list)
    for t, f, a in all_rows:
        by_hour[t.astimezone(LONDON).hour].append((f, a))
    hourly = [{"hour": h, **metrics(by_hour[h])} for h in sorted(by_hour)]

    # Error histogram (forecast - actual), 500 MW bins.
    bin_w = 500
    hist = defaultdict(int)
    for f, a in pairs:
        hist[int(math.floor((f - a) / bin_w))] += 1
    histogram = [{"bin_start": k * bin_w, "bin_end": (k + 1) * bin_w, "count": hist[k]}
                 for k in sorted(hist)]

    return {
        "start": start_day.isoformat(),
        "end": end_day.isoformat(),
        "cutoff_hour": cutoff_hour,
        "overall": metrics(pairs),
        "daily": daily,
        "by_hour_of_day": hourly,
        "histogram": histogram,
        "horizon": horizon_analysis(ds, start_day, end_day),
    }


def horizon_analysis(ds: Dataset, start_day: date, end_day: date) -> list[dict]:
    """Error versus lead time: for each horizon h use the latest forecast published
    at least h hours before the target half-hour."""
    s, _ = delivery_window(start_day)
    _, e = delivery_window(end_day)
    targets = [t for t in ds.targets_between(s, e) if t in ds.actuals]
    out = []
    for h in config.HORIZONS_HOURS:
        pairs = []
        for t in targets:
            f = ds.latest_before(t, t - timedelta(hours=h))
            if f:
                pairs.append((f[1], ds.actuals[t]))
        m = metrics(pairs)
        out.append({"horizon_hours": h, **m})
    return out

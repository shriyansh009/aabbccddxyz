"""'How much do I need to buy for tomorrow?' logic. Pure functions, no I/O.

Residual need (MW) for a half-hour = demand - forecast wind. On top of that we add a buffer
for the risk that wind under-delivers: the `confidence` quantile of historical over-forecast
(forecast - actual). The buffer is learned ONLY from errors that were already known at the
decision time (delivery days <= D-2), so the recommendation never uses information from the
future. If too little history exists (start of the window) we fall back to the whole window
and flag the result as in-sample.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import analysis, config

MIN_HISTORY_SAMPLES = 48 * 3  # three days of half-hours


def historical_errors(ds: analysis.Dataset, day: date, cutoff_hour: float):
    """Signed errors (forecast - actual) usable at decision time for `day`.
    Returns (errors, in_sample)."""
    def collect(last_day: date):
        errs, d = [], config.DELIVERY_START
        while d <= last_day:
            errs.extend(f - a for _, f, a in analysis._day_pairs(ds, d, cutoff_hour))
            d += timedelta(days=1)
        return errs

    # Day D-1 is still in progress at the D-1 cut-off, so its outcome is not known yet.
    errs = collect(day - timedelta(days=2))
    if len(errs) >= MIN_HISTORY_SAMPLES:
        return errs, False
    return collect(config.DELIVERY_END), True


def buffers(errors: list[float], confidence: float) -> dict:
    s = sorted(errors)
    if not s:
        return {"over_mw": 0.0, "under_mw": 0.0, "n": 0}
    return {
        # wind over-forecast at this confidence -> extra power to buy
        "over_mw": max(0.0, analysis._pct(s, confidence)),
        # wind under-forecast at this confidence -> power we may over-buy
        "under_mw": max(0.0, -analysis._pct(s, 1 - confidence)),
        "n": len(s),
    }


def plan(ds: analysis.Dataset, day: date, cutoff_hour: float, demand: list[float],
         confidence: float) -> dict:
    fday = analysis.forecast_for_day(ds, day, cutoff_hour)
    rows = fday["rows"]
    if len(demand) == 1:
        demand = demand * len(rows)
    if len(demand) != len(rows):
        raise ValueError(f"Demand profile must have 1 or {len(rows)} values for {day}, got {len(demand)}")

    errs, in_sample = historical_errors(ds, day, cutoff_hour)
    buf = buffers(errs, confidence)

    out, missing = [], 0
    tot = dict(base=0.0, buffer=0.0, rec=0.0, demand=0.0, wind=0.0)
    bt = dict(have=False, need=0.0, base_short=0.0, rec_short=0.0, base_surplus=0.0, rec_surplus=0.0)

    for r, dem in zip(rows, demand):
        f, a = r["forecast_mw"], r["actual_mw"]
        if f is None:
            missing += 1
            out.append({**r, "demand_mw": dem, "base_buy_mw": None, "buffer_mw": None,
                        "recommended_buy_mw": None})
            continue
        base = max(0.0, dem - f)
        rec = min(dem, base + buf["over_mw"])        # never buy more than total demand
        out.append({**r, "demand_mw": dem, "base_buy_mw": base,
                    "buffer_mw": rec - base, "recommended_buy_mw": rec})
        tot["base"] += base * 0.5
        tot["buffer"] += (rec - base) * 0.5
        tot["rec"] += rec * 0.5
        tot["demand"] += dem * 0.5
        tot["wind"] += min(f, dem) * 0.5
        if a is not None:
            bt["have"] = True
            need = max(0.0, dem - a)
            bt["need"] += need * 0.5
            bt["base_short"] += max(0.0, need - base) * 0.5
            bt["rec_short"] += max(0.0, need - rec) * 0.5
            bt["base_surplus"] += max(0.0, base - need) * 0.5
            bt["rec_surplus"] += max(0.0, rec - need) * 0.5

    bought = [o["recommended_buy_mw"] for o in out if o["recommended_buy_mw"] is not None]
    return {
        "delivery_day": day.isoformat(),
        "decision_cutoff": fday["decision_cutoff"],
        "forecast_published_range": fday["forecast_published_range"],
        "confidence": confidence,
        "buffer": {**buf, "in_sample": in_sample},
        "totals_mwh": {
            "demand": tot["demand"], "wind_covered": tot["wind"], "base_buy": tot["base"],
            "buffer": tot["buffer"], "recommended_buy": tot["rec"],
        },
        "peak_recommended_buy_mw": max(bought, default=None),
        "periods_missing_forecast": missing,
        "backtest": {
            "available": bt["have"],
            "actual_need_mwh": bt["need"],
            "base": {"shortfall_mwh": bt["base_short"], "surplus_mwh": bt["base_surplus"]},
            "recommended": {"shortfall_mwh": bt["rec_short"], "surplus_mwh": bt["rec_surplus"]},
        } if bt["have"] else {"available": False},
        "rows": out,
    }

from datetime import date, datetime, timedelta, timezone

import pytest

from app import analysis


def T(h, d=3, m=0):
    return datetime(2026, 1, d, h, m, tzinfo=timezone.utc)


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_cutoff_is_previous_day_london_time_winter():
    # January: London == UTC
    assert analysis.decision_cutoff(date(2026, 1, 3), 9) == T(9, d=2)


def test_cutoff_respects_bst():
    # July: London = UTC+1 so 09:00 local is 08:00 UTC
    c = analysis.decision_cutoff(date(2026, 7, 2), 9)
    assert c == datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc)


def test_latest_forecast_before_cutoff_is_chosen_and_later_ones_ignored():
    target = T(12)
    forecasts = [
        (iso(T(6, d=2)), iso(target), 1000.0),   # published 06:00 D-1
        (iso(T(8, d=2)), iso(target), 1200.0),   # published 08:00 D-1  <- should be used
        (iso(T(10, d=2)), iso(target), 5000.0),  # after the 09:00 cut-off: must be ignored
    ]
    ds = analysis.Dataset([(iso(target), 1500.0)], forecasts)
    out = analysis.forecast_for_day(ds, date(2026, 1, 3), 9)
    row = next(r for r in out["rows"] if r["time"] == iso(target))
    assert row["forecast_mw"] == 1200.0
    assert row["published_at"] == iso(T(8, d=2))
    assert row["error_mw"] == -300.0  # under-forecast


def test_no_forecast_available_before_cutoff():
    target = T(12)
    ds = analysis.Dataset([(iso(target), 100.0)], [(iso(T(10, d=2)), iso(target), 50.0)])
    row = analysis.forecast_for_day(ds, date(2026, 1, 3), 9)["rows"][0]
    assert row["forecast_mw"] is None and row["error_mw"] is None


def test_metrics_known_values():
    m = analysis.metrics([(110, 100), (90, 100), (120, 100), (100, 100)])
    assert m["n"] == 4
    assert m["mae_mw"] == pytest.approx((10 + 10 + 20 + 0) / 4)
    assert m["bias_mw"] == pytest.approx((10 - 10 + 20 + 0) / 4)
    assert m["rmse_mw"] == pytest.approx(((100 + 100 + 400 + 0) / 4) ** 0.5)
    assert m["nmae_pct"] == pytest.approx(100 * 10 / 100)
    assert m["max_abs_error_mw"] == 20


def test_metrics_empty():
    assert analysis.metrics([]) == {"n": 0}


def test_accuracy_and_horizon_pipeline():
    targets = [T(h, m=m) for h in (10, 11) for m in (0, 30)]
    actuals = [(iso(t), 1000.0) for t in targets]
    forecasts = []
    for t in targets:
        forecasts.append((iso(t - timedelta(hours=30)), iso(t), 1300.0))  # old, poor forecast
        forecasts.append((iso(t - timedelta(hours=3)), iso(t), 1050.0))   # recent, better
    ds = analysis.Dataset(actuals, forecasts)
    res = analysis.accuracy(ds, date(2026, 1, 3), date(2026, 1, 3), 9)
    # day-ahead (cut-off 09:00 on 2 Jan) can only see the 30h-old forecast
    assert res["overall"]["mae_mw"] == pytest.approx(300.0)
    hz = {h["horizon_hours"]: h for h in res["horizon"]}
    assert hz[2]["mae_mw"] == pytest.approx(50.0)
    assert hz[24]["mae_mw"] == pytest.approx(300.0)  # only the 30h-old forecast qualifies
    assert hz[2]["mae_mw"] < hz[24]["mae_mw"]
    assert hz[48]["n"] == 0  # nothing was published 48h ahead

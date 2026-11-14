"""Processing tests use small SYNTHETIC FIXTURES to test arithmetic only. They are not scientific data."""
import pytest
from app.services.climate_processing import (annual_mean_from_monthly, kelvin_to_celsius, window_for_target,
                                             window_mean, ensemble_stats, grid_cell_bbox, annual_mean_from_daily)
from app.services.builders import build_observed_dataset, build_projection_dataset

def test_kelvin():
    assert kelvin_to_celsius(273.15) == pytest.approx(0.0)
    assert kelvin_to_celsius(300.0) == pytest.approx(26.85)

def test_annual_mean_requires_12_months():
    m = {i: 20.0 for i in range(1, 13)}
    assert annual_mean_from_monthly(m) == (20.0, 12)
    m[5] = None
    assert annual_mean_from_monthly(m) == (None, 11)
    m[5] = -999.0
    assert annual_mean_from_monthly(m)[0] is None

def test_windows_centered_and_clipped():
    assert window_for_target(2030) == (2020, 2039, False)
    assert window_for_target(2050) == (2040, 2059, False)
    assert window_for_target(2075) == (2065, 2084, False)
    assert window_for_target(2100) == (2090, 2100, True)  # 2090-2109 clipped to data end (11 yrs)

def test_window_mean_refuses_incomplete():
    with pytest.raises(ValueError):
        window_mean({2020: 1.0, 2022: 2.0}, 2020, 2022)

def test_ensemble_stats():
    s = ensemble_stats([1, 2, 3])
    assert s["mean"] == 2 and s["min"] == 1 and s["max"] == 3 and s["n_models"] == 3

def test_daily_requires_full_year():
    with pytest.raises(ValueError):
        annual_mean_from_daily([1.0] * 100)

def test_grid_cell_cairo():
    nex = grid_cell_bbox(30.0444, 31.2357, 0.25, 0.25, -89.875, 0.125)
    assert nex == pytest.approx([31.0, 30.0, 31.25, 30.25])
    power = grid_cell_bbox(30.0444, 31.2357, 0.5, 0.625, -90.0, -180.0)
    assert power[0] < 31.2357 < power[2] and power[1] < 30.0444 < power[3]

def _fake_power(years, drop=None, unit="C"):
    p = {}
    for y in years:
        for m in range(1, 13):
            p[f"{y}{m:02d}"] = 20.0 + (y - years[0]) * 0.1
        p[f"{y}13"] = 99.0  # POWER's annual key must be ignored
    if drop:
        p[drop] = -999.0
    return {"properties": {"parameter": {"T2M": p}}, "parameters": {"T2M": {"units": unit}}, "header": {"fill_value": -999}}

def test_build_observed_withholds_partial_year_and_checks_units():
    ds = build_observed_dataset(_fake_power(list(range(1990, 2026)), drop="202006"), location_id="cairo",
                                variable_id="air_temperature", lat=30.0444, lon=31.2357, request_url="x")
    r = {x.year: x for x in ds.records}
    assert r[2020].value is None and not r[2020].complete and r[2020].n_months == 11
    assert r[2021].complete
    assert ds.coverage["last_complete_year"] == 2025
    assert ds.record_type == "reanalysis"  # never labelled as direct observation
    with pytest.raises(ValueError):
        build_observed_dataset(_fake_power(list(range(1990, 2026)), unit="K"), location_id="cairo",
                               variable_id="air_temperature", lat=30.0, lon=31.0, request_url="x")

def test_build_observed_requires_baseline():
    with pytest.raises(ValueError):
        build_observed_dataset(_fake_power(list(range(2000, 2026))), location_id="cairo", variable_id="air_temperature",
                               lat=30.0, lon=31.0, request_url="x")

def test_build_projection_logic_with_test_double():
    calls = []
    def fake(model, scn, s, e):
        calls.append((model, scn, s, e))
        off = {"A": 0.0, "B": 1.0}[model[-1]]
        base = 295.0 + off
        add = {"historical": 0, "ssp245": 1.0, "ssp585": 2.0}[scn] * ((s + e) / 2 - 2000) / 50
        return base + add, 7300
    ds = build_projection_dataset(fake, location_id="cairo", variable_id="air_temperature", lat=30.0444, lon=31.2357,
                                  models=[{"id": "M-A"}, {"id": "M-B"}], backend="test")
    assert ("M-A", "historical", 1995, 2014) in calls
    assert ("M-A", "ssp585", 2090, 2100) in calls
    assert len(ds.records) == 2 * 4 * 2 and len(ds.ensemble) == 8
    e = next(x for x in ds.ensemble if x.scenario == "ssp585" and x.target_year == 2100)
    assert e.anomaly_mean > next(x for x in ds.ensemble if x.scenario == "ssp245" and x.target_year == 2100).anomaly_mean
    assert ds.windows[-1].clipped and ds.record_type == "projection"
    assert all(abs(r.anomaly - (r.value - r.baseline)) < 1e-6 for r in ds.records)

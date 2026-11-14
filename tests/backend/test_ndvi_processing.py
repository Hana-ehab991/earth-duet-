"""Phase 2: NDVI scaling, quality rules, annual processing and suitability (pure; no Earth Engine).

All numbers below are hand-made TEST FIXTURES that exercise arithmetic and rules. They are not Earth observations."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.services import ndvi_processing as P
from app.services.comparison_errors import ComparisonError
from app.services.comparison_validation import RegionRequest


def req(lat=30.0, lon=31.0, r=10.0, y0=2010, y1=2012):
    return RegionRequest(lat, lon, r, y0, y1, "ndvi")


def year(y, mean=0.45, valid=4500, comps=3.5, n=4, snow=0.0, cloud=0.05):
    return {"year": y, "n_images": n, "ndvi_mean": mean, "valid_pixels": valid, "mean_composites": comps,
            "snow_fraction": snow, "cloud_fraction": cloud}


def raw(years, total=5000, water=0):
    return {"total_pixels": total, "water_pixels": water, "years": years}


def run(years, total=5000, water=0, **kw):
    return P.process_region(raw(years, total, water), req(**kw), "2026-01-01T00:00:00+00:00", "test")


def test_scaling_factor_and_validity():
    assert P.scale_ndvi_raw(4500) == 0.45 and P.scale_ndvi_raw(10000) == 1.0 and P.scale_ndvi_raw(-2000) == -0.2
    assert P.scale_ndvi_raw(3000) == 0.3                      # no float noise (0.30000000000000004)
    for bad in (-3000, -2001, 10001, None, float("nan"), "4500", True):
        assert P.scale_ndvi_raw(bad) is None, bad


def test_quality_rule_matches_catalog_bits():
    assert P.DQA_EXCLUDED_BITS == (8, 10, 14, 15) and P.WATER_FLAGS == (0, 3, 5, 6, 7)
    assert P.pixel_is_valid(4500, 0, 0)
    assert not P.pixel_is_valid(4500, 1, 0)                   # marginal
    assert not P.pixel_is_valid(4500, 2, 0)                   # snow/ice summary
    assert not P.pixel_is_valid(4500, 3, 0)                   # cloudy summary
    for bit in P.DQA_EXCLUDED_BITS:
        assert not P.pixel_is_valid(4500, 0, 1 << bit), bit
    assert P.pixel_is_valid(4500, 0, 1 << 11)                 # land flag bit alone does not invalidate
    assert not P.pixel_is_valid(-3000, 0, 0)                  # fill value


def test_land_water_flag_extraction():
    assert P.land_water_flag(1 << 11) == 1 and not P.is_water(1 << 11)         # land
    assert P.is_water(7 << 11) and P.is_water(0) and P.is_water(5 << 11)       # deep ocean, shallow ocean, deep inland water
    assert not P.is_water(2 << 11) and not P.is_water(4 << 11)                 # shoreline / ephemeral are not counted


def test_season_window_end_exclusive():
    assert P.season_bounds(2012) == ("2012-04-01", "2012-06-01")


def test_normal_years_are_reported_with_values():
    r = run([year(2010, 0.40), year(2011, 0.42), year(2012, 0.44)])
    assert [a.value for a in r.annual] == [0.4, 0.42, 0.44] and r.suitability.status == "ok"
    assert all(a.reason_code is None for a in r.annual)
    assert r.methodology["processing_version"] == P.PROCESSING_VERSION and r.methodology["dataset_id"] == "MODIS/061/MOD13Q1"


def test_both_locations_get_identical_treatment():
    years = [year(2010, 0.4), year(2011, 0.5, valid=2000), year(2012, 0.3)]
    a = run(years, lat=30.0, lon=31.0).annual
    b = run(years, lat=24.0, lon=32.9).annual
    assert a == b                                              # same rules and thresholds, no per-location tuning


def test_missing_data_is_null_with_reason_never_filled():
    r = run([year(2010, 0.4), year(2011, None, valid=0), year(2012, 0.4, n=0)])
    assert r.annual[1].value is None and r.annual[1].reason_code == "no_valid_observations"
    assert r.annual[2].value is None and r.annual[2].reason_code == "no_composites"
    assert [w.code for w in r.suitability.warnings if w.code == "missing_years"] == ["missing_years"]


def test_snow_cloud_and_low_quality_handling():
    r = run([year(2010, 0.1, valid=1000, snow=0.7), year(2011, 0.1, valid=1000, cloud=0.6, snow=0.0),
             year(2012, 0.4, valid=1000, snow=0.0, cloud=0.05)])
    assert r.annual[0].reason_code == "snow_ice" and r.annual[0].value is None
    assert r.annual[1].reason_code == "cloud" and r.annual[1].value is None
    assert r.annual[2].reason_code == "insufficient_valid_pixels"
    assert all(a.value is None for a in r.annual) and r.suitability.status == "unavailable"


def test_too_few_composites_rejected():
    r = run([year(2010, 0.5, comps=1.2)], y1=2010)
    assert r.annual[0].reason_code == "insufficient_valid_composites" and r.annual[0].value is None


def test_ocean_is_unsuitable_and_reports_no_values():
    r = run([year(2010, -0.05), year(2011, -0.04)], total=5000, water=4800, y1=2011)
    assert r.suitability.status == "unsuitable" and r.suitability.water_fraction == 0.96
    assert all(a.value is None and a.reason_code == "water" for a in r.annual)
    assert r.suitability.warnings[0].code == "mostly_water"


def test_partial_water_is_a_warning_only():
    r = run([year(2010), year(2011)], water=1000, y1=2011)
    assert r.suitability.status == "warning" and "includes_water" in [w.code for w in r.suitability.warnings]
    assert all(a.value is not None for a in r.annual)


def test_sparse_vegetation_and_negative_value_warnings():
    r = run([year(2010, 0.08), year(2011, -0.02), year(2012, 0.10)])
    codes = [w.code for w in r.suitability.warnings]
    assert "sparse_vegetation" in codes and "negative_ndvi" in codes and r.suitability.status == "warning"
    assert r.annual[1].value == -0.02                          # negative NDVI is legitimate data, not an error


def test_season_warnings_by_latitude():
    assert "southern_hemisphere_season" in [w.code for w in run([year(2010)], lat=-20, y1=2010).suitability.warnings]
    assert "high_latitude_season" in [w.code for w in run([year(2010)], lat=70, y1=2010).suitability.warnings]
    assert run([year(2010)], lat=10, y1=2010).suitability.status == "ok"


def _err(fn):
    try:
        fn()
    except ComparisonError as e:
        return e.code
    return None


def test_bad_payloads_raise_instead_of_guessing():
    assert _err(lambda: P.process_region({"years": "x"}, req(), "t")) == "earth_engine_bad_response"
    assert _err(lambda: run([year(2010), year(2011)])) == "earth_engine_bad_response"                 # 2012 missing
    assert _err(lambda: run([year(2010, 4500.0), year(2011), year(2012)])) == "earth_engine_bad_response"  # unscaled value
    assert _err(lambda: run([year(2010, valid=6000), year(2011), year(2012)])) == "earth_engine_bad_response"
    assert _err(lambda: run([year(2010), year(2011), year(2012)], total=100, water=200)) == "earth_engine_bad_response"


def test_zero_footprint_is_unavailable_not_a_value():
    r = run([year(2010)], total=0, y1=2010)
    assert r.annual[0].reason_code == "no_pixels" and r.suitability.status == "unavailable"


def test_methodology_documents_everything_and_fingerprint_tracks_config():
    m = P.methodology(10)
    for k in ("quality_filtering", "temporal_aggregation", "spatial_support", "acceptance_rules", "limitations", "scale_factor", "doi"):
        assert k in m
    assert "not a measurement of vegetation area" in m["limitations"][0]
    fp = P.qa_config_fingerprint()
    assert fp == P.qa_config_fingerprint() and len(fp) == 16
    old = P.MIN_VALID_PIXEL_FRACTION
    try:
        P.MIN_VALID_PIXEL_FRACTION = 0.9
        assert P.qa_config_fingerprint() != fp                 # a different threshold must never share a cache key
    finally:
        P.MIN_VALID_PIXEL_FRACTION = old

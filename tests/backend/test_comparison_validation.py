"""Phase 2: request validation for arbitrary-location comparison (pure; no Earth Engine)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.services.comparison_errors import ComparisonError, HTTP_STATUS
from app.services.comparison_validation import (RegionRequest, haversine_km, validate_pair, validate_region_request)


def _ok(**kw):
    a = dict(latitude=30.0444, longitude=31.2357, radius_km=10, start_year=2010, end_year=2024, variable="ndvi")
    a.update(kw)
    return validate_region_request(**a)


def _code(**kw):
    try:
        _ok(**kw)
    except ComparisonError as e:
        return e.code
    return None


def test_valid_request_is_normalised():
    r = _ok(latitude=30.04441234, longitude=31.23569999, variable=" NDVI ")
    assert (r.latitude, r.longitude, r.variable) == (30.0444, 31.2357, "ndvi")
    assert r.radius_km == 10.0 and (r.start_year, r.end_year) == (2010, 2024)


def test_coordinates_validated():
    for kw in (dict(latitude=90.1), dict(latitude=-91), dict(longitude=180.5), dict(longitude=-181),
               dict(latitude=math.nan), dict(longitude=math.inf), dict(latitude="30"), dict(longitude=None),
               dict(latitude=True)):
        assert _code(**kw) == "invalid_coordinates", kw
    assert _code(latitude=90, longitude=180) is None and _code(latitude=-90, longitude=-180) is None


def test_radius_bounds_limit_request_cost():
    assert _code(radius_km=0.5) == "invalid_radius" and _code(radius_km=25.1) == "invalid_radius"
    assert _code(radius_km=math.nan) == "invalid_radius" and _code(radius_km="10") == "invalid_radius"
    assert _code(radius_km=1) is None and _code(radius_km=25) is None


def test_year_range_validated_and_future_rejected():
    assert _code(start_year=2025, end_year=2030) == "invalid_year_range"   # no invented future NDVI
    assert _code(start_year=2009) == "invalid_year_range"
    assert _code(start_year=2020, end_year=2015) == "invalid_year_range"
    assert _code(start_year=2010.5) == "invalid_year_range" and _code(end_year="2024") == "invalid_year_range"
    assert _code(start_year=2020, end_year=2020) is None


def test_only_ndvi_supported():
    assert _code(variable="evi") == "unsupported_variable" and _code(variable=None) == "unsupported_variable"


def test_pair_rules():
    a, b = _ok(), _ok(latitude=24.0889, longitude=32.8998)
    assert validate_pair(a, b) == []
    try:
        validate_pair(a, a)
        assert False
    except ComparisonError as e:
        assert e.code == "identical_locations"
    try:
        validate_pair(a, _ok(latitude=24.0889, longitude=32.8998, radius_km=5))
        assert False
    except ComparisonError as e:
        assert e.code == "mismatched_spatial_support"
    near = validate_pair(a, _ok(latitude=30.10, longitude=31.30))
    assert [w.code for w in near] == ["regions_overlap"]


def test_haversine_and_error_codes_have_http_status():
    assert abs(haversine_km(0, 0, 0, 1) - 111.19) < 0.1
    for code in ("invalid_coordinates", "earth_engine_not_configured", "earth_engine_timeout", "earth_engine_busy"):
        assert code in HTTP_STATUS
    assert ComparisonError("x", "m", "h").to_body() == {"error": {"code": "x", "message": "m", "hint": "h"}}

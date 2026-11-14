"""Phase 2: Earth Engine service behaviour with a MOCK `ee` module. No network, no credentials.

The canned payloads are TEST FIXTURES, never real observations, and are only used to check plumbing:
authentication order, error mapping, request limits, timeouts and that failures never produce data."""
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.services.comparison_errors import ComparisonError
from app.services.comparison_settings import ComparisonSettings, get_comparison_settings
from app.services.comparison_validation import RegionRequest
from app.services.earth_engine_service import EarthEngineClient, build_request_graph, classify_exception

REQ = RegionRequest(30.0444, 31.2357, 10.0, 2010, 2011, "ndvi")
FIXTURE_RAW = {"total_pixels": 5000, "water_pixels": 0, "years": [
    {"year": 2010, "n_images": 4, "ndvi_mean": 0.31, "valid_pixels": 4400, "mean_composites": 3.2, "snow_fraction": 0.0, "cloud_fraction": 0.1},
    {"year": 2011, "n_images": 4, "ndvi_mean": 0.33, "valid_pixels": 4500, "mean_composites": 3.4, "snow_fraction": 0.0, "cloud_fraction": 0.1}]}


def settings(**kw):
    d = dict(ee_project="test-project", ee_timeout_s=5.0, ee_max_concurrent=2, ee_queue_wait_s=0.2)
    d.update(kw)
    return ComparisonSettings(**d)


def fake_ee(raw=FIXTURE_RAW):
    ee = MagicMock(name="ee")
    ee.__version__ = "0.0-test"
    ee.Dictionary.return_value.combine.return_value.getInfo.return_value = raw
    return ee


def client(ee=None, adc=None, **kw):
    return EarthEngineClient(settings(**kw), ee_module=ee or fake_ee(), adc_loader=adc or (lambda scopes: ("CREDS", "p")))


def code_of(fn):
    try:
        fn()
    except ComparisonError as e:
        return e.code
    return None


# ------------------------------------------------------------------------------------------------ auth
def test_uses_application_default_credentials_with_explicit_project():
    ee = fake_ee()
    scopes_seen = []
    c = client(ee, adc=lambda scopes: (scopes_seen.append(scopes) or "CREDS", "p"))
    c.ensure_initialized()
    ee.Initialize.assert_called_once_with(credentials="CREDS", project="test-project")
    assert "https://www.googleapis.com/auth/earthengine" in scopes_seen[0]


def test_falls_back_to_stored_local_credentials_when_no_adc():
    ee = fake_ee()

    class DefaultCredentialsError(Exception):
        pass

    def no_adc(scopes):
        raise DefaultCredentialsError("Your default credentials were not found.")

    client(ee, adc=no_adc).ensure_initialized()
    ee.Initialize.assert_called_once_with(project="test-project")        # `earthengine authenticate` path


def test_missing_project_or_package_is_not_configured_and_no_key_files_are_involved():
    assert code_of(lambda: client(ee_project=None).ensure_initialized()) == "earth_engine_not_configured"
    c = EarthEngineClient(settings())
    c._ee_module = MagicMock(side_effect=ComparisonError("earth_engine_not_configured", "x"))
    assert code_of(c.ensure_initialized) == "earth_engine_not_configured"
    src = (Path(__file__).resolve().parents[2] / "backend/app/services/earth_engine_service.py").read_text()
    assert "ServiceAccountCredentials" not in src and "private-key" not in src.lower() and "json_key" not in src.lower()


def test_both_auth_paths_failing_gives_structured_error_without_leaking_details():
    ee = fake_ee()
    ee.Initialize.side_effect = Exception("403 Caller does not have required permission to use project secret-proj")
    err = None
    try:
        client(ee).ensure_initialized()
    except ComparisonError as e:
        err = e
    assert err.code == "earth_engine_auth_failed" and "secret-proj" not in err.message


# --------------------------------------------------------------------------------- error classification
def test_error_mapping_table():
    cases = [
        (Exception("Computation timed out."), "earth_engine_timeout"),
        (Exception("User memory limit exceeded."), "earth_engine_computation_limit"),
        (Exception("Quota exceeded for quota metric"), "earth_engine_quota_exceeded"),
        (Exception("429 Too Many Requests"), "earth_engine_quota_exceeded"),
        (Exception("Too many concurrent aggregations."), "earth_engine_quota_exceeded"),
        (Exception("Caller does not have required permission"), "earth_engine_auth_failed"),
        (Exception("Project not registered / not signed up for Earth Engine"), "earth_engine_auth_failed"),
        (Exception("ImageCollection asset 'MODIS/061/MOD13Q1' not found (does not exist or caller does not have access)"),
         "earth_engine_dataset_unavailable"),
        (ConnectionError("reset by peer"), "earth_engine_unavailable"),
        (Exception("503 Service Unavailable"), "earth_engine_unavailable"),
        (Exception("something odd"), "earth_engine_error"),
    ]
    for exc, expected in cases:
        assert classify_exception(exc).code == expected, (exc, classify_exception(exc).code)

    class DefaultCredentialsError(Exception): pass
    class RefreshError(Exception): pass
    assert classify_exception(DefaultCredentialsError("x")).code == "earth_engine_not_configured"
    assert classify_exception(RefreshError("invalid_grant")).code == "earth_engine_auth_failed"
    assert classify_exception(Exception("1403 pixels")).code == "earth_engine_error"       # '403' only as a whole token
    keep = ComparisonError("invalid_radius", "m")
    assert classify_exception(keep) is keep


# ------------------------------------------------------------------------------------------ graph / fetch
def test_graph_uses_documented_dataset_window_and_identical_spatial_support():
    ee = fake_ee()
    build_request_graph(ee, REQ)
    ee.ImageCollection.assert_any_call("MODIS/061/MOD13Q1")
    ee.Geometry.Point.assert_called_with([31.2357, 30.0444])                    # [lon, lat]
    ee.Geometry.Point.return_value.buffer.assert_called_with(10000.0)           # 10 km in metres
    base = ee.ImageCollection.return_value
    dates = [c.args for c in base.filterDate.call_args_list]
    assert ("2010-04-01", "2011-06-01") in dates                                # reference window
    assert ("2010-04-01", "2010-06-01") in dates and ("2011-04-01", "2011-06-01") in dates   # end exclusive


def test_reduce_region_parameters_are_identical_for_every_call():
    ee = fake_ee()
    seen = []
    img = MagicMock()
    img.reduceRegion.side_effect = lambda **kw: seen.append(kw) or MagicMock()
    # route every derived image to one recording mock
    for attr in ("select", "unmask", "rename", "selfMask", "updateMask", "multiply", "mean", "count", "rightShift", "bitwiseAnd",
                 "eq", "gt", "gte", "lte", "And", "Or"):
        getattr(img, attr).return_value = img
    img.projection.return_value = "PROJ"
    base = ee.ImageCollection.return_value
    base.filterDate.return_value.sort.return_value.first.return_value = img
    ee.Image.return_value = img
    col = base.filterDate.return_value                       # every season collection routes to the recording image
    col.map.return_value = col
    col.mean.return_value = img
    col.count.return_value = img
    build_request_graph(ee, REQ)
    assert seen, "reduceRegion was never called"
    for kw in seen:
        assert kw["scale"] == 250 and kw["crs"] == "PROJ" and kw["maxPixels"] == int(1e8)
        assert kw["geometry"] is ee.Geometry.Point.return_value.buffer.return_value


def test_fetch_processes_payload_and_stamps_provenance():
    r = client().fetch_ndvi_annual(REQ)
    assert [a.value for a in r.annual] == [0.31, 0.33] and r.earth_engine_api_version == "0.0-test"
    assert r.retrieved_at.endswith("+00:00") and r.methodology["dataset_id"] == "MODIS/061/MOD13Q1"


def test_failures_raise_and_never_return_data():
    ee = fake_ee()
    ee.Dictionary.return_value.combine.return_value.getInfo.side_effect = Exception("Computation timed out.")
    assert code_of(lambda: client(ee).fetch_ndvi_annual(REQ)) == "earth_engine_timeout"
    ee2 = fake_ee(raw={"total_pixels": 10})                                     # malformed payload
    assert code_of(lambda: client(ee2).fetch_ndvi_annual(REQ)) == "earth_engine_bad_response"
    assert code_of(lambda: client(ee_project=None).fetch_ndvi_annual(REQ)) == "earth_engine_not_configured"


def test_probe_reports_ready_or_raises():
    ee = fake_ee()
    ee.ImageCollection.return_value.limit.return_value.size.return_value.getInfo.return_value = 1
    p = client(ee).probe()
    assert p["status"] == "ready" and p["dataset_reachable"] is True and "project" not in p


# -------------------------------------------------------------------- concurrency, timeout, busy
def test_timeout_returns_error_and_slot_is_held_until_the_computation_really_ends():
    ee = fake_ee()
    release = threading.Event()
    ee.Dictionary.return_value.combine.return_value.getInfo.side_effect = lambda: release.wait(5) and FIXTURE_RAW
    c = client(ee, ee_timeout_s=0.2, ee_max_concurrent=1, ee_queue_wait_s=0.1)
    assert code_of(lambda: c.fetch_ndvi_annual(REQ)) == "earth_engine_timeout"
    assert code_of(lambda: c.fetch_ndvi_annual(REQ)) == "earth_engine_busy"      # abandoned work still occupies the slot
    release.set()
    time.sleep(0.3)
    ee.Dictionary.return_value.combine.return_value.getInfo.side_effect = None
    ee.Dictionary.return_value.combine.return_value.getInfo.return_value = FIXTURE_RAW
    assert c.fetch_ndvi_annual(REQ).annual[0].value == 0.31                       # slot released afterwards


def test_settings_from_environment_are_clamped():
    import os
    saved = {k: os.environ.get(k) for k in ("EE_PROJECT", "GOOGLE_CLOUD_PROJECT", "EARTH_DUET_EE_MAX_CONCURRENT", "EARTH_DUET_EE_TIMEOUT_S")}
    try:
        os.environ.pop("EE_PROJECT", None)
        os.environ["GOOGLE_CLOUD_PROJECT"] = "gcp-fallback"
        os.environ["EARTH_DUET_EE_MAX_CONCURRENT"] = "9999"
        os.environ["EARTH_DUET_EE_TIMEOUT_S"] = "not-a-number"
        s = get_comparison_settings()
        assert s.ee_project == "gcp-fallback" and s.ee_max_concurrent == 16 and s.ee_timeout_s == 60.0
        os.environ["EE_PROJECT"] = "primary"
        assert get_comparison_settings().ee_project == "primary"
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

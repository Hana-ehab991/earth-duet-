"""Phase 3: comparison orchestration (cache + Earth Engine plumbing + response assembly) with a MOCKED Earth Engine.

Nothing here touches Earth Engine or the network, and nothing here proves the live integration works."""
import concurrent.futures
import sqlite3
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.services import ndvi_processing as P
from app.services.comparison_cache import ComparisonCache
from app.services.comparison_errors import ComparisonError
from app.services.comparison_settings import ComparisonSettings
from app.services.earth_engine_service import EarthEngineClient
from app.services.location_comparison import API_HTTP_STATUS, LocationComparisonService, RateLimited
from comparison_fakes import ASWAN, CAIRO, FakeClient, api_settings, body, make_service, raw_payload


def err_code(svc, payload):
    with pytest.raises(ComparisonError) as e:
        svc.compare(payload)
    return e.value.code


# ------------------------------------------------------------------------------------------ happy path
def test_valid_request_live_then_cached(tmp_path):
    svc, client = make_service(tmp_path)
    r1 = svc.compare(body())
    assert (r1["dataStatus"], r1["resultStatus"], r1["dataOrigin"], r1["isSynthetic"]) == ("live", "complete", "earth_engine", False)
    assert len(client.calls) == 2 and r1["variable"] == "ndvi" and r1["unit"].startswith("dimensionless")
    assert [o["year"] for o in r1["locationA"]["observations"]] == [2010, 2011, 2012, 2013, 2014]
    assert r1["locationA"]["dataStatus"] == r1["locationB"]["dataStatus"] == "live"
    assert r1["locationA"]["cache"]["status"] == "miss" and r1["locationA"]["cache"]["expiresAt"]
    r2 = svc.compare(body())
    assert len(client.calls) == 2                                  # no new Earth Engine calls
    assert r2["dataStatus"] == "cached" and r2["locationA"]["cache"]["status"] == "hit"
    assert r2["locationA"]["observations"] == r1["locationA"]["observations"]
    assert r2["locationA"]["retrievedAt"] == r1["locationA"]["retrievedAt"]     # original retrieval time preserved


def test_both_locations_get_identical_processing_and_provenance(tmp_path):
    svc, client = make_service(tmp_path)
    r = svc.compare(body(radiusKm=7.5))
    a, b = client.calls
    assert (a.radius_km, a.start_year, a.end_year, a.variable) == (b.radius_km, b.start_year, b.end_year, b.variable) == (7.5, 2010, 2014, "ndvi")
    p, m = r["provenance"], r["methodology"]
    assert (p["datasetId"], p["datasetVersion"], p["processingVersion"]) == ("MODIS/061/MOD13Q1", "061", P.PROCESSING_VERSION)
    assert p["configFingerprint"] == P.qa_config_fingerprint() and p["doi"] and p["sourceUrl"]
    assert m["scaleFactor"] == 0.0001 and m["seasonalWindow"] == {"start": "04-01", "endExclusive": "06-01"}
    assert "Nothing is gap-filled" in m["qualityFiltering"] and m["temporalAggregation"] and m["spatialAggregation"]
    assert any("not a measurement of vegetation area" in x for x in m["limitations"])


def test_partially_cached(tmp_path):
    svc, client = make_service(tmp_path)
    svc.compare(body())
    r = svc.compare(body(locationB={"latitude": 25.0, "longitude": 32.0}))
    assert r["dataStatus"] == "partially_cached"
    assert (r["locationA"]["dataStatus"], r["locationB"]["dataStatus"]) == ("cached", "live")
    assert len(client.calls) == 3


def test_cache_persists_across_service_restart(tmp_path):
    svc1, c1 = make_service(tmp_path)
    r1 = svc1.compare(body())
    svc2, c2 = make_service(tmp_path)                                # brand-new service + cache object, same file
    r2 = svc2.compare(body())
    assert c2.calls == [] and r2["dataStatus"] == "cached"
    assert r2["locationB"]["observations"] == r1["locationB"]["observations"]


@pytest.mark.parametrize("change", [{"radiusKm": 11}, {"startYear": 2011}, {"endYear": 2013}])
def test_parameter_change_invalidates(tmp_path, change):
    svc, client = make_service(tmp_path)
    svc.compare(body())
    r = svc.compare(body(**change))
    assert r["dataStatus"] == "live" and len(client.calls) == 4


def test_processing_change_invalidates(tmp_path, monkeypatch):
    svc, client = make_service(tmp_path)
    svc.compare(body())
    monkeypatch.setattr(P, "PROCESSING_VERSION", "ndvi-annual-v2")
    r = svc.compare(body())
    assert r["dataStatus"] == "live" and len(client.calls) == 4 and r["provenance"]["processingVersion"] == "ndvi-annual-v2"


def test_coordinates_are_canonicalised_and_reported(tmp_path):
    svc, client = make_service(tmp_path)
    r = svc.compare(body(locationA={"latitude": 30.04441, "longitude": 31.23574}))
    la = r["locationA"]
    assert (la["latitude"], la["longitude"]) == (30.0444, 31.2357)
    assert (la["requestedLatitude"], la["requestedLongitude"]) == (30.04441, 31.23574)
    assert (la["cache"]["canonicalLatitude"], la["cache"]["canonicalLongitude"]) == ("30.0444", "31.2357")
    assert 30.0444 in [c.latitude for c in client.calls]            # the region actually queried is the canonical one
    assert 30.04441 not in [c.latitude for c in client.calls]
    # 0.0001 deg away is a different region and a different cache entry
    r2 = svc.compare(body(locationA={"latitude": 30.0445, "longitude": 31.2357}))
    assert r2["locationA"]["dataStatus"] == "live" and r2["locationA"]["cache"]["key"] != la["cache"]["key"]


# ------------------------------------------------------------------------------------ missing / no data
def test_missing_observations_are_null_with_reasons_and_never_filled(tmp_path):
    client = FakeClient(payload=lambda req: raw_payload(req, missing_years=(2011, 2012)))
    svc, _ = make_service(tmp_path, client=client)
    r = svc.compare(body())
    obs = {o["year"]: o for o in r["locationA"]["observations"]}
    for y in (2011, 2012):
        assert obs[y]["value"] is None and obs[y]["qualityStatus"] == "unavailable" and obs[y]["reasonCode"] == "no_composites"
        assert obs[y]["reason"]
    assert obs[2010]["value"] is not None and obs[2010]["qualityStatus"] == "valid" and obs[2010]["reasonCode"] is None
    assert any(w["code"] == "missing_years" for w in r["locationA"]["warnings"])
    assert r["comparableYears"] == [2010, 2013, 2014] and r["resultStatus"] == "complete"


def test_no_usable_data_is_a_structured_success_not_an_http_error(tmp_path):
    client = FakeClient(payload=lambda req: raw_payload(req, total=5000, water=4900))     # open ocean
    svc, _ = make_service(tmp_path, client=client)
    r = svc.compare(body())
    assert r["resultStatus"] == "no_usable_data" and r["comparableYears"] == []
    for loc in (r["locationA"], r["locationB"]):
        assert loc["hasUsableData"] is False and loc["validYearCount"] == 0
        assert all(o["value"] is None and o["qualityStatus"] == "unavailable" and o["reasonCode"] == "water" for o in loc["observations"])
        assert loc["suitability"]["status"] == "unsuitable" and any(w["code"] == "mostly_water" for w in loc["warnings"])
    assert any(w["code"] == "no_usable_data" for w in r["comparisonWarnings"])
    assert "nothing was estimated" in r["resultMessage"]
    # a deterministic outcome of real data: cached like any other result
    assert svc.compare(body())["dataStatus"] == "cached"


def test_partial_data_when_only_one_location_is_usable(tmp_path):
    def payload(req):
        return raw_payload(req, total=5000, water=4900) if req.latitude == CAIRO["latitude"] else raw_payload(req)
    svc, _ = make_service(tmp_path, client=FakeClient(payload=payload))
    r = svc.compare(body())
    assert r["resultStatus"] == "partial_data" and r["locationA"]["hasUsableData"] is False and r["locationB"]["hasUsableData"] is True
    assert r["comparableYears"] == [] and any(w["code"] == "one_location_without_data" for w in r["comparisonWarnings"])


def test_scientific_warnings_are_returned(tmp_path):
    svc, _ = make_service(tmp_path, client=FakeClient(payload=lambda req: raw_payload(req, base=0.08, water=800)))
    r = svc.compare(body(locationB={"latitude": -33.9, "longitude": 18.4}))
    a = {w["code"] for w in r["locationA"]["warnings"]}
    b = {w["code"] for w in r["locationB"]["warnings"]}
    assert {"sparse_vegetation", "includes_water"} <= a
    assert "southern_hemisphere_season" in b


def test_overlapping_regions_are_a_warning_not_an_error(tmp_path):
    svc, _ = make_service(tmp_path)
    r = svc.compare(body(locationB={"latitude": 30.05, "longitude": 31.24}))
    assert any(w["code"] == "regions_overlap" for w in r["comparisonWarnings"])


# ------------------------------------------------------------------------------------------ validation
@pytest.mark.parametrize("payload,code", [
    (body(locationA={"latitude": 91, "longitude": 0}), "invalid_coordinates"),
    (body(locationB={"latitude": 0, "longitude": 181}), "invalid_coordinates"),
    (body(locationA={"latitude": "30", "longitude": 31}), "invalid_coordinates"),
    (body(locationA={"latitude": float("nan"), "longitude": 31}), "invalid_coordinates"),
    (body(locationA={"latitude": True, "longitude": 31}), "invalid_coordinates"),
    (body(radiusKm=0.5), "invalid_radius"), (body(radiusKm=26), "invalid_radius"), (body(radiusKm="10"), "invalid_radius"),
    (body(startYear=2015, endYear=2012), "invalid_year_range"), (body(startYear=2009), "invalid_year_range"),
    (body(endYear=2025), "invalid_year_range"), (body(startYear=2010.5), "invalid_year_range"),
    (body(variable="temperature"), "unsupported_variable"), (body(variable=5), "unsupported_variable"),
    (body(locationB={"latitude": 30.0444, "longitude": 31.2357}), "identical_locations"),
    (body(locationB={"latitude": 30.04441, "longitude": 31.23572}), "identical_locations"),   # identical after rounding
    ([], "invalid_request"), ("x", "invalid_request"), ({}, "invalid_request"),
    ({k: v for k, v in body().items() if k != "startYear"}, "invalid_request"),
    (dict(body(), radius_km=10), "invalid_request"),
    (body(locationA={"latitude": 1}), "invalid_request"), (body(locationA=None), "invalid_request"),
    (body(locationA={"latitude": 1, "longitude": 2, "extra": 3}), "invalid_request"),
])
def test_invalid_requests_never_reach_earth_engine(tmp_path, payload, code):
    svc, client = make_service(tmp_path)
    assert err_code(svc, payload) == code
    assert client.calls == []


def test_variable_and_radius_defaults_are_documented_behaviour(tmp_path):
    svc, client = make_service(tmp_path)
    p = body(); del p["variable"]; del p["radiusKm"]
    r = svc.compare(p)
    assert r["variable"] == "ndvi" and r["radiusKm"] == 10.0


def test_variable_is_case_insensitive_and_reported_normalised(tmp_path):
    svc, _ = make_service(tmp_path)
    assert svc.compare(body(variable=" NDVI "))["variable"] == "ndvi"


# ---------------------------------------------------------------------------------------------- errors
@pytest.mark.parametrize("exc,code,retryable", [
    (ComparisonError("earth_engine_not_configured", "not configured", "set it up"), "earth_engine_not_configured", False),
    (ComparisonError("earth_engine_auth_failed", "rejected", "fix roles"), "earth_engine_auth_failed", False),
    (ComparisonError("earth_engine_timeout", "slow", "retry", retryable=True), "earth_engine_timeout", True),
    (ComparisonError("earth_engine_quota_exceeded", "quota", "later", retryable=True), "earth_engine_quota_exceeded", True),
    (ComparisonError("earth_engine_bad_response", "odd payload"), "earth_engine_bad_response", False),
])
def test_provider_failures_propagate_and_are_not_cached(tmp_path, exc, code, retryable):
    svc, client = make_service(tmp_path, client=FakeClient(error=exc))
    with pytest.raises(ComparisonError) as e:
        svc.compare(body())
    assert e.value.code == code and e.value.retryable is retryable and API_HTTP_STATUS[code] in (429, 502, 503, 504)
    assert svc.cache.status()["entryCount"] in (0, None)
    client.error = None                                           # provider recovers -> a normal live answer
    assert svc.compare(body())["dataStatus"] == "live"


def test_unexpected_exception_is_hidden_behind_internal_error(tmp_path):
    secret = "C:\\Users\\me\\secret\\key.json and /home/app/.config/gcloud/token"
    svc, _ = make_service(tmp_path, client=FakeClient(error=RuntimeError(secret)))
    with pytest.raises(ComparisonError) as e:
        svc.compare(body())
    text = f"{e.value.code} {e.value.message} {e.value.hint}"
    assert e.value.code == "internal_error" and "secret" not in text and "gcloud" not in text and "Traceback" not in text


def test_provider_text_and_paths_are_not_exposed(tmp_path):
    leaky = ComparisonError("earth_engine_error", "Earth Engine returned an unexpected error.",
                            "Traceback in /home/app/venv/lib/python3.12/site-packages/ee/data.py line 9")
    svc, _ = make_service(tmp_path, client=FakeClient(error=leaky))
    with pytest.raises(ComparisonError) as e:
        svc.compare(body())
    assert "/home/app" not in (e.value.hint or "") and "site-packages" not in (e.value.hint or "")
    leaky2 = ComparisonError("earth_engine_auth_failed", "x at C:\\Users\\me\\creds.json", "see /var/secrets/key")
    svc2, _ = make_service(tmp_path / "b", client=FakeClient(error=leaky2))
    with pytest.raises(ComparisonError) as e2:
        svc2.compare(body())
    assert "Users" not in e2.value.message and "/var/secrets" not in (e2.value.hint or "")


def test_one_location_failing_fails_the_request_but_caches_the_other(tmp_path):
    class Half(FakeClient):
        def fetch_ndvi_annual(self, req):
            if req.latitude == ASWAN["latitude"]:
                raise ComparisonError("earth_engine_quota_exceeded", "quota", "later", retryable=True)
            return super().fetch_ndvi_annual(req)
    svc, _ = make_service(tmp_path, client=Half())
    with pytest.raises(ComparisonError):
        svc.compare(body())
    time.sleep(0.1)
    assert svc.cache.status()["entryCount"] == 1                    # A is cached, B (the failure) is not


def test_request_deadline_gives_a_timeout_error(tmp_path):
    svc, _ = make_service(tmp_path, client=FakeClient(delay=1.0), request_deadline_s=0.2)
    assert err_code(svc, body()) == "earth_engine_timeout"
    time.sleep(1.3)                                  # let the abandoned fetches finish before the temp dir is removed


def test_cache_failure_never_fails_the_request(tmp_path):
    (tmp_path / "bad.sqlite").write_bytes(b"not a database" * 100)
    svc, client = make_service(tmp_path, cache=ComparisonCache(tmp_path / "bad.sqlite"))
    r = svc.compare(body())
    assert r["dataStatus"] == "live" and r["locationA"]["cache"]["expiresAt"] is None
    assert svc.status()["cache"]["accessible"] is False


def test_cache_disabled_always_goes_live(tmp_path):
    svc, client = make_service(tmp_path, cache_ttl_days=0)
    svc.compare(body()); r = svc.compare(body())
    assert len(client.calls) == 4 and r["locationA"]["cache"]["status"] == "disabled"


# ------------------------------------------------------------------------------------------ concurrency
def test_concurrent_identical_requests_share_one_fetch_per_location(tmp_path):
    svc, client = make_service(tmp_path, client=FakeClient(delay=0.3))
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda _: svc.compare(body()), range(8)))
    assert len(client.calls) == 2                                   # one live fetch each for A and B
    assert all(r["resultStatus"] == "complete" for r in results)
    assert len({tuple(o["value"] for o in r["locationA"]["observations"]) for r in results}) == 1
    assert svc._flights == {}


def test_concurrent_different_requests(tmp_path):
    svc, client = make_service(tmp_path)
    def one(i):
        return svc.compare(body(locationA={"latitude": 10.0 + i, "longitude": 20.0}, locationB={"latitude": -10.0 - i, "longitude": 40.0}))
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        rs = list(pool.map(one, range(8)))
    assert len(client.calls) == 16 and all(r["dataStatus"] == "live" for r in rs)
    assert svc.cache.status()["entryCount"] == 16


def test_failure_of_the_leading_request_reaches_waiting_requests(tmp_path):
    err = ComparisonError("earth_engine_quota_exceeded", "quota", "later", retryable=True)
    svc, client = make_service(tmp_path, client=FakeClient(error=err, delay=0.2))
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        futs = [pool.submit(svc.compare, body()) for _ in range(4)]
    codes = [f.exception().code for f in futs]
    assert codes == ["earth_engine_quota_exceeded"] * 4 and svc._flights == {}


# ------------------------------------------------------------------------------- rate limit and status
def test_rate_limit_is_per_client_and_reports_retry_after(tmp_path):
    svc, _ = make_service(tmp_path, rate_limit_requests=2, rate_limit_window_s=60)
    svc.check_rate_limit("1.2.3.4"); svc.check_rate_limit("1.2.3.4")
    with pytest.raises(RateLimited) as e:
        svc.check_rate_limit("1.2.3.4")
    assert e.value.code == "rate_limited" and e.value.retry_after >= 1 and API_HTTP_STATUS["rate_limited"] == 429
    svc.check_rate_limit("5.6.7.8")                                  # other clients are unaffected


def test_status_never_claims_health_from_configuration_alone(tmp_path):
    svc, client = make_service(tmp_path)
    s = svc.status()
    assert s["configured"] is True and s["earthEngine"]["status"] == "configured_unverified"
    assert s["earthEngine"]["liveVerifiedByThisProcess"] is False and s["configuration"]["credentialsChecked"] is False
    assert s["supportedVariables"] == ["ndvi"] and s["supportedYearRange"] == {"start": 2010, "end": 2024}
    assert s["radiusKm"]["min"] == 1.0 and s["radiusKm"]["max"] == 25.0 and client.calls == []
    assert s["cache"]["accessible"] is True and s["cache"]["entryCount"] == 0
    svc.compare(body())
    assert svc.status()["earthEngine"]["status"] == "last_request_succeeded"
    assert svc.status()["cache"]["entryCount"] == 2


def test_status_reports_failures_and_missing_configuration(tmp_path):
    svc, _ = make_service(tmp_path, client=FakeClient(error=ComparisonError("earth_engine_auth_failed", "x", "y")))
    with pytest.raises(ComparisonError):
        svc.compare(body())
    st = svc.status()["earthEngine"]
    assert st["status"] == "last_request_failed" and st["lastErrorCode"] == "earth_engine_auth_failed"
    bare = LocationComparisonService(api_settings(tmp_path / "x"), client_factory=lambda: None, ee_project=None, package_check=lambda: True)
    assert bare.status()["configured"] is False and bare.status()["earthEngine"]["status"] == "not_configured"
    nopkg = LocationComparisonService(api_settings(tmp_path / "y"), client_factory=lambda: None, ee_project="p", package_check=lambda: False)
    assert nopkg.status()["earthEngine"]["status"] == "not_configured"


def test_status_exposes_no_secrets_or_paths(tmp_path):
    text = repr(make_service(tmp_path)[0].status())
    assert str(tmp_path) not in text and "comparison.sqlite" not in text and "token" not in text.lower()


# ----------------------------------------------------- end-to-end plumbing with the real Phase 2 client
def test_with_real_earth_engine_client_and_mocked_ee_module(tmp_path):
    raw = {"total_pixels": 5000, "water_pixels": 0, "years": [
        {"year": y, "n_images": 4, "ndvi_mean": 0.31 + (y - 2010) / 100, "valid_pixels": 4400, "mean_composites": 3.2,
         "snow_fraction": 0.0, "cloud_fraction": 0.1} for y in (2010, 2011)]}
    ee = MagicMock(name="ee"); ee.__version__ = "0.0-test"
    ee.Dictionary.return_value.combine.return_value.getInfo.return_value = raw
    real = EarthEngineClient(ComparisonSettings(ee_project="test-project", ee_timeout_s=5.0, ee_max_concurrent=2, ee_queue_wait_s=1.0),
                             ee_module=ee, adc_loader=lambda scopes: ("CREDS", "p"))
    svc = LocationComparisonService(api_settings(tmp_path), client_factory=lambda: real, ee_project="test-project",
                                    package_check=lambda: True)
    r = svc.compare(body(endYear=2011))
    assert r["resultStatus"] == "complete" and r["locationA"]["observations"][0]["value"] == 0.31
    assert r["locationA"]["earthEngineApiVersion"] == "0.0-test"
    ee.Initialize.assert_called_once()                              # authentication happened once, server side

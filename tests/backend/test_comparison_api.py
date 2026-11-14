"""Phase 3: HTTP layer (FastAPI TestClient) with a MOCKED Earth Engine client and temporary databases.

Needs fastapi + httpx (backend/requirements.txt). Skipped, not failed, where they are not installed."""
import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.config import Settings
from app.main import create_app
from app.services.comparison_errors import ComparisonError
from comparison_fakes import FakeClient, body, make_service

ROOT = Path(__file__).resolve().parents[2]
ERROR_KEYS = {"code", "message", "hint"}


def make_client(tmp_path, client=None, **kw):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "metadata", data / "metadata")
    (data / "processed").mkdir(parents=True); (data / "demo").mkdir()
    app = create_app(Settings(data_dir=data, demo_mode=False, cors_origins=("http://localhost:5173",)))
    svc, fake = make_service(tmp_path, client=client, **kw)
    app.state.comparison_service = svc
    return TestClient(app), fake


def assert_error(r, status, code):
    assert r.status_code == status, r.text
    j = r.json()
    assert set(j) == {"error"} and set(j["error"]) == ERROR_KEYS and j["error"]["code"] == code
    assert "Traceback" not in r.text and "site-packages" not in r.text


def test_valid_request_returns_typed_camelcase_response(tmp_path):
    c, fake = make_client(tmp_path)
    r = c.post("/api/compare-locations", json=body())
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["dataStatus"] == "live" and j["resultStatus"] == "complete" and j["isSynthetic"] is False
    assert j["locationA"]["observations"][0]["qualityStatus"] == "valid"
    assert {"datasetId", "processingVersion", "retrievedAt"} <= set(j["provenance"])
    assert c.post("/api/compare-locations", json=body()).json()["dataStatus"] == "cached"
    assert len(fake.calls) == 2


def test_no_usable_data_is_http_200(tmp_path):
    from comparison_fakes import raw_payload
    c, _ = make_client(tmp_path, client=FakeClient(payload=lambda req: raw_payload(req, water=4900)))
    r = c.post("/api/compare-locations", json=body())
    assert r.status_code == 200 and r.json()["resultStatus"] == "no_usable_data"
    assert all(o["value"] is None for o in r.json()["locationA"]["observations"])


@pytest.mark.parametrize("payload,code", [
    (body(locationA={"latitude": 95, "longitude": 0}), "invalid_coordinates"),
    (body(radiusKm=100), "invalid_radius"), (body(startYear=2020, endYear=2012), "invalid_year_range"),
    (body(variable="rainfall"), "unsupported_variable"),
    (body(locationB={"latitude": 30.0444, "longitude": 31.2357}), "identical_locations"),
    ({"locationA": {}}, "invalid_request"), ([1, 2], "invalid_request"),
])
def test_invalid_input_error_format(tmp_path, payload, code):
    c, fake = make_client(tmp_path)
    assert_error(c.post("/api/compare-locations", json=payload), 422, code)
    assert fake.calls == []


def test_malformed_json_and_oversized_body(tmp_path):
    c, _ = make_client(tmp_path)
    assert_error(c.post("/api/compare-locations", content=b"{not json", headers={"content-type": "application/json"}), 400, "invalid_json")
    assert_error(c.post("/api/compare-locations", content=b"[" + b"1," * 10000 + b"1]", headers={"content-type": "application/json"}), 413, "request_too_large")


@pytest.mark.parametrize("code,status", [
    ("earth_engine_not_configured", 503), ("earth_engine_auth_failed", 503), ("earth_engine_timeout", 504),
    ("earth_engine_quota_exceeded", 429), ("earth_engine_busy", 429), ("earth_engine_bad_response", 502),
])
def test_provider_failures_map_to_http_statuses(tmp_path, code, status):
    c, _ = make_client(tmp_path, client=FakeClient(error=ComparisonError(code, "msg", "hint", retryable=status in (429, 504))))
    assert_error(c.post("/api/compare-locations", json=body()), status, code)


def test_unexpected_failure_is_a_clean_500(tmp_path):
    c, _ = make_client(tmp_path, client=FakeClient(error=RuntimeError("C:\\secret\\token.json")))
    r = c.post("/api/compare-locations", json=body())
    assert_error(r, 500, "internal_error")
    assert "secret" not in r.text


def test_rate_limit_returns_429_with_retry_after(tmp_path):
    c, _ = make_client(tmp_path, rate_limit_requests=2)
    assert c.post("/api/compare-locations", json=body()).status_code == 200
    assert c.post("/api/compare-locations", json=body()).status_code == 200
    r = c.post("/api/compare-locations", json=body())
    assert_error(r, 429, "rate_limited")
    assert int(r.headers["retry-after"]) >= 1


def test_forwarded_for_is_ignored_unless_trusted(tmp_path):
    c, _ = make_client(tmp_path, rate_limit_requests=1)
    assert c.post("/api/compare-locations", json=body(), headers={"x-forwarded-for": "9.9.9.1"}).status_code == 200
    assert c.post("/api/compare-locations", json=body(), headers={"x-forwarded-for": "9.9.9.2"}).status_code == 429   # spoofing does not help


def test_status_endpoint(tmp_path):
    c, fake = make_client(tmp_path)
    j = c.get("/api/comparison/status").json()
    assert j["earthEngine"]["status"] == "configured_unverified" and j["supportedVariables"] == ["ndvi"]
    assert j["cache"]["accessible"] is True and fake.calls == []
    assert "token" not in c.get("/api/comparison/status").text.lower()


def test_cors_allows_post_from_the_configured_origin(tmp_path):
    c, _ = make_client(tmp_path)
    r = c.options("/api/compare-locations", headers={"origin": "http://localhost:5173", "access-control-request-method": "POST",
                                                     "access-control-request-headers": "content-type"})
    assert r.status_code == 200 and "POST" in r.headers["access-control-allow-methods"]
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_existing_routes_still_work_and_openapi_builds(tmp_path):
    c, _ = make_client(tmp_path)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/variables").status_code == 200
    assert_error(c.get("/api/timeseries"), 422, "invalid_parameters")  # existing validation handler unchanged
    paths = c.get("/openapi.json").json()["paths"]
    for p in ("/api/health", "/api/locations", "/api/variables", "/api/scenarios", "/api/timeseries", "/api/climate",
              "/api/imagery/metadata", "/api/provenance", "/api/compare-locations", "/api/comparison/status"):
        assert p in paths

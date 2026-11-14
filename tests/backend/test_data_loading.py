"""Regression tests for the Time Travel data-loading bugs (Windows encoding, health diagnostics, observed-only mode).

The POWER payload below is a TEST FIXTURE with made-up numbers; it is never used by the app.
"""
import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.builders import build_observed_dataset

ROOT = Path(__file__).resolve().parents[2]


def _power_payload(first=1981, last=2025):
    t2m = {}
    for y in range(first, last + 1):
        for m in range(1, 13):
            t2m[f"{y}{m:02d}"] = 15.0 + 10.0 * (1 if 5 <= m <= 9 else 0) + 0.02 * (y - first)
        t2m[f"{y}13"] = 20.0
    t2m["202601"] = -999.0  # partial current year: must be withheld, not averaged
    return {"header": {"api": {"version": "v2.x"}, "title": "fixture", "fill_value": -999.0, "sources": []},
            "parameters": {"T2M": {"units": "C", "longname": "Temperature at 2 Meters"}},
            "properties": {"parameter": {"T2M": t2m}}}


def _client(tmp_path, observed_bytes=None):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "metadata", data / "metadata")
    (data / "processed").mkdir(parents=True)
    if observed_bytes is not None:
        (data / "processed" / "cairo__air_temperature__observed.json").write_bytes(observed_bytes)
    return TestClient(create_app(Settings(data_dir=data, demo_mode=False, cors_origins=("http://localhost:5173",))))


def _observed_json():
    ds = build_observed_dataset(_power_payload(), location_id="cairo", variable_id="air_temperature",
                                lat=30.0444, lon=31.2357, request_url="fixture")
    return ds.model_dump_json(indent=1)


def test_observed_file_written_with_windows_ansi_codepage_still_loads(tmp_path):
    text = _observed_json()
    assert "°" in text
    c = _client(tmp_path, text.encode("cp1252"))  # what the old script produced on Windows
    r = c.get("/api/timeseries", params={"location": "cairo", "variable": "air_temperature"})
    assert r.status_code == 200, r.text
    assert r.json()["latest_complete_year"] == 2025
    assert r.json()["dataset"]["unit"] == "°C"


def test_observed_file_utf8_loads(tmp_path):
    c = _client(tmp_path, _observed_json().encode("utf-8"))
    assert c.get("/api/timeseries", params={"location": "cairo"}).status_code == 200


def test_observed_loads_while_projection_is_unavailable(tmp_path):
    c = _client(tmp_path, _observed_json().encode("utf-8"))
    assert c.get("/api/timeseries", params={"location": "cairo"}).status_code == 200
    r = c.get("/api/climate", params={"location": "cairo"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "dataset_not_available"
    prov = c.get("/api/provenance", params={"location": "cairo"}).json()
    assert [d["kind"] for d in prov["datasets"]] == ["observed"]
    assert [u["kind"] for u in prov["unavailable"]] == ["projection"]


def test_health_reports_which_data_folder_is_read(tmp_path):
    c = _client(tmp_path)
    j = c.get("/api/health").json()
    assert j["data_dir"].endswith("data")
    assert j["processed_files"]["cairo__air_temperature__observed.json"]["exists"] is False
    (tmp_path / "data" / "processed" / "cairo__air_temperature__observed.json").write_text(_observed_json(), encoding="utf-8")
    j = c.get("/api/health").json()
    assert j["processed_files"]["cairo__air_temperature__observed.json"]["exists"] is True
    assert j["locations"]["cairo"] == "configured"


def test_aswan_is_configured_with_its_own_series(tmp_path):
    c = _client(tmp_path)
    locs = {l["id"]: l for l in c.get("/api/locations").json()}
    assert locs["aswan"]["status"] == "primary_mvp"
    assert abs(locs["aswan"]["latitude"] - 24.0889) < 1e-3 and abs(locs["aswan"]["longitude"] - 32.8998) < 1e-3
    assert locs["aswan"]["dataset_status"] == "data_not_fetched"      # honest until fetched
    assert c.get("/api/timeseries", params={"location": "aswan"}).status_code == 503
    # Fixture data (test only) written for Aswan only must be served for Aswan and never for Cairo.
    ds = build_observed_dataset(_power_payload(), location_id="aswan", variable_id="air_temperature",
                                lat=24.0889, lon=32.8998, request_url="fixture")
    (tmp_path / "data" / "processed" / "aswan__air_temperature__observed.json").write_text(ds.model_dump_json(), encoding="utf-8")
    assert c.get("/api/timeseries", params={"location": "aswan"}).json()["dataset"]["location_id"] == "aswan"
    assert c.get("/api/timeseries", params={"location": "cairo"}).status_code == 503

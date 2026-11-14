import shutil
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def client(tmp_path, demo, with_demo_files=True):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "metadata", data / "metadata")
    (data / "processed").mkdir(parents=True); (data / "demo").mkdir()
    if with_demo_files:
        for f in (ROOT / "data" / "demo").glob("*.json"):
            shutil.copy(f, data / "demo" / f.name)
    return TestClient(create_app(Settings(data_dir=data, demo_mode=demo, cors_origins=("http://localhost:5173",))))

def test_no_data_means_honest_error_not_fake_values(tmp_path):
    c = client(tmp_path, demo=False)
    r = c.get("/api/timeseries", params={"location": "cairo"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "dataset_not_available"
    assert c.get("/api/climate", params={"location": "cairo"}).status_code == 503
    locs = {l["id"]: l for l in c.get("/api/locations").json()}
    assert locs["cairo"]["dataset_status"] == "data_not_fetched"
    assert locs["greenland"]["dataset_status"] == "not_configured"

def test_other_locations_never_get_cairo_data(tmp_path):
    c = client(tmp_path, demo=True)
    for loc in ("greenland", "amazon"):
        r = c.get("/api/timeseries", params={"location": loc, "variable": "air_temperature"})
        assert r.status_code == 501 and r.json()["error"]["code"] == "dataset_not_configured"

def test_demo_mode_flags_everything(tmp_path):
    c = client(tmp_path, demo=True)
    r = c.get("/api/timeseries", params={"location": "cairo", "start_year": 2000, "end_year": 2010})
    assert r.status_code == 200
    j = r.json()
    assert j["dataset"]["is_demo"] and j["dataset"]["record_type"] == "synthetic_demo"
    assert [x["year"] for x in j["dataset"]["records"]] == list(range(2000, 2011))
    assert j["latest_complete_year"] == 2010
    assert c.get("/api/health").json()["demo_mode"] is True
    assert c.get("/api/locations").json()[0]["dataset_status"] == "demo_only"

def test_demo_files_ignored_when_demo_off(tmp_path):
    c = client(tmp_path, demo=False)
    assert c.get("/api/timeseries", params={"location": "cairo"}).status_code == 503

def test_processed_dir_rejects_synthetic(tmp_path):
    c = client(tmp_path, demo=False)
    shutil.copy(ROOT / "data" / "demo" / "cairo__air_temperature__observed.json",
                tmp_path / "data" / "processed" / "cairo__air_temperature__observed.json")
    r = c.get("/api/timeseries", params={"location": "cairo"})
    assert r.status_code == 500 and r.json()["error"]["code"] == "dataset_invalid"

def test_climate_scenario_filter_and_validation(tmp_path):
    c = client(tmp_path, demo=True)
    j = c.get("/api/climate", params={"location": "cairo", "scenario": "ssp585"}).json()
    assert {e["scenario"] for e in j["dataset"]["ensemble"]} == {"ssp585"}
    assert "not predictions" in j["disclaimer"]
    assert c.get("/api/climate", params={"location": "cairo", "scenario": "ssp999"}).status_code == 404
    assert c.get("/api/climate", params={"location": "cairo", "model": "nope"}).status_code == 404
    assert c.get("/api/climate", params={"location": "BAD LOC!"}).status_code == 422
    assert c.get("/api/timeseries", params={"location": "cairo", "start_year": 2020, "end_year": 2010}).status_code == 422

def test_imagery_availability(tmp_path):
    c = client(tmp_path, demo=False)
    j = c.get("/api/imagery/metadata", params={"location": "cairo", "year": 1995}).json()
    assert j["availability"]["modis_terra_truecolor"]["available"] is False
    j = c.get("/api/imagery/metadata", params={"location": "cairo", "year": 2010}).json()
    assert j["availability"]["modis_terra_truecolor"] == {"available": True, "date": "2010-07-15", "reason": None}
    j = c.get("/api/imagery/metadata", params={"location": "cairo", "year": 2100}).json()
    assert j["availability"]["modis_terra_truecolor"]["available"] is False
    assert j["layers"][0]["verified_in_build_environment"] is False

def test_provenance_and_unknowns(tmp_path):
    c = client(tmp_path, demo=True)
    j = c.get("/api/provenance", params={"location": "cairo"}).json()
    assert len(j["datasets"]) == 2 and "records" not in j["datasets"][0]
    assert c.get("/api/provenance", params={"location": "atlantis"}).status_code == 404
    assert c.get("/api/scenarios").json()["scenarios"][0]["label"] == "SSP2-4.5"

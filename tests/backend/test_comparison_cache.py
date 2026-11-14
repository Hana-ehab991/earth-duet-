"""Phase 3: SQLite cache behaviour. Uses temporary databases only; no Earth Engine, no network."""
import json
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.services import ndvi_processing as P
from app.services.comparison_cache import CACHE_SCHEMA_VERSION, ComparisonCache, build_key
from app.services.comparison_validation import RegionRequest, validate_region_request
from comparison_fakes import raw_payload

REQ = RegionRequest(30.0444, 31.2357, 10.0, 2010, 2013, "ndvi")


def result_for(req, **kw):
    return P.process_region(raw_payload(req, **kw), req, "2026-11-13T00:00:00+00:00", "fake-ee-0")


def cache(tmp_path, ttl=30.0, clock=None):
    return ComparisonCache(tmp_path / "c.sqlite", ttl_days=ttl, **({"clock": clock} if clock else {}))


def test_miss_then_hit_round_trips_everything(tmp_path):
    c = cache(tmp_path)
    assert c.get(REQ) is None
    res = result_for(REQ)
    assert c.put(REQ, res) is not None
    hit = c.get(REQ)
    assert hit is not None and hit.result == res and hit.retrieved_at == res.retrieved_at


def test_persists_across_instances(tmp_path):
    res = result_for(REQ)
    cache(tmp_path).put(REQ, res)
    assert cache(tmp_path).get(REQ).result == res


def test_key_changes_with_every_scientific_parameter(tmp_path, monkeypatch):
    base = build_key(REQ).key
    variants = {
        "lat": RegionRequest(30.0445, 31.2357, 10.0, 2010, 2013, "ndvi"),
        "lon": RegionRequest(30.0444, 31.2358, 10.0, 2010, 2013, "ndvi"),
        "radius": RegionRequest(30.0444, 31.2357, 11.0, 2010, 2013, "ndvi"),
        "start": RegionRequest(30.0444, 31.2357, 10.0, 2011, 2013, "ndvi"),
        "end": RegionRequest(30.0444, 31.2357, 10.0, 2010, 2014, "ndvi"),
    }
    keys = {n: build_key(r).key for n, r in variants.items()}
    assert base not in keys.values() and len(set(keys.values())) == len(keys)
    for attr, value in [("PROCESSING_VERSION", "ndvi-annual-v2"), ("SEASON_END_EXCLUSIVE_MD", "06-15"),
                        ("MIN_VALID_PIXEL_FRACTION", 0.7), ("SCALE_FACTOR", 0.0002), ("NOMINAL_SCALE_M", 500),
                        ("DATASET_VERSION", "062"), ("DQA_EXCLUDED_BITS", (8, 10, 14)), ("WATER_FLAGS", (0, 3))]:
        with monkeypatch.context() as m:
            m.setattr(P, attr, value)
            assert build_key(REQ).key != base, attr


def test_processing_change_is_a_miss(tmp_path, monkeypatch):
    c = cache(tmp_path)
    c.put(REQ, result_for(REQ))
    with monkeypatch.context() as m:
        m.setattr(P, "MIN_MEAN_VALID_COMPOSITES", 3.0)
        assert c.get(REQ) is None
    assert c.get(REQ) is not None


def test_canonical_coordinates_do_not_merge_distinct_regions():
    same_a = validate_region_request(30.04441, 31.23574, 10, 2010, 2013)   # both round to 30.0444 / 31.2357
    same_b = validate_region_request(30.04444, 31.23566, 10, 2010, 2013)
    other = validate_region_request(30.0445, 31.2357, 10, 2010, 2013)       # 0.0001 deg (~11 m) away
    assert build_key(same_a).key == build_key(same_b).key
    assert build_key(other).key != build_key(same_a).key
    z1, z2 = validate_region_request(-0.0, 0.0, 10, 2010, 2013), validate_region_request(0.0, -0.0, 10, 2010, 2013)
    assert build_key(z1).key == build_key(z2).key
    assert json.loads(build_key(z1).canonical_json)["latitude"] == "0.0000"


def test_non_canonical_request_is_refused():
    with pytest.raises(ValueError):
        build_key(RegionRequest(30.04441, 31.2357, 10.0, 2010, 2013, "ndvi"))


def test_canonical_coordinates_are_stored_in_metadata_columns(tmp_path):
    c = cache(tmp_path)
    c.put(REQ, result_for(REQ))
    row = sqlite3.connect(tmp_path / "c.sqlite").execute(
        "SELECT latitude, longitude, radius_km, start_year, end_year, season_start, season_end_exclusive, dataset_id, "
        "dataset_version, config_fingerprint, processing_version, origin, canonical_params FROM region_results").fetchone()
    assert row[:12] == ("30.0444", "31.2357", "10.000", 2010, 2013, "04-01", "06-01", "MODIS/061/MOD13Q1", "061",
                        P.qa_config_fingerprint(), P.PROCESSING_VERSION, "earth_engine")
    assert json.loads(row[12])["latitude"] == "30.0444"


def test_expiry(tmp_path):
    now = [1_000_000.0]
    c = cache(tmp_path, ttl=30.0, clock=lambda: now[0])
    c.put(REQ, result_for(REQ))
    now[0] += 29 * 86400
    assert c.get(REQ) is not None
    now[0] += 2 * 86400
    assert c.get(REQ) is None


def test_ttl_zero_disables_cache_and_creates_no_file(tmp_path):
    c = cache(tmp_path, ttl=0)
    assert not c.enabled and c.put(REQ, result_for(REQ)) is None and c.get(REQ) is None
    assert not (tmp_path / "c.sqlite").exists()


def test_corrupted_payload_is_discarded_not_trusted(tmp_path):
    c = cache(tmp_path)
    c.put(REQ, result_for(REQ))
    db = sqlite3.connect(tmp_path / "c.sqlite")
    db.execute("UPDATE region_results SET payload = substr(payload, 1, 40)")
    db.commit()
    assert c.get(REQ) is None
    assert db.execute("SELECT count(*) FROM region_results").fetchone()[0] == 0     # bad row removed


def test_tampered_value_with_valid_json_fails_checksum(tmp_path):
    c = cache(tmp_path)
    res = result_for(REQ)
    c.put(REQ, res)
    db = sqlite3.connect(tmp_path / "c.sqlite")
    payload = db.execute("SELECT payload FROM region_results").fetchone()[0]
    d = json.loads(payload)
    d["annual"][0]["value"] = 0.99
    db.execute("UPDATE region_results SET payload = ?", (json.dumps(d),))
    db.commit()
    assert c.get(REQ) is None


def test_checksum_valid_but_physically_impossible_value_is_rejected(tmp_path):
    c = cache(tmp_path)
    c.put(REQ, result_for(REQ))
    db = sqlite3.connect(tmp_path / "c.sqlite")
    import hashlib
    d = json.loads(db.execute("SELECT payload FROM region_results").fetchone()[0])
    d["annual"][0]["value"] = 7.0                       # outside -0.2..1.0
    p = json.dumps(d)
    db.execute("UPDATE region_results SET payload = ?, payload_sha256 = ?", (p, hashlib.sha256(p.encode()).hexdigest()))
    db.commit()
    assert c.get(REQ) is None


def test_demo_origin_cannot_be_stored(tmp_path):
    c = cache(tmp_path)
    c.put(REQ, result_for(REQ))
    db = sqlite3.connect(tmp_path / "c.sqlite")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE region_results SET origin = 'synthetic_demo'")


def test_garbage_database_file_never_breaks_callers(tmp_path):
    (tmp_path / "c.sqlite").write_bytes(b"this is not a sqlite database" * 50)
    c = cache(tmp_path)
    assert c.get(REQ) is None
    assert c.put(REQ, result_for(REQ)) is None          # not stored, no exception
    assert c.status()["accessible"] is False
    assert c.last_error is not None and str(tmp_path) not in c.last_error


def test_put_refuses_mismatched_result(tmp_path):
    other = RegionRequest(10.0, 10.0, 10.0, 2010, 2013, "ndvi")
    with pytest.raises(ValueError):
        cache(tmp_path).put(REQ, result_for(other))


def test_parameterized_sql_survives_hostile_values(tmp_path):
    c = cache(tmp_path)
    c.put(REQ, result_for(REQ))
    # Keys are hashes and every statement binds its values; make sure the table is intact after odd inputs.
    c._delete("x'; DROP TABLE region_results; --")
    assert c.get(REQ) is not None


def test_concurrent_writers_and_readers_share_one_database(tmp_path):
    c = cache(tmp_path)
    reqs = [RegionRequest(10.0 + i, 20.0, 10.0, 2010, 2013, "ndvi") for i in range(12)]
    errors = []

    def work(r):
        try:
            for _ in range(3):
                c.put(r, result_for(r))
                assert c.get(r) is not None
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=work, args=(r,)) for r in reqs]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    assert cache(tmp_path).status()["entryCount"] == 12


def test_status_does_not_create_the_database(tmp_path):
    c = cache(tmp_path / "nested")
    s = c.status()
    assert s["accessible"] is True and s["entryCount"] == 0 and not (tmp_path / "nested").exists()
    assert s["schemaVersion"] == CACHE_SCHEMA_VERSION

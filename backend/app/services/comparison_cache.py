"""Persistent SQLite cache of validated per-location NDVI results (stdlib sqlite3 only).

Design
------
* One row per LOCATION (region), not per comparison pair. A and B are processed independently with identical
  settings, so a location is reused by any later comparison that asks for the same scientific parameters.
* The key is a SHA-256 over canonical JSON of every scientifically meaningful parameter (see `build_key`). Changing
  any of them (dataset/version, variable, canonical coordinates, radius, years, season, QA/aggregation fingerprint,
  processing version, cache schema) yields a different key, i.e. a cache miss.
* Only results that came from Earth Engine and passed Phase 2 validation are stored (`origin` is constrained to
  'earth_engine' by the table itself). Errors are never stored. There is no demo path.
* Every read re-verifies the row (checksum, expiry, origin, schema version, canonical parameters, structure and
  physical range of the values). A row that fails is deleted and treated as a miss.
* Cache problems never break a comparison: an unreadable/corrupt/locked database means "miss" and "not stored".
* Concurrency: WAL mode, a short-lived connection per operation, a busy timeout, one IMMEDIATE transaction per write.
  This is safe across threads and across several worker processes sharing the file.
* Nothing credential-like is stored.

Coordinate precision
--------------------
Coordinates are rounded to 4 decimal places (comparison_validation.COORD_DECIMALS) BEFORE the region is queried,
reported or cached: 0.0001 deg is about 11.1 m in latitude (and 11.1 m x cos(latitude) in longitude), versus a
source pixel of about 231.7 m. The rounded value is what Earth Engine analyses, so two requests share a cache entry
only if they analyse exactly the same circle. The key uses fixed-decimal strings (never float repr) and -0.0 is
normalised to 0.0. The canonical coordinates are stored in their own columns and in `canonical_params`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from . import ndvi_processing as P
from .comparison_validation import COORD_DECIMALS, RegionRequest

log = logging.getLogger("earth_duet.comparison_cache")

CACHE_SCHEMA_VERSION = 1
ORIGIN_EARTH_ENGINE = "earth_engine"
_STATUSES = {"ok", "warning", "unsuitable", "unavailable"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS region_results (
    cache_key            TEXT PRIMARY KEY,
    cache_schema_version INTEGER NOT NULL,
    dataset_id           TEXT NOT NULL,
    dataset_version      TEXT NOT NULL,
    variable             TEXT NOT NULL,
    latitude             TEXT NOT NULL,      -- canonical (rounded) coordinates, fixed decimals
    longitude            TEXT NOT NULL,
    radius_km            TEXT NOT NULL,
    start_year           INTEGER NOT NULL,
    end_year             INTEGER NOT NULL,
    season_start         TEXT NOT NULL,
    season_end_exclusive TEXT NOT NULL,
    config_fingerprint   TEXT NOT NULL,
    processing_version   TEXT NOT NULL,
    canonical_params     TEXT NOT NULL,      -- the exact JSON that was hashed into cache_key
    payload              TEXT NOT NULL,      -- serialized NdviRegionResult (JSON)
    payload_sha256       TEXT NOT NULL,
    origin               TEXT NOT NULL CHECK (origin = 'earth_engine'),
    retrieved_at         TEXT NOT NULL,      -- when Earth Engine was queried (ISO 8601 UTC)
    earth_engine_api_version TEXT,
    created_at           REAL NOT NULL,      -- unix seconds
    expires_at           REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_region_results_expires ON region_results (expires_at);
CREATE INDEX IF NOT EXISTS idx_region_results_params
    ON region_results (dataset_id, variable, latitude, longitude, radius_km, start_year, end_year);
"""


class _Corrupt(Exception):
    """A cache row failed verification."""


@dataclass(frozen=True)
class CacheKey:
    key: str
    params: dict
    canonical_json: str


@dataclass(frozen=True)
class CachedRegion:
    result: P.NdviRegionResult
    key: str
    retrieved_at: str
    expires_at: float


def _fixed(x: float, decimals: int) -> str:
    return f"{x + 0.0:.{decimals}f}"          # `+ 0.0` turns -0.0 into 0.0


def build_key(req: RegionRequest) -> CacheKey:
    """Deterministic key for one region request. `req` must already be validated/canonical (Phase 2 rounding)."""
    if (round(req.latitude, COORD_DECIMALS) != req.latitude or round(req.longitude, COORD_DECIMALS) != req.longitude
            or round(req.radius_km, 3) != req.radius_km):
        raise ValueError("RegionRequest is not canonical; run it through validate_region_request first.")
    params = {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "dataset_id": P.DATASET_ID, "dataset_version": P.DATASET_VERSION,
        "variable": req.variable,
        "latitude": _fixed(req.latitude, COORD_DECIMALS), "longitude": _fixed(req.longitude, COORD_DECIMALS),
        "coordinate_decimals": COORD_DECIMALS,
        "radius_km": _fixed(req.radius_km, 3),
        "start_year": req.start_year, "end_year": req.end_year,
        "season_start": P.SEASON_START_MD, "season_end_exclusive": P.SEASON_END_EXCLUSIVE_MD,
        "config_fingerprint": P.qa_config_fingerprint(),   # QA filtering, scale factor, thresholds, spatial scale
        "processing_version": P.PROCESSING_VERSION,
    }
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return CacheKey(hashlib.sha256(canonical.encode()).hexdigest(), params, canonical)


# ------------------------------------------------------------------------------------------ serialization
def encode_result(result: P.NdviRegionResult) -> str:
    return json.dumps(asdict(result), sort_keys=True, allow_nan=False, separators=(",", ":"))


def _opt_num(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise _Corrupt("bad number")
    return float(x)


def decode_result(payload: str, expected: RegionRequest) -> P.NdviRegionResult:
    """Rebuild an NdviRegionResult, verifying structure and physical plausibility. Raises _Corrupt otherwise."""
    try:
        d = json.loads(payload)
        r = d["request"]
        req = RegionRequest(float(r["latitude"]), float(r["longitude"]), float(r["radius_km"]),
                            int(r["start_year"]), int(r["end_year"]), str(r["variable"]))
        if req != expected:
            raise _Corrupt("stored request differs from key")
        annual = []
        for a in d["annual"]:
            value = _opt_num(a["value"])
            reason_code = a["reason_code"]
            if (value is None) == (reason_code is None):
                raise _Corrupt("value/reason inconsistent")
            if value is not None and not (P.NDVI_MIN - 1e-6 <= value <= P.NDVI_MAX + 1e-6):
                raise _Corrupt("NDVI outside physical range")
            if reason_code is not None and reason_code not in P.REASON_TEXT:
                raise _Corrupt("unknown reason code")
            annual.append(P.AnnualNdvi(int(a["year"]), value, reason_code, a["reason"], int(a["n_composites"]),
                                       _opt_num(a["valid_pixel_fraction"]), _opt_num(a["mean_valid_composites"]),
                                       _opt_num(a["snow_flag_fraction"]), _opt_num(a["cloud_flag_fraction"])))
        if [a.year for a in annual] != list(range(req.start_year, req.end_year + 1)):
            raise _Corrupt("years do not cover the requested range")
        s = d["suitability"]
        if s["status"] not in _STATUSES:
            raise _Corrupt("bad suitability status")
        suit = P.RegionSuitability(s["status"], tuple(P.SuitabilityWarning(str(w["code"]), str(w["message"]))
                                                      for w in s["warnings"]), _opt_num(s["water_fraction"]))
        meth = d["methodology"]
        if (not isinstance(meth, dict) or meth.get("processing_version") != P.PROCESSING_VERSION
                or meth.get("config_fingerprint") != P.qa_config_fingerprint()):
            raise _Corrupt("methodology does not match the current processing")
        if not isinstance(d["retrieved_at"], str):
            raise _Corrupt("bad timestamp")
        total, water = int(d["total_pixels"]), int(d["water_pixels"])
        if total < 0 or water < 0 or water > total:
            raise _Corrupt("bad pixel counts")
        ee_v = d.get("earth_engine_api_version")
        return P.NdviRegionResult(req, tuple(annual), suit, total, water, d["retrieved_at"], meth,
                                  None if ee_v is None else str(ee_v))
    except _Corrupt:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise _Corrupt(f"{type(e).__name__}") from None


# ------------------------------------------------------------------------------------------------ cache
class ComparisonCache:
    """Thread- and process-safe persistent cache. The database file is created lazily on first use."""

    def __init__(self, path: Path | str, ttl_days: float = 30.0, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.ttl_seconds = max(0.0, float(ttl_days)) * 86400.0
        self._clock = clock
        self._init_lock = threading.Lock()
        self._ready = False
        self.last_error: Optional[str] = None      # exception class name only; never paths or messages

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0

    # -- plumbing ----------------------------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30.0, isolation_level=None)   # autocommit; explicit BEGIN
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _ensure(self) -> None:
        if self._ready:
            return
        with self._init_lock:
            if self._ready:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as c:
                c.execute("PRAGMA journal_mode = WAL")
                c.executescript(_SCHEMA)
                c.execute("SELECT count(*) FROM region_results").fetchone()   # fails fast on a corrupt file
            self._ready = True

    def _fail(self, exc: BaseException) -> None:
        self.last_error = type(exc).__name__
        log.warning("comparison cache unavailable (%s); continuing without it", self.last_error)

    build_key = staticmethod(build_key)

    # -- operations --------------------------------------------------------------------------------------
    def get(self, req: RegionRequest) -> Optional[CachedRegion]:
        """Return a verified, unexpired entry, or None (miss). Never raises for cache problems."""
        if not self.enabled:
            return None
        key = build_key(req)
        try:
            self._ensure()
            with closing(self._connect()) as c:
                row = c.execute(
                    "SELECT payload, payload_sha256, origin, retrieved_at, expires_at, canonical_params, "
                    "cache_schema_version FROM region_results WHERE cache_key = ?", (key.key,)).fetchone()
        except (sqlite3.Error, OSError) as e:
            self._fail(e)
            return None
        if row is None:
            return None
        payload, sha, origin, retrieved_at, expires_at, canonical, schema_v = row
        if not isinstance(expires_at, (int, float)) or expires_at <= self._clock():
            return None                              # expired: miss (rows are purged on later writes)
        try:
            if origin != ORIGIN_EARTH_ENGINE or schema_v != CACHE_SCHEMA_VERSION or canonical != key.canonical_json:
                raise _Corrupt("metadata mismatch")
            if not isinstance(payload, str) or hashlib.sha256(payload.encode()).hexdigest() != sha:
                raise _Corrupt("checksum mismatch")
            result = decode_result(payload, req)
        except _Corrupt as e:
            log.warning("discarding corrupt comparison cache entry (%s)", e)
            self._delete(key.key)
            return None
        return CachedRegion(result, key.key, str(retrieved_at), float(expires_at))

    def put(self, req: RegionRequest, result: P.NdviRegionResult) -> Optional[CachedRegion]:
        """Store a validated Earth Engine result atomically. Returns the stored entry, or None if not stored."""
        if not self.enabled:
            return None
        if result.request != req:
            raise ValueError("result does not belong to this request")
        key = build_key(req)
        try:
            payload = encode_result(result)
            now = self._clock()
            expires = now + self.ttl_seconds
            p = key.params
            self._ensure()
            with closing(self._connect()) as c:
                c.execute("BEGIN IMMEDIATE")
                try:
                    c.execute("DELETE FROM region_results WHERE expires_at <= ?", (now,))
                    c.execute(
                        "INSERT OR REPLACE INTO region_results (cache_key, cache_schema_version, dataset_id, "
                        "dataset_version, variable, latitude, longitude, radius_km, start_year, end_year, "
                        "season_start, season_end_exclusive, config_fingerprint, processing_version, "
                        "canonical_params, payload, payload_sha256, origin, retrieved_at, earth_engine_api_version, "
                        "created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (key.key, CACHE_SCHEMA_VERSION, p["dataset_id"], p["dataset_version"], p["variable"],
                         p["latitude"], p["longitude"], p["radius_km"], p["start_year"], p["end_year"],
                         p["season_start"], p["season_end_exclusive"], p["config_fingerprint"],
                         p["processing_version"], key.canonical_json, payload,
                         hashlib.sha256(payload.encode()).hexdigest(), ORIGIN_EARTH_ENGINE, result.retrieved_at,
                         result.earth_engine_api_version, now, expires))
                    c.execute("COMMIT")
                except BaseException:
                    c.execute("ROLLBACK")
                    raise
            return CachedRegion(result, key.key, result.retrieved_at, expires)
        except (sqlite3.Error, OSError, ValueError) as e:
            self._fail(e)
            return None

    def _delete(self, cache_key: str) -> None:
        try:
            with closing(self._connect()) as c:
                c.execute("DELETE FROM region_results WHERE cache_key = ?", (cache_key,))
        except (sqlite3.Error, OSError) as e:
            self._fail(e)

    def status(self) -> dict:
        """Cheap, read-only health summary for the status endpoint. Does not create the database file."""
        info: dict[str, Any] = {"enabled": self.enabled, "ttlDays": self.ttl_seconds / 86400.0,
                                "schemaVersion": CACHE_SCHEMA_VERSION, "accessible": False, "entryCount": None}
        if not self.enabled:
            return info
        try:
            if not self.path.exists():
                anc = self.path.parent
                while not anc.exists() and anc != anc.parent:
                    anc = anc.parent
                info["accessible"] = os.access(anc, os.W_OK)     # can be created on first use
                info["entryCount"] = 0
                info["initialized"] = False
                return info
            uri = self.path.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=5.0)) as c:
                info["entryCount"] = c.execute("SELECT count(*) FROM region_results").fetchone()[0]
            info["accessible"], info["initialized"] = True, True
        except (sqlite3.Error, OSError):
            info["accessible"] = False
        return info

"""Orchestration of a two-location NDVI comparison (validation -> cache -> Earth Engine -> response).

All scientific processing lives in Phase 2 (`ndvi_processing`, `earth_engine_service`, `comparison_validation`);
this module only validates input shape, decides cache vs live, and assembles the camelCase response dict.
It never fabricates, interpolates or substitutes values, and never mixes synthetic data with real data
(there is no synthetic path here).

Result semantics (request valid, service healthy):
  resultStatus "complete"        both locations have at least one usable year
  resultStatus "partial_data"    exactly one location has usable years
  resultStatus "no_usable_data"  neither has any (e.g. ocean, persistent cloud/snow): HTTP 200, null observations
HTTP errors are reserved for invalid requests and genuine processing/service failures.
"""
from __future__ import annotations

import concurrent.futures
import importlib.util
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from . import ndvi_processing as P
from .comparison_api_settings import ComparisonApiSettings, get_comparison_api_settings
from .comparison_cache import ComparisonCache
from .comparison_errors import HTTP_STATUS, ComparisonError
from .comparison_settings import get_comparison_settings
from .comparison_validation import (DEFAULT_RADIUS_KM, FIRST_SUPPORTED_YEAR, LAST_SUPPORTED_YEAR, MAX_RADIUS_KM,
                                    MIN_RADIUS_KM, SUPPORTED_VARIABLES, RegionRequest, validate_pair,
                                    validate_region_request)
from .rate_limit import SlidingWindowLimiter

log = logging.getLogger("earth_duet.location_comparison")

#: Phase 2 statuses plus the codes introduced by the API layer.
API_HTTP_STATUS: dict[str, int] = {
    **HTTP_STATUS,
    "invalid_json": 400, "invalid_request": 422, "request_too_large": 413,
    "rate_limited": 429, "internal_error": 500,
}

_ALLOWED_TOP = {"locationA", "locationB", "variable", "startYear", "endYear", "radiusKm"}
_REQUIRED_TOP = ("locationA", "locationB", "startYear", "endYear")
_PATH_RE = re.compile(r"([A-Za-z]:\\[^\s'\"]*|/(?:home|usr|var|mnt|tmp|etc|opt|root|Users|app|srv)/[^\s'\"]*)")


class RateLimited(ComparisonError):
    def __init__(self, retry_after_s: float):
        super().__init__("rate_limited", "Too many comparison requests from this client.",
                         f"Wait about {int(retry_after_s) + 1} seconds and try again.", retryable=True)
        self.retry_after = int(retry_after_s) + 1


@dataclass(frozen=True)
class _Resolved:
    result: P.NdviRegionResult
    status: str                    # "live" | "cached"
    key: Optional[str]
    expires_at: Optional[float]


def _iso(ts: Optional[float]) -> Optional[str]:
    return None if ts is None else datetime.fromtimestamp(ts, timezone.utc).replace(microsecond=0).isoformat()


def _public(err: ComparisonError) -> ComparisonError:
    """Strip anything that could leak internals (file paths, raw provider text) from an error before it is sent."""
    hint = err.hint
    if err.code == "earth_engine_error":
        log.warning("unclassified Earth Engine error detail: %s", hint)
        hint = "An unexpected error occurred at the data provider. The details were logged on the server."
    elif hint:
        hint = _PATH_RE.sub("[path removed]", hint)
    msg = _PATH_RE.sub("[path removed]", err.message)
    if hint == err.hint and msg == err.message:
        return err
    out = ComparisonError(err.code, msg, hint, err.retryable)
    return out


def _has_ee_package() -> bool:
    try:
        return importlib.util.find_spec("ee") is not None
    except (ImportError, ValueError):
        return False


class LocationComparisonService:
    def __init__(self, api_settings: ComparisonApiSettings, cache: Optional[ComparisonCache] = None,
                 client_factory: Optional[Callable[[], Any]] = None, ee_project: Optional[str] = None,
                 package_check: Callable[[], bool] = _has_ee_package, clock: Callable[[], float] | None = None):
        self.api = api_settings
        self.cache = cache or ComparisonCache(api_settings.cache_path, api_settings.cache_ttl_days)
        if client_factory is None:
            from .earth_engine_service import get_client      # no `ee` import happens here
            client_factory = get_client
        self._client_factory = client_factory
        self._ee_project = ee_project if ee_project is not None else get_comparison_settings().ee_project
        self._package_check = package_check
        self._clock = clock or time.time
        self.limiter = SlidingWindowLimiter(api_settings.rate_limit_requests, api_settings.rate_limit_window_s)
        self._flights: dict[str, concurrent.futures.Future] = {}
        self._flight_lock = threading.Lock()
        self._ee_state: dict[str, Any] = {"outcome": None, "at": None, "code": None}
        self._ee_state_lock = threading.Lock()

    # ------------------------------------------------------------------------------------------ public
    def check_rate_limit(self, client_id: str) -> None:
        wait = self.limiter.check(client_id)
        if wait is not None:
            raise RateLimited(wait)

    def compare(self, payload: Any) -> dict:
        try:
            return self._compare(payload)
        except ComparisonError as e:
            raise _public(e) from None
        except Exception:  # noqa: BLE001
            log.exception("unexpected failure while comparing locations")
            raise ComparisonError("internal_error", "The comparison could not be completed because of an internal error.",
                                  "Try again later. If it keeps failing, check the server logs.") from None

    def status(self) -> dict:
        project_set = bool(self._ee_project)
        pkg = self._package_check()
        with self._ee_state_lock:
            st = dict(self._ee_state)
        if not (project_set and pkg):
            ee_status = "not_configured"
        elif st["outcome"] == "succeeded":
            ee_status = "last_request_succeeded"
        elif st["outcome"] == "failed":
            ee_status = "last_request_failed"
        else:
            ee_status = "configured_unverified"
        ees = get_comparison_settings()
        return {
            "feature": "location-comparison",
            "configured": project_set and pkg,
            "configuration": {"earthEngineProjectSet": project_set, "earthEnginePackageInstalled": pkg,
                              "credentialsChecked": False},
            "earthEngine": {
                "status": ee_status,
                "note": ("Credentials and permissions are only verified by a real request. 'last_request_succeeded' "
                         "refers to this server process only."),
                "lastRequestAt": st["at"], "lastErrorCode": st["code"],
                "liveVerifiedByThisProcess": st["outcome"] == "succeeded",
            },
            "cache": self.cache.status(),
            "supportedVariables": list(SUPPORTED_VARIABLES),
            "supportedYearRange": {"start": FIRST_SUPPORTED_YEAR, "end": LAST_SUPPORTED_YEAR},
            "radiusKm": {"min": MIN_RADIUS_KM, "max": MAX_RADIUS_KM, "default": DEFAULT_RADIUS_KM},
            "limits": {
                "maxRequestBytes": self.api.max_request_bytes,
                "requestDeadlineSeconds": self.api.request_deadline_s,
                "earthEngineTimeoutSeconds": ees.ee_timeout_s,
                "maxConcurrentEarthEngineComputations": ees.ee_max_concurrent,
                "rateLimit": {"requests": self.api.rate_limit_requests, "windowSeconds": self.api.rate_limit_window_s,
                              "enabled": self.limiter.enabled, "scope": "per server process"},
            },
            "processingVersion": P.PROCESSING_VERSION,
            "datasetId": P.DATASET_ID,
        }

    # ------------------------------------------------------------------------------------------- steps
    def _parse(self, payload: Any) -> tuple[RegionRequest, RegionRequest, list, dict, dict]:
        if not isinstance(payload, dict):
            raise ComparisonError("invalid_request", "The request body must be a JSON object.")
        unknown = sorted(set(payload) - _ALLOWED_TOP)
        if unknown:
            raise ComparisonError("invalid_request", f"Unknown field(s): {', '.join(map(str, unknown))}.",
                                  f"Allowed fields: {', '.join(sorted(_ALLOWED_TOP))}.")
        missing = [k for k in _REQUIRED_TOP if k not in payload]
        if missing:
            raise ComparisonError("invalid_request", f"Missing required field(s): {', '.join(missing)}.")
        locs = []
        for name in ("locationA", "locationB"):
            loc = payload[name]
            if not isinstance(loc, dict) or set(loc) != {"latitude", "longitude"}:
                raise ComparisonError("invalid_request", f"{name} must be an object with exactly 'latitude' and 'longitude'.")
            locs.append(loc)
        radius = payload.get("radiusKm", DEFAULT_RADIUS_KM)
        variable = payload.get("variable", "ndvi")
        a = validate_region_request(locs[0]["latitude"], locs[0]["longitude"], radius,
                                    payload["startYear"], payload["endYear"], variable)
        b = validate_region_request(locs[1]["latitude"], locs[1]["longitude"], radius,
                                    payload["startYear"], payload["endYear"], variable)
        pair_warnings = validate_pair(a, b)        # raises identical_locations; overlap is only a warning
        return a, b, [{"code": w.code, "message": w.message} for w in pair_warnings], locs[0], locs[1]

    def _record_ee(self, outcome: str, code: Optional[str] = None) -> None:
        with self._ee_state_lock:
            self._ee_state = {"outcome": outcome, "code": code,
                              "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}

    def _resolve(self, req: RegionRequest, deadline_s: float) -> _Resolved:
        """Cache lookup, else ONE live fetch even if several identical requests arrive together (single flight)."""
        hit = self.cache.get(req)
        if hit:
            return _Resolved(hit.result, "cached", hit.key, hit.expires_at)
        key = self.cache.build_key(req).key
        with self._flight_lock:
            fut = self._flights.get(key)
            leader = fut is None
            if leader:
                fut = self._flights[key] = concurrent.futures.Future()
        if not leader:
            try:
                return fut.result(timeout=deadline_s)
            except concurrent.futures.TimeoutError:
                raise ComparisonError("earth_engine_timeout", "The comparison did not finish in time.",
                                      "Try again shortly.", retryable=True) from None
        try:
            hit = self.cache.get(req)               # another request may have stored it a moment ago
            if hit:
                res = _Resolved(hit.result, "cached", hit.key, hit.expires_at)
            else:
                try:
                    result = self._client_factory().fetch_ndvi_annual(req)
                except ComparisonError as e:
                    if e.code.startswith("earth_engine_") and e.code != "earth_engine_busy":
                        self._record_ee("failed", e.code)
                    raise
                self._record_ee("succeeded")
                stored = self.cache.put(req, result)    # failures to store never fail the request
                res = _Resolved(result, "live", key, stored.expires_at if stored else None)
            fut.set_result(res)
            return res
        except BaseException as e:
            fut.set_exception(e)
            raise
        finally:
            with self._flight_lock:
                self._flights.pop(key, None)

    def _compare(self, payload: Any) -> dict:
        a, b, pair_warnings, raw_a, raw_b = self._parse(payload)
        deadline = self.api.request_deadline_s
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="compare")
        try:
            futs = [pool.submit(self._resolve, a, deadline), pool.submit(self._resolve, b, deadline)]
            _, not_done = concurrent.futures.wait(futs, timeout=deadline)
        finally:
            pool.shutdown(wait=False)               # unfinished fetches keep running and still fill the cache
        if not_done:
            raise ComparisonError("earth_engine_timeout", "The comparison did not finish in time.",
                                  "Try again, or use a smaller radius. Locations already retrieved are cached.",
                                  retryable=True)
        ra, rb = futs[0].result(), futs[1].result()   # re-raises the first ComparisonError (A before B)
        return self._assemble(a, ra, rb, raw_a, raw_b, pair_warnings)

    # ---------------------------------------------------------------------------------------- response
    @staticmethod
    def _observation(a: P.AnnualNdvi) -> dict:
        return {"year": a.year, "value": a.value, "qualityStatus": "valid" if a.value is not None else "unavailable",
                "reasonCode": a.reason_code, "reason": a.reason, "compositeCount": a.n_composites,
                "validPixelFraction": a.valid_pixel_fraction, "meanValidComposites": a.mean_valid_composites,
                "snowFlagFraction": a.snow_flag_fraction, "cloudFlagFraction": a.cloud_flag_fraction}

    def _location(self, requested: dict, res: _Resolved) -> dict:
        r = res.result
        n_valid = sum(1 for x in r.annual if x.value is not None)
        return {
            "latitude": r.request.latitude, "longitude": r.request.longitude,
            "requestedLatitude": requested["latitude"], "requestedLongitude": requested["longitude"],
            "dataStatus": res.status, "retrievedAt": r.retrieved_at, "earthEngineApiVersion": r.earth_engine_api_version,
            "cache": {"status": "hit" if res.status == "cached" else ("disabled" if not self.cache.enabled else "miss"),
                      "key": res.key, "expiresAt": _iso(res.expires_at),
                      "canonicalLatitude": f"{r.request.latitude + 0.0:.4f}",
                      "canonicalLongitude": f"{r.request.longitude + 0.0:.4f}"},
            "suitability": {"status": r.suitability.status, "waterFraction": r.suitability.water_fraction,
                            "totalPixels": r.total_pixels, "waterPixels": r.water_pixels},
            "hasUsableData": n_valid > 0, "validYearCount": n_valid,
            "warnings": [{"code": w.code, "message": w.message} for w in r.suitability.warnings],
            "observations": [self._observation(x) for x in r.annual],
        }

    def _assemble(self, req: RegionRequest, ra: _Resolved, rb: _Resolved, raw_a: dict, raw_b: dict,
                  pair_warnings: list) -> dict:
        ma, mb = ra.result.methodology, rb.result.methodology
        if (ma.get("config_fingerprint") != mb.get("config_fingerprint")
                or ma.get("processing_version") != mb.get("processing_version")):
            raise ComparisonError("internal_error", "The two locations were not processed identically.",
                                  "This is a server problem; nothing was returned.")
        loc_a, loc_b = self._location(raw_a, ra), self._location(raw_b, rb)
        n_a, n_b = loc_a["validYearCount"], loc_b["validYearCount"]
        warnings = list(pair_warnings)
        if n_a and n_b:
            result_status = "complete"
            message = "Both locations have usable NDVI values."
        elif n_a or n_b:
            result_status = "partial_data"
            missing = "Location B" if n_a else "Location A"
            message = f"{missing} has no usable NDVI values for this request; its observations are null."
            warnings.append({"code": "one_location_without_data", "message": message})
        else:
            result_status = "no_usable_data"
            message = ("Neither location has usable NDVI values for this request (see each location's warnings and "
                       "per-year reasons). All observations are null; nothing was estimated.")
            warnings.append({"code": "no_usable_data", "message": message})
        years_a = {o["year"] for o in loc_a["observations"] if o["value"] is not None}
        years_b = {o["year"] for o in loc_b["observations"] if o["value"] is not None}
        statuses = {ra.status, rb.status}
        data_status = "cached" if statuses == {"cached"} else ("live" if statuses == {"live"} else "partially_cached")
        return {
            "variable": req.variable, "unit": ma["unit"], "startYear": req.start_year, "endYear": req.end_year,
            "radiusKm": req.radius_km,
            "dataStatus": data_status, "dataOrigin": "earth_engine", "isSynthetic": False,
            "resultStatus": result_status, "resultMessage": message,
            "comparableYears": sorted(years_a & years_b),
            "locationA": loc_a, "locationB": loc_b,
            "comparisonWarnings": warnings,
            "provenance": {
                "datasetId": ma["dataset_id"], "datasetVersion": ma["dataset_version"], "sourceUrl": ma["source_url"],
                "doi": ma["doi"], "producer": P.DATASET_PRODUCER, "band": ma["band"],
                "processingVersion": ma["processing_version"], "configFingerprint": ma["config_fingerprint"],
                "retrievedAt": min(ra.result.retrieved_at, rb.result.retrieved_at),
                "servedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            },
            "methodology": {
                "processingVersion": ma["processing_version"], "band": ma["band"], "scaleFactor": ma["scale_factor"],
                "unit": ma["unit"], "physicalRange": list(ma["physical_range"]),
                "seasonalWindow": {"start": P.SEASON_START_MD, "endExclusive": P.SEASON_END_EXCLUSIVE_MD},
                "qualityFiltering": ma["quality_filtering"], "temporalAggregation": ma["temporal_aggregation"],
                "spatialAggregation": ma["spatial_support"], "acceptanceRules": ma["acceptance_rules"],
                "limitations": list(ma["limitations"]),
            },
        }


def build_default_service(settings: Any) -> LocationComparisonService:
    """Service for the running app. Touches neither the disk nor Earth Engine until a request arrives."""
    return LocationComparisonService(get_comparison_api_settings(settings.data_dir))

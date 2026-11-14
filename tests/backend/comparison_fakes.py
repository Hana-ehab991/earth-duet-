"""Shared test doubles for the Phase 3 tests. Everything here is a TEST FIXTURE: arithmetic payloads in the raw
layout the Phase 2 processor expects. They are never real observations and no test treats them as such."""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from app.services import ndvi_processing as P
from app.services.comparison_api_settings import ComparisonApiSettings
from app.services.location_comparison import LocationComparisonService

RETRIEVED_AT = "2026-11-13T00:00:00+00:00"


def raw_payload(req, base=0.50, step=0.001, missing_years=(), total=5000, water=0, snow=0.0, cloud=0.05, valid_frac=0.9):
    years = []
    for y in range(req.start_year, req.end_year + 1):
        if y in missing_years:
            years.append({"year": y, "n_images": 0})           # season without composites -> unavailable
        else:
            years.append({"year": y, "n_images": 9, "ndvi_mean": round(base + step * (y - req.start_year), 5),
                          "valid_pixels": total * valid_frac, "mean_composites": 4.0,
                          "snow_fraction": snow, "cloud_fraction": cloud})
    return {"total_pixels": total, "water_pixels": water, "years": years}


class FakeClient:
    """Stands in for EarthEngineClient. `payload(req)` builds the raw payload; `error` makes every call fail."""

    def __init__(self, payload: Optional[Callable] = None, error: Optional[BaseException] = None, delay: float = 0.0):
        self.payload = payload or (lambda req: raw_payload(req, base=0.30 + (abs(req.latitude) % 10) / 100))
        self.error, self.delay = error, delay
        self.calls: list = []
        self._lock = threading.Lock()

    def fetch_ndvi_annual(self, req):
        with self._lock:
            self.calls.append(req)
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return P.process_region(self.payload(req), req, RETRIEVED_AT, "fake-ee-0")


def api_settings(tmp_path, **kw) -> ComparisonApiSettings:
    d = dict(cache_path=tmp_path / "cache" / "comparison.sqlite", cache_ttl_days=30.0, request_deadline_s=30.0,
             rate_limit_requests=0, rate_limit_window_s=60.0, trust_forwarded_for=False, max_request_bytes=8192)
    d.update(kw)
    return ComparisonApiSettings(**d)


def make_service(tmp_path, client=None, cache=None, **kw) -> tuple[LocationComparisonService, FakeClient]:
    client = client or FakeClient()
    svc = LocationComparisonService(api_settings(tmp_path, **kw), cache=cache, client_factory=lambda: client,
                                    ee_project="test-project", package_check=lambda: True)
    return svc, client


CAIRO = {"latitude": 30.0444, "longitude": 31.2357}
ASWAN = {"latitude": 24.0889, "longitude": 32.8998}


def body(**over):
    b = {"locationA": dict(CAIRO), "locationB": dict(ASWAN), "variable": "ndvi", "startYear": 2010, "endYear": 2014,
         "radiusKm": 10}
    b.update(over)
    return b

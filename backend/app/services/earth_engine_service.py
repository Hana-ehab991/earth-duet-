"""Server-side Google Earth Engine access for NDVI annual values at an arbitrary location.

* Earth Engine is imported lazily: the API server and all existing tests run without `earthengine-api`.
* Authentication uses Application Default Credentials (or the attached service identity on Cloud Run /
  Compute Engine / GKE). `earthengine authenticate` credentials are the local-development fallback.
  No key files are read, written or created by this code, and nothing credential-like is logged or returned.
* Failures raise ComparisonError with a structured code. This module never returns invented values.
* NOT yet verified against the live Earth Engine service (see docs/EARTH_ENGINE_COMPARISON.md).
"""
from __future__ import annotations

import concurrent.futures
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .comparison_errors import ComparisonError
from .comparison_settings import ComparisonSettings, get_comparison_settings
from .comparison_validation import RegionRequest
from . import ndvi_processing as P

log = logging.getLogger("earth_duet.earth_engine")

EE_SCOPES = ["https://www.googleapis.com/auth/earthengine", "https://www.googleapis.com/auth/cloud-platform"]

SETUP_HINT = ("Server setup needed: use a Google Cloud project registered for Earth Engine with the Earth Engine API "
              "enabled, set EE_PROJECT, and provide Application Default Credentials (attached service identity in "
              "deployment; `earthengine authenticate` or `gcloud auth application-default login` locally). "
              "See docs/EARTH_ENGINE_COMPARISON.md.")
PERMISSION_HINT = ("The credentials need the 'Earth Engine Resource Viewer' and 'Service Usage Consumer' roles on the "
                   "registered project, and the project must be registered for Earth Engine.")


# --------------------------------------------------------------------------------- error classification
def classify_exception(exc: BaseException) -> ComparisonError:
    """Map any exception raised by Earth Engine / google-auth / the network to a structured ComparisonError."""
    if isinstance(exc, ComparisonError):
        return exc
    name, msg = type(exc).__name__, str(exc)
    low = msg.lower()

    def has(*needles: str) -> bool:
        return any(n in low for n in needles)

    def code(c: str) -> bool:
        return re.search(rf"\b{c}\b", low) is not None

    if name == "DefaultCredentialsError" or has("could not automatically determine credentials", "ee.authenticate",
                                                "please authorize access", "credentials not found"):
        return ComparisonError("earth_engine_not_configured", "Earth Engine credentials are not configured on the server.", SETUP_HINT)
    if name == "RefreshError" or has("invalid_grant", "invalid_client", "unauthenticated") or code("401"):
        return ComparisonError("earth_engine_auth_failed", "Earth Engine rejected the server credentials.", SETUP_HINT)
    if has("not found", "does not exist") and has("collection", "asset", "imagecollection"):
        return ComparisonError("earth_engine_dataset_unavailable", f"Dataset {P.DATASET_ID} is not available from Earth Engine.",
                               "Earth Engine reports it as missing OR inaccessible to this identity: the catalog entry may have been "
                               "renamed or deprecated (https://developers.google.com/earth-engine/datasets/status), or the "
                               "credentials may lack access. " + PERMISSION_HINT)
    if has("permission", "not registered", "not signed up", "serviceusage", "caller does not have", "access denied",
           "api has not been used", "is disabled") or code("403"):
        return ComparisonError("earth_engine_auth_failed", "The server's Earth Engine identity lacks permission.", PERMISSION_HINT)
    if has("quota", "rate limit", "too many requests", "resource_exhausted", "too many concurrent") or code("429"):
        return ComparisonError("earth_engine_quota_exceeded", "Earth Engine quota or rate limit reached. Try again later.",
                               "Cached results are still available.", retryable=True)
    if has("timed out", "deadline", "timeout") or name in {"Timeout", "ReadTimeout", "ConnectTimeout", "TimeoutError"}:
        return ComparisonError("earth_engine_timeout", "Earth Engine did not answer in time.", "Try again, or try a smaller radius.", retryable=True)
    if has("memory limit", "too many pixels", "too expensive", "computation too"):
        return ComparisonError("earth_engine_computation_limit", "The Earth Engine computation exceeded a service limit.", "Try a smaller radius.")
    if isinstance(exc, (ConnectionError, OSError)) or name in {"ConnectionError", "SSLError", "ServiceUnavailable", "HTTPError"} or code("503") or has("unavailable", "connection"):
        return ComparisonError("earth_engine_unavailable", "Earth Engine could not be reached.", "Try again later.", retryable=True)
    return ComparisonError("earth_engine_error", "Earth Engine returned an unexpected error.", msg[:300] or name)


# --------------------------------------------------------------------------------------------- graph
def build_request_graph(ee: Any, req: RegionRequest) -> Any:
    """Build ONE server-side computation returning the raw payload for a region (all requested years).

    Identical code path for every location: the only inputs are the point, radius and years.
    """
    region = ee.Geometry.Point([req.longitude, req.latitude]).buffer(req.radius_km * 1000.0)
    base = ee.ImageCollection(P.DATASET_ID)
    s0, _ = P.season_bounds(req.start_year)
    _, e1 = P.season_bounds(req.end_year)
    ref = ee.Image(base.filterDate(s0, e1).sort("system:time_start").first())
    proj = ref.select(P.BAND_NDVI).projection()  # native sinusoidal grid, rescaled to NOMINAL_SCALE_M by reduceRegion

    def reduce(img, reducer):
        return ee.Dictionary(img.reduceRegion(reducer=reducer, geometry=region, scale=P.NOMINAL_SCALE_M, crs=proj,
                                              maxPixels=P.MAX_PIXELS))

    def mask_and_scale(img):
        ndvi, summary, detail = img.select(P.BAND_NDVI), img.select(P.BAND_SUMMARY_QA), img.select(P.BAND_DETAILED_QA)
        ok = summary.eq(P.SUMMARY_QA_GOOD).And(ndvi.gte(P.RAW_VALID_MIN)).And(ndvi.lte(P.RAW_VALID_MAX))
        for bit in P.DQA_EXCLUDED_BITS:
            ok = ok.And(detail.bitwiseAnd(1 << bit).eq(0))
        return ndvi.updateMask(ok).multiply(P.SCALE_FACTOR).rename("ndvi")

    def snow_flag(img):
        s, d = img.select(P.BAND_SUMMARY_QA), img.select(P.BAND_DETAILED_QA)
        return s.eq(P.SUMMARY_QA_SNOW_ICE).Or(d.bitwiseAnd(1 << P.DQA_BIT_SNOW_ICE).gt(0)).rename("snow")

    def cloud_flag(img):
        s, d = img.select(P.BAND_SUMMARY_QA), img.select(P.BAND_DETAILED_QA)
        return (s.eq(P.SUMMARY_QA_CLOUDY).Or(d.bitwiseAnd(1 << P.DQA_BIT_ADJACENT_CLOUD).gt(0))
                .Or(d.bitwiseAnd(1 << P.DQA_BIT_MIXED_CLOUDS).gt(0)).Or(d.bitwiseAnd(1 << P.DQA_BIT_SHADOW).gt(0)).rename("cloud"))

    # Footprint: all pixels of the region on the data grid, and the share flagged as open water (one reference composite).
    detail = ref.select(P.BAND_DETAILED_QA)
    flag = detail.rightShift(P.DQA_LANDWATER_SHIFT).bitwiseAnd(P.DQA_LANDWATER_MASK)
    water = None
    for f in P.WATER_FLAGS:
        m = flag.eq(f)
        water = m if water is None else water.Or(m)
    footprint = ee.Dictionary({
        "total_pixels": reduce(detail.unmask(0), ee.Reducer.count()).get(P.BAND_DETAILED_QA),
        "water_pixels": reduce(water.rename("water").selfMask(), ee.Reducer.count()).get("water"),
    })

    def year_dict(year: int):
        start, end = P.season_bounds(year)          # end is exclusive in filterDate
        col = base.filterDate(start, end)
        n = col.size()
        masked = col.map(mask_and_scale)
        mean_img = masked.mean()                    # per-pixel mean of valid composites
        comp = masked.count().rename("comp")
        comp = comp.updateMask(comp.gt(0))          # valid composites per valid pixel
        stats = ee.Dictionary({
            "ndvi_mean": reduce(mean_img, ee.Reducer.mean()).get("ndvi"),
            "valid_pixels": reduce(mean_img, ee.Reducer.count()).get("ndvi"),
            "mean_composites": reduce(comp, ee.Reducer.mean()).get("comp"),
            "snow_fraction": reduce(col.map(snow_flag).mean(), ee.Reducer.mean()).get("snow"),
            "cloud_fraction": reduce(col.map(cloud_flag).mean(), ee.Reducer.mean()).get("cloud"),
        })
        stats = ee.Dictionary(ee.Algorithms.If(n.gt(0), stats, ee.Dictionary({})))   # empty season -> no statistics
        return ee.Dictionary({"year": year, "n_images": n}).combine(stats)

    years = ee.List([year_dict(y) for y in range(req.start_year, req.end_year + 1)])
    return footprint.combine(ee.Dictionary({"years": years}))


# ----------------------------------------------------------------------------------------------- client
class EarthEngineClient:
    """Thread-safe Earth Engine access with bounded concurrency and a hard wait limit per computation.

    `ee_module` and `adc_loader` are injectable so tests never touch the network.
    """

    def __init__(self, settings: Optional[ComparisonSettings] = None, ee_module: Any = None,
                 adc_loader: Optional[Callable[[list[str]], tuple[Any, Optional[str]]]] = None):
        self.settings = settings or get_comparison_settings()
        self._ee = ee_module
        self._adc_loader = adc_loader
        self._init_lock = threading.Lock()
        self._initialized = False
        self._slots = threading.BoundedSemaphore(self.settings.ee_max_concurrent)
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=self.settings.ee_max_concurrent,
                                                           thread_name_prefix="ee")

    # -- setup -----------------------------------------------------------------------------------------
    def _ee_module(self) -> Any:
        if self._ee is None:
            try:
                import ee  # lazy: not needed unless the comparison feature is used
            except ImportError as e:
                raise ComparisonError("earth_engine_not_configured", "The earthengine-api package is not installed on the server.",
                                      "Run: pip install -r backend/requirements.txt") from e
            self._ee = ee
        return self._ee

    def _load_adc(self) -> tuple[Any, Optional[str]]:
        if self._adc_loader is not None:
            return self._adc_loader(EE_SCOPES)
        import google.auth  # installed with earthengine-api
        return google.auth.default(scopes=EE_SCOPES)

    def ensure_initialized(self) -> None:
        with self._init_lock:
            if self._initialized:
                return
            ee = self._ee_module()
            project = self.settings.ee_project
            if not project:
                raise ComparisonError("earth_engine_not_configured", "No Earth Engine project is configured (EE_PROJECT).", SETUP_HINT)
            try:  # 1) Application Default Credentials / attached service identity
                creds, _ = self._load_adc()
                ee.Initialize(credentials=creds, project=project)
            except Exception as adc_err:  # noqa: BLE001
                try:  # 2) local-development fallback: credentials stored by `earthengine authenticate`
                    ee.Initialize(project=project)
                except Exception as stored_err:  # noqa: BLE001
                    no_adc = type(adc_err).__name__ == "DefaultCredentialsError"
                    log.warning("Earth Engine initialisation failed (%s)", type(stored_err if no_adc else adc_err).__name__)
                    raise classify_exception(stored_err if no_adc else adc_err) from None
            try:
                ee.data.setDeadline(int(self.settings.ee_timeout_s * 1000))
            except Exception:  # noqa: BLE001  (older client versions)
                pass
            self._initialized = True

    # -- execution with admission control --------------------------------------------------------------
    def _execute(self, work: Callable[[Any], Any]) -> Any:
        """Run `work(ee)` in a worker thread. At most `ee_max_concurrent` computations exist at once; a computation
        abandoned after a timeout keeps its slot until it really finishes, so timeouts cannot cause overload."""
        if not self._slots.acquire(timeout=self.settings.ee_queue_wait_s):
            raise ComparisonError("earth_engine_busy", "The server is busy with other comparisons. Try again in a moment.",
                                  retryable=True)

        def run():
            try:
                self.ensure_initialized()
                return work(self._ee_module())
            except BaseException as e:  # noqa: BLE001
                raise classify_exception(e) from None
            finally:
                self._slots.release()

        try:
            fut = self._pool.submit(run)
        except BaseException:
            self._slots.release()
            raise
        try:
            return fut.result(timeout=self.settings.ee_timeout_s)
        except concurrent.futures.TimeoutError:
            raise ComparisonError("earth_engine_timeout", "Earth Engine did not answer in time.",
                                  "Try again, or try a smaller radius.", retryable=True) from None

    # -- public API -------------------------------------------------------------------------------------
    def fetch_ndvi_annual(self, request: RegionRequest) -> P.NdviRegionResult:
        """Annual NDVI for one region. Raises ComparisonError on any failure; never substitutes other data."""
        def work(ee: Any):
            raw = build_request_graph(ee, request).getInfo()
            return raw, getattr(ee, "__version__", None)

        raw, version = self._execute(work)
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return P.process_region(raw, request, retrieved_at, version)

    def probe(self) -> dict:
        """Cheap connectivity/permission check (one tiny computation). For a health/status endpoint."""
        def work(ee: Any):
            return ee.ImageCollection(P.DATASET_ID).limit(1).size().getInfo()
        n = self._execute(work)
        return {"status": "ready", "dataset_id": P.DATASET_ID, "dataset_reachable": bool(n),
                "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}


_client: Optional[EarthEngineClient] = None
_client_lock = threading.Lock()


def get_client() -> EarthEngineClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = EarthEngineClient()
        return _client

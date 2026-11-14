"""NDVI methodology and pure processing (no Earth Engine import, so everything here is unit-testable).

Dataset  : MODIS/061/MOD13Q1 (Terra Vegetation Indices, 16-day composites, 250 m).
Quantity : NDVI indicator (dimensionless, -0.2..1.0 after scaling). NOT a measurement of vegetation area,
           desertification or vegetation loss. Changes in NDVI must be described as changes in the NDVI indicator.

Band layout and QA bit meanings below were checked against the Earth Engine catalog page for
MODIS/061/MOD13Q1 (https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1).
Nothing in this module has been run against the live Earth Engine service.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Any, Optional

from .comparison_errors import ComparisonError
from .comparison_validation import RegionRequest

# ----------------------------------------------------------------------------------------------- dataset
DATASET_ID = "MODIS/061/MOD13Q1"
DATASET_VERSION = "061"
DATASET_URL = "https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1"
DATASET_DOI = "https://doi.org/10.5067/MODIS/MOD13Q1.061"
DATASET_PRODUCER = "NASA LP DAAC at the USGS EROS Center"
BAND_NDVI, BAND_SUMMARY_QA, BAND_DETAILED_QA = "NDVI", "SummaryQA", "DetailedQA"

# ---------------------------------------------------------------------------------------------- scaling
SCALE_FACTOR = 0.0001
RAW_VALID_MIN, RAW_VALID_MAX = -2000, 10000          # catalog valid range of the NDVI band; anything else (e.g. -3000 fill) is invalid
NDVI_MIN, NDVI_MAX = RAW_VALID_MIN * SCALE_FACTOR, RAW_VALID_MAX * SCALE_FACTOR  # -0.2 .. 1.0

# --------------------------------------------------------------------------------------------- quality
SUMMARY_QA_GOOD, SUMMARY_QA_MARGINAL, SUMMARY_QA_SNOW_ICE, SUMMARY_QA_CLOUDY = 0, 1, 2, 3
DQA_BIT_ADJACENT_CLOUD, DQA_BIT_MIXED_CLOUDS, DQA_BIT_SNOW_ICE, DQA_BIT_SHADOW = 8, 10, 14, 15
#: A composite pixel is used only if SummaryQA == 0 (good) AND none of these DetailedQA bits is set.
DQA_EXCLUDED_BITS = (DQA_BIT_ADJACENT_CLOUD, DQA_BIT_MIXED_CLOUDS, DQA_BIT_SNOW_ICE, DQA_BIT_SHADOW)
DQA_LANDWATER_SHIFT, DQA_LANDWATER_MASK = 11, 0b111
#: DetailedQA bits 11-13 values treated as open water: 0 shallow ocean, 3 shallow inland water,
#: 5 deep inland water, 6 moderate/continental ocean, 7 deep ocean. (1 = land; 2 coastline/shoreline and
#: 4 ephemeral water are mixed/uncertain and are NOT counted as water.)
WATER_FLAGS = (0, 3, 5, 6, 7)

# ----------------------------------------------------------------------------------- season / geometry
SEASON_START_MD = "04-01"
SEASON_END_EXCLUSIVE_MD = "06-01"
NOMINAL_SCALE_M = 250
MAX_PIXELS = int(1e8)

# ---------------------------------------------------------------------- acceptance thresholds (design choices)
MIN_VALID_PIXEL_FRACTION = 0.5       # share of the region's pixels with >=1 valid composite in the season
MIN_MEAN_VALID_COMPOSITES = 2.0      # mean number of valid composites per valid pixel
WATER_UNSUITABLE_FRACTION = 0.5      # region mostly water -> NDVI not meaningful
WATER_WARNING_FRACTION = 0.1
SNOW_REASON_FRACTION = 0.3           # >=30 % of pixel-composites flagged snow/ice -> reason "snow_ice"
CLOUD_REASON_FRACTION = 0.3
LOW_NDVI_WARNING = 0.2               # below this NDVI typically means sparse/no green vegetation (bare ground, sand, rock, snow, built-up)

PROCESSING_VERSION = "ndvi-annual-v1"

REASON_TEXT = {
    "no_composites": "No MODIS composites exist for this season.",
    "water": "The region is mostly open water, where NDVI is not meaningful.",
    "snow_ice": "Observations were flagged as snow or ice.",
    "cloud": "Observations were flagged as cloud, cloud-adjacent, mixed cloud or shadow.",
    "no_valid_observations": "No observation passed the quality filter.",
    "insufficient_valid_pixels": "Too few pixels in the region had a valid observation this season "
                                f"(minimum {MIN_VALID_PIXEL_FRACTION:.0%}).",
    "insufficient_valid_composites": "Valid pixels were supported by too few composites this season "
                                     f"(minimum mean {MIN_MEAN_VALID_COMPOSITES:g}).",
    "no_pixels": "The region contains no source pixels.",
}


# ------------------------------------------------------------------------- reference (client-side) rules
def scale_ndvi_raw(raw: Any) -> Optional[float]:
    """Raw MOD13Q1 NDVI integer -> NDVI. Fill values, NaN, None and out-of-range values become None."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        return None
    if raw < RAW_VALID_MIN or raw > RAW_VALID_MAX:
        return None
    return round(raw * SCALE_FACTOR, 4)


def pixel_is_valid(raw_ndvi: Any, summary_qa: Any, detailed_qa: Any) -> bool:
    """Reference implementation of the per-pixel acceptance rule that earth_engine_service applies server-side."""
    if scale_ndvi_raw(raw_ndvi) is None or summary_qa != SUMMARY_QA_GOOD:
        return False
    if not isinstance(detailed_qa, int) or isinstance(detailed_qa, bool):
        return False
    return all((detailed_qa >> b) & 1 == 0 for b in DQA_EXCLUDED_BITS)


def land_water_flag(detailed_qa: int) -> int:
    return (detailed_qa >> DQA_LANDWATER_SHIFT) & DQA_LANDWATER_MASK


def is_water(detailed_qa: int) -> bool:
    return land_water_flag(detailed_qa) in WATER_FLAGS


def season_bounds(year: int) -> tuple[str, str]:
    """(start inclusive, end EXCLUSIVE) ISO dates of the seasonal window. Earth Engine filterDate is [start, end)."""
    return f"{year}-{SEASON_START_MD}", f"{year}-{SEASON_END_EXCLUSIVE_MD}"


# ----------------------------------------------------------------------------------------- methodology
def qa_config() -> dict:
    return {
        "summary_qa_accepted": [SUMMARY_QA_GOOD],
        "detailed_qa_excluded_bits": list(DQA_EXCLUDED_BITS),
        "raw_valid_range": [RAW_VALID_MIN, RAW_VALID_MAX],
        "water_flags": list(WATER_FLAGS),
        "min_valid_pixel_fraction": MIN_VALID_PIXEL_FRACTION,
        "min_mean_valid_composites": MIN_MEAN_VALID_COMPOSITES,
        "water_unsuitable_fraction": WATER_UNSUITABLE_FRACTION,
        "snow_reason_fraction": SNOW_REASON_FRACTION,
        "cloud_reason_fraction": CLOUD_REASON_FRACTION,
    }


def qa_config_fingerprint() -> str:
    """Stable hash of everything that changes which pixels/years are accepted. Part of the cache key (Phase 3)."""
    blob = json.dumps({"processing_version": PROCESSING_VERSION, "dataset": DATASET_ID, "scale": SCALE_FACTOR,
                       "season": [SEASON_START_MD, SEASON_END_EXCLUSIVE_MD], "nominal_scale_m": NOMINAL_SCALE_M,
                       "qa": qa_config()}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def methodology(radius_km: float) -> dict:
    """Machine-readable description of exactly what was computed (stored with every result)."""
    return {
        "processing_version": PROCESSING_VERSION,
        "config_fingerprint": qa_config_fingerprint(),
        "dataset_id": DATASET_ID, "dataset_version": DATASET_VERSION, "source_url": DATASET_URL, "doi": DATASET_DOI,
        "band": BAND_NDVI, "scale_factor": SCALE_FACTOR, "unit": "dimensionless (NDVI indicator)",
        "physical_range": [NDVI_MIN, NDVI_MAX],
        "quality_filtering": (
            "Per composite pixel, kept only if SummaryQA = 0 (good data) and DetailedQA bits 8 (adjacent cloud), "
            "10 (mixed clouds), 14 (possible snow/ice) and 15 (possible shadow) are all 0, and the raw NDVI lies in "
            f"{RAW_VALID_MIN}..{RAW_VALID_MAX} (this excludes the fill value). Nothing is gap-filled or interpolated."),
        "temporal_aggregation": (
            f"Composites whose start date lies in [{SEASON_START_MD}, {SEASON_END_EXCLUSIVE_MD}) of each year "
            "(end exclusive) are selected. Per pixel, the mean of the valid composites is taken; the regional value "
            "is then the mean over pixels, so every pixel has equal weight regardless of how many composites it had. "
            "A 16-day composite that starts in the window may extend a few days past its end date."),
        "spatial_support": (
            f"Circle of radius {radius_km:g} km (geodesic buffer) around the point, sampled at {NOMINAL_SCALE_M} m "
            "nominal resolution in the dataset's native sinusoidal projection (native pixel ~231.7 m). "
            "Identical for every location in a comparison."),
        "acceptance_rules": (
            f"A year is reported only if at least {MIN_VALID_PIXEL_FRACTION:.0%} of the region's pixels have a valid "
            f"observation and valid pixels average at least {MIN_MEAN_VALID_COMPOSITES:g} valid composites; otherwise "
            "the year is null with a stated reason. Regions with >=50 % open water are reported as unsuitable."),
        "limitations": [
            "NDVI is a greenness indicator derived from red and near-infrared reflectance. It is not a measurement of "
            "vegetation area, biomass, desertification or vegetation loss.",
            "No land-cover classification is applied: cropland, built-up areas, bare ground and natural vegetation "
            "inside the circle are averaged together.",
            "The April-June window is the same at every latitude and is not a growing season everywhere "
            "(for example the Southern Hemisphere autumn/winter, or high latitudes).",
            "Water is detected from one composite's land/water flag; seasonal or ephemeral water may be missed.",
            "Interannual NDVI differences can reflect cloud/aerosol residue, sensor and compositing effects, "
            "phenology timing and rainfall, not only land-surface change.",
        ],
    }


# -------------------------------------------------------------------------------------------- results
@dataclass(frozen=True)
class AnnualNdvi:
    year: int
    value: Optional[float]                 # NDVI, or None (never fabricated, never interpolated)
    reason_code: Optional[str]             # why value is None
    reason: Optional[str]
    n_composites: int
    valid_pixel_fraction: Optional[float]
    mean_valid_composites: Optional[float]
    snow_flag_fraction: Optional[float]
    cloud_flag_fraction: Optional[float]


@dataclass(frozen=True)
class SuitabilityWarning:
    code: str
    message: str


@dataclass(frozen=True)
class RegionSuitability:
    status: str                            # "ok" | "warning" | "unsuitable" | "unavailable"
    warnings: tuple[SuitabilityWarning, ...]
    water_fraction: Optional[float]


@dataclass(frozen=True)
class NdviRegionResult:
    request: RegionRequest
    annual: tuple[AnnualNdvi, ...]
    suitability: RegionSuitability
    total_pixels: int
    water_pixels: int
    retrieved_at: str
    methodology: dict
    earth_engine_api_version: Optional[str] = None


# ------------------------------------------------------------------------------------------- helpers
def _num(x: Any) -> Optional[float]:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return float(x)


def _bad(msg: str) -> ComparisonError:
    return ComparisonError("earth_engine_bad_response", msg,
                           "The Earth Engine response did not match the expected structure; nothing was returned.")


def _classify_unavailable(snow: Optional[float], cloud: Optional[float], default: str) -> str:
    # Pick the dominant documented cause; ties favour snow (a stable surface state) over cloud.
    s, c = snow or 0.0, cloud or 0.0
    if s >= SNOW_REASON_FRACTION and s >= c:
        return "snow_ice"
    if c >= CLOUD_REASON_FRACTION:
        return "cloud"
    return default


def _null_year(year: int, code: str, n: int, vpf=None, mvc=None, snow=None, cloud=None) -> AnnualNdvi:
    return AnnualNdvi(year, None, code, REASON_TEXT[code], n, vpf, mvc, snow, cloud)


# ---------------------------------------------------------------------------------------------- main
def process_region(raw: dict, request: RegionRequest, retrieved_at: str,
                   earth_engine_api_version: Optional[str] = None) -> NdviRegionResult:
    """Turn the raw Earth Engine payload for ONE region into validated annual values + suitability.

    Raw layout: {"total_pixels", "water_pixels", "years": [{"year", "n_images", "ndvi_mean", "valid_pixels",
    "mean_composites", "snow_fraction", "cloud_fraction"}, ...]}. NDVI is expected already scaled by 0.0001.
    The same function and thresholds are used for every location, so locations are always treated identically.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("years"), list):
        raise _bad("Missing 'years' list.")
    total = _num(raw.get("total_pixels"))
    total_i = int(total) if total is not None else 0
    water_i = int(_num(raw.get("water_pixels")) or 0)
    if water_i > total_i > 0:
        raise _bad("Water pixel count exceeds total pixel count.")
    rows: dict[int, dict] = {}
    for r in raw["years"]:
        if isinstance(r, dict) and isinstance(r.get("year"), (int, float)) and not isinstance(r.get("year"), bool):
            rows[int(r["year"])] = r
    water_fraction = (water_i / total_i) if total_i > 0 else None
    mostly_water = water_fraction is not None and water_fraction >= WATER_UNSUITABLE_FRACTION

    annual: list[AnnualNdvi] = []
    for year in range(request.start_year, request.end_year + 1):
        row = rows.get(year)
        if row is None:
            raise _bad(f"No result returned for {year}.")
        n = int(_num(row.get("n_images")) or 0)
        snow, cloud = _num(row.get("snow_fraction")), _num(row.get("cloud_fraction"))
        mean = _num(row.get("ndvi_mean"))
        valid = _num(row.get("valid_pixels"))
        comps = _num(row.get("mean_composites"))
        if total_i <= 0:
            annual.append(_null_year(year, "no_pixels", n)); continue
        if mostly_water:
            annual.append(_null_year(year, "water", n, snow=snow, cloud=cloud)); continue
        if n == 0:
            annual.append(_null_year(year, "no_composites", 0)); continue
        if valid is not None and valid > total_i:
            raise _bad(f"Valid pixel count exceeds total pixel count for {year}.")
        vpf = (valid / total_i) if valid is not None else 0.0
        if mean is None or not valid:
            annual.append(_null_year(year, _classify_unavailable(snow, cloud, "no_valid_observations"), n,
                                     vpf, comps, snow, cloud)); continue
        if not (NDVI_MIN - 1e-6 <= mean <= NDVI_MAX + 1e-6):
            raise _bad(f"Regional NDVI {mean} for {year} is outside the physical range "
                       f"{NDVI_MIN}..{NDVI_MAX}; the scale factor was probably not applied correctly.")
        if vpf < MIN_VALID_PIXEL_FRACTION:
            annual.append(_null_year(year, _classify_unavailable(snow, cloud, "insufficient_valid_pixels"), n,
                                     vpf, comps, snow, cloud)); continue
        if comps is None or comps < MIN_MEAN_VALID_COMPOSITES:
            annual.append(_null_year(year, "insufficient_valid_composites", n, vpf, comps, snow, cloud)); continue
        annual.append(AnnualNdvi(year, round(mean, 5), None, None, n, round(vpf, 4), round(comps, 3), snow, cloud))

    return NdviRegionResult(request=request, annual=tuple(annual),
                            suitability=_suitability(request, annual, water_fraction, mostly_water),
                            total_pixels=total_i, water_pixels=water_i, retrieved_at=retrieved_at,
                            methodology=methodology(request.radius_km), earth_engine_api_version=earth_engine_api_version)


def _suitability(req: RegionRequest, annual: list[AnnualNdvi], water_fraction: Optional[float], mostly_water: bool) -> RegionSuitability:
    w: list[SuitabilityWarning] = []
    values = [a.value for a in annual if a.value is not None]
    status = "ok"
    if mostly_water:
        w.append(SuitabilityWarning("mostly_water", f"About {water_fraction:.0%} of this region is open water (ocean or "
                                    "inland water). NDVI is not meaningful there, so no values are reported."))
        status = "unsuitable"
    elif not values:
        top = Counter(a.reason_code for a in annual).most_common(1)[0][0]
        w.append(SuitabilityWarning("no_valid_ndvi", "No year had enough valid observations. Most common reason: "
                                    f"{REASON_TEXT.get(top, top)}"))
        status = "unavailable"
    else:
        if water_fraction is not None and water_fraction >= WATER_WARNING_FRACTION:
            w.append(SuitabilityWarning("includes_water", f"About {water_fraction:.0%} of the region is open water; the "
                                        "NDVI is computed over the land and cloud-free pixels only."))
        missing = len(annual) - len(values)
        if missing:
            w.append(SuitabilityWarning("missing_years", f"{missing} of {len(annual)} years have no usable value and are "
                                        "left empty (not interpolated)."))
        if statistics.median(values) < LOW_NDVI_WARNING:
            w.append(SuitabilityWarning("sparse_vegetation", f"Typical NDVI is below {LOW_NDVI_WARNING}: little or no green "
                                        "vegetation is detected (bare ground, sand, rock, snow or built-up land are likely). "
                                        "Small NDVI differences here are easily dominated by noise."))
        if min(values) < 0:
            w.append(SuitabilityWarning("negative_ndvi", "Some values are negative. NDVI can be below zero over water, "
                                        "snow/ice or cloud-contaminated surfaces; negative values are not 'less vegetation' "
                                        "in a linear sense."))
        status = "warning" if w else "ok"
    if req.latitude < 0:
        w.append(SuitabilityWarning("southern_hemisphere_season", "April-June is autumn/winter in the Southern Hemisphere; "
                                    "the fixed seasonal window may not represent the growing season."))
    elif req.latitude >= 60:
        w.append(SuitabilityWarning("high_latitude_season", "At high latitudes April-June may still be snow-covered or "
                                    "precede the growing season."))
    if len(w) and status == "ok":
        status = "warning"
    if req.latitude <= -60:
        w.append(SuitabilityWarning("high_latitude_season", "At high latitudes the fixed seasonal window may not match "
                                    "the growing season."))
    return RegionSuitability(status=status, warnings=tuple(w), water_fraction=None if water_fraction is None else round(water_fraction, 4))

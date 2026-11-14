"""Input validation for arbitrary-location comparison requests (pure; no Earth Engine import).

Every limit here also bounds the cost of a request (radius, year span, one variable), which is part of the
protection against excessive arbitrary-location queries. Rate limiting is added at the API layer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .comparison_errors import ComparisonError

SUPPORTED_VARIABLES = ("ndvi",)
FIRST_SUPPORTED_YEAR = 2010
LAST_SUPPORTED_YEAR = 2024
MIN_RADIUS_KM = 1.0
MAX_RADIUS_KM = 25.0
DEFAULT_RADIUS_KM = 10.0
#: Coordinates are rounded to 4 decimals (~11 m), far below the ~250 m source pixel. The rounded value is
#: what is queried AND what is reported/cached, so the response always describes the region actually analysed.
COORD_DECIMALS = 4


@dataclass(frozen=True)
class RegionRequest:
    latitude: float
    longitude: float
    radius_km: float
    start_year: int
    end_year: int
    variable: str = "ndvi"


@dataclass(frozen=True)
class PairWarning:
    code: str
    message: str


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def validate_region_request(latitude: Any, longitude: Any, radius_km: Any, start_year: Any, end_year: Any,
                            variable: Any = "ndvi") -> RegionRequest:
    if not (_is_number(latitude) and _is_number(longitude)):
        raise ComparisonError("invalid_coordinates", "Latitude and longitude must be finite numbers.")
    if not -90.0 <= latitude <= 90.0:
        raise ComparisonError("invalid_coordinates", f"Latitude {latitude} is outside -90..90 degrees.")
    if not -180.0 <= longitude <= 180.0:
        raise ComparisonError("invalid_coordinates", f"Longitude {longitude} is outside -180..180 degrees.",
                              "Use decimal degrees; longitudes are not wrapped automatically.")
    if not _is_number(radius_km) or not MIN_RADIUS_KM <= radius_km <= MAX_RADIUS_KM:
        raise ComparisonError("invalid_radius", f"Region radius must be between {MIN_RADIUS_KM:g} and {MAX_RADIUS_KM:g} km.")
    if not (_is_int(start_year) and _is_int(end_year)):
        raise ComparisonError("invalid_year_range", "Start and end year must be whole numbers.")
    if start_year > end_year:
        raise ComparisonError("invalid_year_range", "Start year must not be after end year.")
    if start_year < FIRST_SUPPORTED_YEAR or end_year > LAST_SUPPORTED_YEAR:
        raise ComparisonError("invalid_year_range",
                              f"Years must be within {FIRST_SUPPORTED_YEAR}-{LAST_SUPPORTED_YEAR} for this dataset.",
                              "Future NDVI is not available: no validated projection dataset is configured.")
    var = variable.strip().lower() if isinstance(variable, str) else None
    if var not in SUPPORTED_VARIABLES:
        raise ComparisonError("unsupported_variable", f"Variable {variable!r} is not supported.",
                              f"Supported: {', '.join(SUPPORTED_VARIABLES)}.")
    return RegionRequest(round(float(latitude), COORD_DECIMALS), round(float(longitude), COORD_DECIMALS),
                         round(float(radius_km), 3), start_year, end_year, var)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def validate_pair(a: RegionRequest, b: RegionRequest) -> list[PairWarning]:
    """Both locations must be analysed with identical support and period; returns non-fatal warnings."""
    if (a.radius_km, a.start_year, a.end_year, a.variable) != (b.radius_km, b.start_year, b.end_year, b.variable):
        raise ComparisonError("mismatched_spatial_support",
                              "Both locations must use the same radius, period and variable to be comparable.")
    if (a.latitude, a.longitude) == (b.latitude, b.longitude):
        raise ComparisonError("identical_locations", "Location A and Location B are the same point.",
                              "Choose two different locations.")
    d = haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)
    warnings: list[PairWarning] = []
    if d < 2 * a.radius_km:
        warnings.append(PairWarning("regions_overlap", f"The two regions overlap (centres {d:.1f} km apart, "
                                    f"radius {a.radius_km:g} km each), so they are not independent samples."))
    return warnings

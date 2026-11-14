"""Pydantic models for POST /api/compare-locations and GET /api/comparison/status.

Field names are camelCase on purpose (this endpoint's documented contract; the older endpoints are snake_case).
The request model is used for documentation (OpenAPI) only: the route parses the body itself so that every
problem maps to a specific lowercase error code in the standard {"error": {...}} format.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------------------------- request
class LocationIn(BaseModel):
    latitude: float = Field(..., description="Decimal degrees, -90..90.", examples=[30.0444])
    longitude: float = Field(..., description="Decimal degrees, -180..180 (not wrapped).", examples=[31.2357])


class CompareLocationsRequest(BaseModel):
    locationA: LocationIn
    locationB: LocationIn
    variable: str = Field("ndvi", description="Supported: 'ndvi'.")
    startYear: int = Field(..., description="First year, 2010..2024.", examples=[2010])
    endYear: int = Field(..., description="Last year (inclusive), 2010..2024.", examples=[2024])
    radiusKm: float = Field(10.0, description="Sampling radius in km, 1..25. Same for both locations.")


# --------------------------------------------------------------------------------------------- response
class WarningOut(BaseModel):
    code: str
    message: str


class ObservationOut(BaseModel):
    year: int
    value: Optional[float] = Field(None, description="Annual NDVI (dimensionless), or null. Never interpolated.")
    qualityStatus: Literal["valid", "unavailable"]
    reasonCode: Optional[str] = Field(None, description="Why value is null.")
    reason: Optional[str] = None
    compositeCount: int
    validPixelFraction: Optional[float] = None
    meanValidComposites: Optional[float] = None
    snowFlagFraction: Optional[float] = None
    cloudFlagFraction: Optional[float] = None


class CacheInfoOut(BaseModel):
    status: Literal["hit", "miss", "disabled"]
    key: Optional[str] = None
    expiresAt: Optional[str] = None
    canonicalLatitude: str
    canonicalLongitude: str


class SuitabilityOut(BaseModel):
    status: Literal["ok", "warning", "unsuitable", "unavailable"]
    waterFraction: Optional[float] = None
    totalPixels: int
    waterPixels: int


class LocationOut(BaseModel):
    latitude: float = Field(..., description="Canonical (4-decimal) latitude actually analysed.")
    longitude: float
    requestedLatitude: float = Field(..., description="Latitude exactly as sent.")
    requestedLongitude: float
    dataStatus: Literal["live", "cached"]
    retrievedAt: str = Field(..., description="When Earth Engine was queried for this location (ISO 8601 UTC).")
    earthEngineApiVersion: Optional[str] = None
    cache: CacheInfoOut
    suitability: SuitabilityOut
    hasUsableData: bool
    validYearCount: int
    warnings: list[WarningOut]
    observations: list[ObservationOut]


class SeasonalWindowOut(BaseModel):
    start: str
    endExclusive: str


class ProvenanceOut(BaseModel):
    datasetId: str
    datasetVersion: str
    sourceUrl: str
    doi: str
    producer: str
    band: str
    processingVersion: str
    configFingerprint: str
    retrievedAt: str = Field(..., description="Earliest retrieval time of the two locations.")
    servedAt: str


class MethodologyOut(BaseModel):
    processingVersion: str
    band: str
    scaleFactor: float
    unit: str
    physicalRange: list[float]
    seasonalWindow: SeasonalWindowOut
    qualityFiltering: str
    temporalAggregation: str
    spatialAggregation: str
    acceptanceRules: str
    limitations: list[str]


class CompareLocationsResponse(BaseModel):
    variable: str
    unit: str
    startYear: int
    endYear: int
    radiusKm: float
    dataStatus: Literal["live", "cached", "partially_cached"]
    dataOrigin: Literal["earth_engine"] = Field(..., description="Only real Earth Engine data (live or cached).")
    isSynthetic: Literal[False]
    resultStatus: Literal["complete", "partial_data", "no_usable_data"]
    resultMessage: str
    comparableYears: list[int] = Field(..., description="Years where BOTH locations have a valid value.")
    locationA: LocationOut
    locationB: LocationOut
    comparisonWarnings: list[WarningOut]
    provenance: ProvenanceOut
    methodology: MethodologyOut


class ErrorBody(BaseModel):
    code: str
    message: str
    hint: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class ComparisonStatusOut(BaseModel):
    feature: str
    configured: bool
    configuration: dict[str, Any]
    earthEngine: dict[str, Any]
    cache: dict[str, Any]
    supportedVariables: list[str]
    supportedYearRange: dict[str, int]
    radiusKm: dict[str, float]
    limits: dict[str, Any]
    processingVersion: str
    datasetId: str

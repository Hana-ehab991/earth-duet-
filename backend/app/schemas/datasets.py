"""Pydantic schemas for processed datasets and API payloads.

Every dataset carries mandatory provenance (location, geometry, variable, unit,
time range, source, processing method, record type and — for projections —
scenario/model/baseline/uncertainty).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

RecordType = Literal["observation", "reanalysis", "model_historical", "projection", "synthetic_demo"]


class Source(BaseModel):
    name: str
    url: str
    product: str
    parameter: str
    citation_note: Optional[str] = None
    extra: dict = Field(default_factory=dict)


class Geometry(BaseModel):
    type: Literal["point", "bbox", "polygon"]
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Nominal native-grid footprint [west, south, east, north] used only to *draw* spatial support.
    support_bbox: Optional[list[float]] = None
    spatial_support: str


class Processing(BaseModel):
    method: str
    missing_value_handling: Optional[str] = None
    retrieved_at: Optional[str] = None
    request: Optional[str] = None
    extra: dict = Field(default_factory=dict)


class Baseline(BaseModel):
    period: tuple[int, int]
    mean: Optional[float] = None
    description: str


class ObservedRecord(BaseModel):
    year: int
    value: Optional[float] = None
    complete: bool
    n_months: int
    reason: Optional[str] = None  # why value is null


class ObservedDataset(BaseModel):
    schema_version: str = "1.0"
    dataset_id: str
    location_id: str
    variable_id: str
    record_type: RecordType
    is_demo: bool = False
    unit: str
    source: Source
    geometry: Geometry
    processing: Processing
    baseline: Baseline
    coverage: dict
    records: list[ObservedRecord]

    @model_validator(mode="after")
    def _check(self) -> "ObservedDataset":
        years = [r.year for r in self.records]
        if len(years) != len(set(years)):
            raise ValueError("duplicate years in observed records")
        if self.is_demo != (self.record_type == "synthetic_demo"):
            raise ValueError("is_demo must be true iff record_type == 'synthetic_demo'")
        for r in self.records:
            if r.complete and r.value is None:
                raise ValueError(f"year {r.year} marked complete but has no value")
            if not r.complete and r.value is not None:
                raise ValueError(f"year {r.year} incomplete but has a value (incomplete years must be null)")
        return self


class ModelRef(BaseModel):
    id: str
    variant: Optional[str] = None
    note: Optional[str] = None


class WindowDef(BaseModel):
    target_year: int
    start_year: int
    end_year: int
    clipped: bool


class ProjectionRecord(BaseModel):
    scenario: str
    target_year: int
    model: str
    value: float
    baseline: float
    anomaly: float


class EnsembleStat(BaseModel):
    scenario: str
    target_year: int
    n_models: int
    mean: float
    min: float
    max: float
    std: float
    anomaly_mean: float
    anomaly_min: float
    anomaly_max: float


class ProjectionDataset(BaseModel):
    schema_version: str = "1.0"
    dataset_id: str
    location_id: str
    variable_id: str
    record_type: RecordType
    is_demo: bool = False
    unit: str
    source: Source
    geometry: Geometry
    processing: Processing
    baseline: Baseline
    models: list[ModelRef]
    scenarios: list[str]
    windows: list[WindowDef]
    records: list[ProjectionRecord]
    ensemble: list[EnsembleStat]
    uncertainty_note: str

    @model_validator(mode="after")
    def _check(self) -> "ProjectionDataset":
        if self.is_demo != (self.record_type == "synthetic_demo"):
            raise ValueError("is_demo must be true iff record_type == 'synthetic_demo'")
        if not self.is_demo and self.record_type != "projection":
            raise ValueError("non-demo projection dataset must have record_type 'projection'")
        known = {m.id for m in self.models}
        for r in self.records:
            if r.model not in known:
                raise ValueError(f"record references unknown model {r.model}")
            if abs((r.value - r.baseline) - r.anomaly) > 1e-6:
                raise ValueError("anomaly != value - baseline")
        return self


# ----- API payloads -----

class ErrorBody(BaseModel):
    code: str
    message: str
    hint: Optional[str] = None


class ApiError(BaseModel):
    error: ErrorBody


class LocationOut(BaseModel):
    id: str
    name: str
    country: Optional[str]
    latitude: float
    longitude: float
    default_zoom_meters: int
    primary_variable: str
    status: str
    analysis_geometry: dict
    dataset_status: Literal["configured", "demo_only", "not_configured", "data_not_fetched"]
    dataset_message: str


class TimeseriesOut(BaseModel):
    dataset: ObservedDataset
    latest_complete_year: Optional[int]
    first_year: Optional[int]
    available_years: list[int]
    requested_range: tuple[Optional[int], Optional[int]]


class ClimateOut(BaseModel):
    dataset: ProjectionDataset
    disclaimer: str

"""Structured errors for the location-comparison feature.

Same shape as the existing API errors ({"error": {"code", "message", "hint"}}) so the frontend can
reuse ApiRequestError. Nothing here is Earth Engine specific, so pure modules can import it freely.
"""
from __future__ import annotations

from typing import Optional


class ComparisonError(Exception):
    def __init__(self, code: str, message: str, hint: Optional[str] = None, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.hint, self.retryable = code, message, hint, retryable

    def to_body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "hint": self.hint}}


# HTTP status per error code. Used by the API layer (Phase 3); kept here so codes and statuses stay together.
HTTP_STATUS: dict[str, int] = {
    # client input problems
    "invalid_coordinates": 422, "invalid_radius": 422, "invalid_year_range": 422, "unsupported_variable": 422,
    "identical_locations": 422, "mismatched_spatial_support": 422,
    # server-side Earth Engine problems (the client cannot fix these)
    "earth_engine_not_configured": 503, "earth_engine_auth_failed": 503, "earth_engine_unavailable": 503,
    "earth_engine_dataset_unavailable": 503, "earth_engine_computation_limit": 503,
    "earth_engine_timeout": 504, "earth_engine_bad_response": 502, "earth_engine_error": 502,
    # load protection: retry later
    "earth_engine_quota_exceeded": 429, "earth_engine_busy": 429,
}

"""Routes for the two-location comparison. Registered in main.py; existing routes are untouched."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..schemas.comparison import (CompareLocationsRequest, CompareLocationsResponse, ComparisonStatusOut,
                                  ErrorResponse)
from ..services.comparison_errors import ComparisonError
from ..services.location_comparison import LocationComparisonService

router = APIRouter(prefix="/api")

_ERRORS = {s: {"model": ErrorResponse} for s in (400, 413, 422, 429, 500, 502, 503, 504)}


def get_comparison_service(request: Request) -> LocationComparisonService:
    return request.app.state.comparison_service


def _client_id(request: Request, trust_forwarded: bool) -> str:
    if trust_forwarded:
        # Right-most entry = the address the trusted proxy itself saw; earlier entries are client-supplied.
        xff = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1][:64]
    return request.client.host if request.client else "unknown"


async def _read_json(request: Request, limit: int):
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > limit:
                raise ComparisonError("request_too_large", f"The request body is larger than {limit} bytes.",
                                      "A comparison request only needs two coordinates, a variable, years and a radius.")
        except ValueError:
            raise ComparisonError("invalid_request", "Invalid Content-Length header.") from None
    body = bytearray()
    async for chunk in request.stream():          # also caps bodies sent without Content-Length
        body.extend(chunk)
        if len(body) > limit:
            raise ComparisonError("request_too_large", f"The request body is larger than {limit} bytes.",
                                  "A comparison request only needs two coordinates, a variable, years and a radius.")
    try:
        return json.loads(bytes(body).decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ComparisonError("invalid_json", "The request body is not valid JSON.",
                              "Send a JSON object with Content-Type: application/json.") from None


@router.post(
    "/compare-locations", response_model=CompareLocationsResponse, responses=_ERRORS,
    summary="Compare annual NDVI for two arbitrary locations",
    description=("Both locations are processed identically (MODIS/061/MOD13Q1, April 1 - June 1 exclusive, same QA, "
                 "same radius). Values are real Earth Engine results (live or cached) or null with a reason; nothing "
                 "is interpolated or synthetic. A valid request with no usable measurements returns HTTP 200 with "
                 "resultStatus 'no_usable_data'; HTTP errors are only for invalid requests and service failures."),
    openapi_extra={"requestBody": {"required": True, "content": {"application/json": {
        "schema": CompareLocationsRequest.model_json_schema(),
        "example": {"locationA": {"latitude": 30.0444, "longitude": 31.2357},
                    "locationB": {"latitude": 24.0889, "longitude": 32.8998},
                    "variable": "ndvi", "startYear": 2010, "endYear": 2024, "radiusKm": 10}}}}},
)
async def compare_locations(request: Request, service: LocationComparisonService = Depends(get_comparison_service)):
    service.check_rate_limit(_client_id(request, service.api.trust_forwarded_for))
    payload = await _read_json(request, service.api.max_request_bytes)
    result = await run_in_threadpool(service.compare, payload)
    try:
        body = CompareLocationsResponse.model_validate(result).model_dump(mode="json")
    except ValidationError:
        raise ComparisonError("internal_error", "The comparison result could not be assembled.",
                              "This is a server problem; nothing was returned.") from None
    return JSONResponse(content=body)


@router.get("/comparison/status", response_model=ComparisonStatusOut,
            summary="Safe operational status of the comparison feature (cheap; never calls Earth Engine)")
def comparison_status(service: LocationComparisonService = Depends(get_comparison_service)):
    return service.status()

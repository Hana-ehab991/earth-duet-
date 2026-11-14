"""Earth Duet API. Run: uvicorn app.main:app --reload (from /backend)."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.comparison_routes import router as comparison_router
from .api.routes import router
from .config import Settings, get_settings
from .services.comparison_errors import ComparisonError
from .services.dataset_store import DatasetStore, DatasetUnavailable
from .services.location_comparison import API_HTTP_STATUS, build_default_service

_STATUS = {
    "unknown_location": 404, "unknown_variable": 404, "unknown_scenario": 404, "unknown_model": 404,
    "dataset_not_configured": 501, "dataset_not_available": 503, "dataset_invalid": 500, "bad_range": 422,
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Earth Duet API", version="0.1.0",
                  description="Provenance-first Earth science data API. Never returns fabricated values; "
                              "synthetic demo data is only served when EARTH_DUET_DEMO_MODE=true and is flagged.")
    app.state.store = DatasetStore(settings)
    app.state.comparison_service = build_default_service(settings)   # lazy: no disk / Earth Engine access yet
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["GET", "POST"], allow_headers=["*"])

    @app.exception_handler(DatasetUnavailable)
    async def _unavailable(_: Request, exc: DatasetUnavailable):
        return JSONResponse(status_code=_STATUS.get(exc.code, 400),
                            content={"error": {"code": exc.code, "message": exc.message, "hint": exc.hint}})

    @app.exception_handler(ComparisonError)
    async def _comparison_error(_: Request, exc: ComparisonError):
        headers = {"Retry-After": str(exc.retry_after)} if getattr(exc, "retry_after", None) else None
        return JSONResponse(status_code=API_HTTP_STATUS.get(exc.code, 500), content=exc.to_body(), headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {
            "code": "invalid_parameters", "message": "Invalid query parameters.",
            "hint": "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())}})

    app.include_router(router)
    app.include_router(comparison_router)
    return app


app = create_app()

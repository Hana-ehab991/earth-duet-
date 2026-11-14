from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..deps import get_store
from ..schemas.datasets import ClimateOut, LocationOut, TimeseriesOut
from ..services.dataset_store import DatasetStore, DatasetUnavailable
from ..services.imagery import imagery_for_year

router = APIRouter(prefix="/api")


@router.get("/health")
def health(store: DatasetStore = Depends(get_store)):
    return {
        "status": "ok",
        "demo_mode": store.settings.demo_mode,
        # Shows which data folder THIS server process reads. If a file you fetched is not listed as existing,
        # you are running a server from a different copy of the project (or a stale one on the same port).
        **store.diagnostics(),
        "locations": {l["id"]: store.dataset_status(l)[0] for l in store.locations()},
    }


@router.get("/locations", response_model=list[LocationOut])
def locations(store: DatasetStore = Depends(get_store)):
    out = []
    for l in store.locations():
        status, msg = store.dataset_status(l)
        out.append(LocationOut(**l, dataset_status=status, dataset_message=msg))
    return out


@router.get("/variables")
def variables(store: DatasetStore = Depends(get_store)):
    return store.variables()


@router.get("/scenarios")
def scenarios(store: DatasetStore = Depends(get_store)):
    return store.scenarios()


@router.get("/timeseries", response_model=TimeseriesOut)
def timeseries(
    location: str = Query(..., min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$"),
    variable: str = Query("air_temperature", pattern=r"^[a-z0-9_]+$"),
    start_year: Optional[int] = Query(None, ge=1900, le=2200),
    end_year: Optional[int] = Query(None, ge=1900, le=2200),
    store: DatasetStore = Depends(get_store),
):
    if start_year and end_year and start_year > end_year:
        raise DatasetUnavailable("bad_range", "start_year must be <= end_year.")
    ds = store.observed(location, variable)
    ds = ds.model_copy(update={"records": [r for r in ds.records
                                           if (start_year is None or r.year >= start_year)
                                           and (end_year is None or r.year <= end_year)]})
    complete = [r.year for r in ds.records if r.complete]
    return TimeseriesOut(
        dataset=ds,
        latest_complete_year=max(complete) if complete else None,
        first_year=min(complete) if complete else None,
        available_years=complete,
        requested_range=(start_year, end_year),
    )


@router.get("/climate", response_model=ClimateOut)
def climate(
    location: str = Query(..., pattern=r"^[a-z0-9_]+$"),
    variable: str = Query("air_temperature", pattern=r"^[a-z0-9_]+$"),
    scenario: Optional[str] = Query(None, pattern=r"^[a-z0-9]+$"),
    model: Optional[str] = Query(None, max_length=60),
    start_year: Optional[int] = Query(None, ge=2000, le=2200),
    end_year: Optional[int] = Query(None, ge=2000, le=2200),
    store: DatasetStore = Depends(get_store),
):
    valid = {s["id"] for s in store.scenarios()["scenarios"]}
    if scenario and scenario not in valid:
        raise DatasetUnavailable("unknown_scenario", f"Unknown scenario '{scenario}'.", f"Valid: {sorted(valid)}")
    ds = store.projection(location, variable)
    if model and model not in {m.id for m in ds.models}:
        raise DatasetUnavailable("unknown_model", f"Model '{model}' is not in this dataset.",
                                 f"Available: {[m.id for m in ds.models]}")

    def keep(scn, ty, mdl=None):
        return ((scenario is None or scn == scenario) and (model is None or mdl is None or mdl == model)
                and (start_year is None or ty >= start_year) and (end_year is None or ty <= end_year))

    ds = ds.model_copy(update={
        "records": [r for r in ds.records if keep(r.scenario, r.target_year, r.model)],
        "ensemble": [e for e in ds.ensemble if keep(e.scenario, e.target_year)],
        "windows": [w for w in ds.windows if (start_year is None or w.target_year >= start_year)
                    and (end_year is None or w.target_year <= end_year)],
    })
    return ClimateOut(dataset=ds, disclaimer=store.scenarios()["disclaimer"])


@router.get("/imagery/metadata")
def imagery_metadata(
    location: str = Query(..., pattern=r"^[a-z0-9_]+$"),
    year: Optional[int] = Query(None, ge=1900, le=2200),
    store: DatasetStore = Depends(get_store),
):
    store.location(location)
    meta = store.imagery()
    out = {"layers": meta["layers"], "resolution_note": meta["resolution_note"]}
    if year is not None:
        out["year"] = year
        out["availability"] = {l["id"]: imagery_for_year(l, year) for l in meta["layers"]}
    return out


@router.get("/provenance")
def provenance(
    location: str = Query(..., pattern=r"^[a-z0-9_]+$"),
    variable: str = Query("air_temperature", pattern=r"^[a-z0-9_]+$"),
    store: DatasetStore = Depends(get_store),
):
    """Provenance of every dataset for a location/variable, WITHOUT the records."""
    out = {"location": location, "variable": variable, "datasets": [], "unavailable": []}
    for kind, loader in (("observed", store.observed), ("projection", store.projection)):
        try:
            ds = loader(location, variable)
        except DatasetUnavailable as e:
            if e.code in {"unknown_location", "unknown_variable"}:
                raise
            out["unavailable"].append({"kind": kind, "code": e.code, "message": e.message, "hint": e.hint})
            continue
        d = ds.model_dump(exclude={"records", "ensemble"})
        d["kind"] = kind
        out["datasets"].append(d)
    return out
